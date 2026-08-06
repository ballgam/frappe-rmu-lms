# Copyright (c) 2026, FOSS United and contributors
# For license information, please see license.txt

"""Turning an uploaded video file into a DASH package.

    upload -> ffprobe -> ffmpeg (normalize, one output per stream) -> shaka-packager -> manifest.mpd

Runs on the `long` queue. Every intermediate lands in a per-video staging folder
that is renamed into place only after the packager succeeds, so a worker that
dies mid-encode leaves nothing a student could load.

The decisions about *what* ffmpeg should do live in `probe.py` as pure
functions; this module is the part that touches the filesystem and subprocesses.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time

import frappe
from frappe.utils import cint, flt, get_files_path

from lms.lms.video import paths, probe

#: Hard ceiling on any single subprocess. A 3-hour lecture re-encoded on a slow
#: box is the worst realistic case; beyond this something is wrong.
SUBPROCESS_TIMEOUT = 6 * 60 * 60

#: How often the encode publishes a progress event. Frequent enough to look
#: live, rare enough not to flood the socket for every viewer in the room.
PROGRESS_INTERVAL_SECONDS = 3

DEFAULT_SEGMENT_DURATION = 4

#: Shaka Packager ships no OS packages, so the default is to run the official
#: image rather than ask every bench to install a GitHub release binary by hand.
#: Sites that bake the binary into their own image can switch to "Binary".
DEFAULT_PACKAGER_IMAGE = "google/shaka-packager:latest"
PACKAGER_BINARY_NAMES = ("packager", "shaka-packager", "packager-linux-x64", "packager-osx-arm64")

#: Where the staging folder is mounted inside the container. The packager command
#: itself uses only relative paths, so it is identical in both modes.
CONTAINER_WORKDIR = "/work"


class VideoPipelineError(frappe.ValidationError):
	"""Anything that stops a video from being packaged, with a message meant to
	be read by whoever uploaded the file."""


def get_video_settings() -> frappe._dict:
	"""LMS Settings values for the pipeline, with defaults for pre-migrate sites."""
	defaults = {
		"video_transcoding_enabled": 1,
		"video_segment_duration": DEFAULT_SEGMENT_DURATION,
		"video_token_ttl_hours": 12,
		"keep_original_video": 1,
		"ffmpeg_path": "",
		"ffprobe_path": "",
		"video_packager_mode": "Docker",
		"video_packager_image": DEFAULT_PACKAGER_IMAGE,
		"packager_path": "",
		"docker_path": "",
	}
	try:
		# get_singles_dict returns only the fields actually stored for the
		# singleton. That distinction matters: get_cached_value reports an unset
		# Check field as 0, which is indistinguishable from an admin deliberately
		# switching it off — and would have left transcoding silently disabled on
		# every site that migrated without opening the settings form.
		stored = frappe.db.get_singles_dict("LMS Settings", cast=True) or {}
	except Exception:
		# Columns don't exist yet on a site that hasn't migrated.
		stored = {}

	values = frappe._dict(defaults)
	for key in defaults:
		if key in stored and stored[key] not in (None, ""):
			values[key] = stored[key]

	values.video_segment_duration = cint(values.video_segment_duration) or DEFAULT_SEGMENT_DURATION
	values.video_token_ttl_hours = flt(values.video_token_ttl_hours) or 12
	return values


def _resolve_binary(configured: str, names: tuple[str, ...], label: str) -> str:
	if configured:
		if os.path.isfile(configured) and os.access(configured, os.X_OK):
			return configured
		raise VideoPipelineError(
			frappe._("{0} is configured in LMS Settings as {1}, but that is not an executable file.").format(
				label, configured
			)
		)

	for name in names:
		found = shutil.which(name)
		if found:
			return found

	raise VideoPipelineError(
		frappe._(
			"{0} was not found on this server. Install it and make it available on PATH, "
			"or set its full path in LMS Settings. Looked for: {1}."
		).format(label, ", ".join(names))
	)


def ffmpeg_binary(settings=None) -> str:
	settings = settings or get_video_settings()
	return _resolve_binary(settings.ffmpeg_path, ("ffmpeg",), "ffmpeg")


def ffprobe_binary(settings=None) -> str:
	settings = settings or get_video_settings()
	return _resolve_binary(settings.ffprobe_path, ("ffprobe",), "ffprobe")


def packager_launcher(staging: str, settings=None) -> tuple[list[str], str | None]:
	"""How to invoke Shaka Packager, as (argv prefix, working directory).

	Two modes, because the packager has no OS packages anywhere:

	- **Docker** (default): run the official image with the staging folder bind
	  mounted at CONTAINER_WORKDIR. Nothing has to be installed on the bench.
	- **Binary**: a `packager` executable on PATH, for images that already bundle it.

	Either way the packager's own arguments are byte-for-byte identical, because
	they are all relative to the working directory.
	"""
	settings = settings or get_video_settings()

	if (settings.video_packager_mode or "Docker") == "Binary":
		return [_resolve_binary(settings.packager_path, PACKAGER_BINARY_NAMES, "Shaka Packager")], staging

	docker = _resolve_binary(settings.docker_path, ("docker", "podman"), "Docker")
	command = [docker, "run", "--rm", "--network", "none"]

	# Without this the container writes its output as root and the bench user can
	# neither publish nor clean up the package. Docker Desktop on macOS remaps
	# ownership itself, but passing it there is harmless.
	if hasattr(os, "getuid"):
		command += ["-u", f"{os.getuid()}:{os.getgid()}"]

	command += [
		"-v", f"{staging}:{CONTAINER_WORKDIR}",
		"-w", CONTAINER_WORKDIR,
		settings.video_packager_image or DEFAULT_PACKAGER_IMAGE,
		"packager",
	]
	return command, None


def check_packager_available(settings=None) -> str:
	"""Preflight the packager and return a human-readable description of it.

	Called before an upload is accepted and by the bench command, so a missing
	dependency surfaces as an actionable message instead of a stack trace two
	minutes into an encode.
	"""
	settings = settings or get_video_settings()
	launcher, _ = packager_launcher(tmp_root_for_probe(), settings)

	try:
		_run([*launcher, "--version"], label="Shaka Packager")
	except VideoPipelineError as exc:
		if (settings.video_packager_mode or "Docker") != "Binary":
			raise VideoPipelineError(
				frappe._(
					"Could not run Shaka Packager via Docker. Check that the Docker daemon is "
					"running and the image has been pulled:\n\n    docker pull {0}\n\nUnderlying error: {1}"
				).format(settings.video_packager_image or DEFAULT_PACKAGER_IMAGE, exc)
			)
		raise

	return " ".join(launcher)


def tmp_root_for_probe() -> str:
	"""A real, existing directory to bind mount for the --version check."""
	root = paths.tmp_root()
	os.makedirs(root, exist_ok=True)
	return root


def _run(command: list[str], cwd: str | None = None, label: str = "command") -> subprocess.CompletedProcess:
	"""Run a subprocess, or raise with the tail of its stderr.

	stdin is closed: ffmpeg prompts on stdin when an output file exists, and a
	background worker has no one to answer, so it would hang until the timeout.
	"""
	try:
		result = subprocess.run(
			command,
			cwd=cwd,
			stdin=subprocess.DEVNULL,
			capture_output=True,
			text=True,
			timeout=SUBPROCESS_TIMEOUT,
		)
	except subprocess.TimeoutExpired:
		raise VideoPipelineError(frappe._("{0} timed out after {1} hours.").format(label, SUBPROCESS_TIMEOUT // 3600))
	except OSError as exc:
		raise VideoPipelineError(frappe._("Could not run {0}: {1}").format(label, exc))

	if result.returncode != 0:
		tail = (result.stderr or result.stdout or "").strip()[-4000:]
		raise VideoPipelineError(frappe._("{0} failed:\n{1}").format(label, tail))

	return result


def run_ffprobe(source: str, settings=None) -> dict:
	result = _run(
		[
			ffprobe_binary(settings),
			"-v", "error",
			"-print_format", "json",
			"-show_streams",
			"-show_format",
			source,
		],
		label="ffprobe",
	)
	try:
		return json.loads(result.stdout)
	except json.JSONDecodeError:
		raise VideoPipelineError(frappe._("ffprobe returned output that could not be parsed."))


def probe_keyframe_gap(source: str, window_seconds: int = 60, settings=None) -> float | None:
	"""Largest gap between keyframes in the first `window_seconds`, or None.

	Decides whether the video stream can be stream-copied: the packager can only
	cut a segment at a keyframe, so a source with a 10-second GOP cannot produce
	4-second segments no matter what we ask for.

	`-skip_frame nokey` makes this cheap — ffprobe discards non-keyframes instead
	of decoding them. Returns None if the answer is unknowable, and the caller
	treats that as "no objection".
	"""
	try:
		result = _run(
			[
				ffprobe_binary(settings),
				"-v", "error",
				"-select_streams", "v:0",
				"-skip_frame", "nokey",
				"-show_entries", "frame=pts_time",
				"-read_intervals", f"%+{window_seconds}",
				"-of", "csv=p=0",
				source,
			],
			label="ffprobe keyframe scan",
		)
	except VideoPipelineError:
		return None

	times = []
	for line in result.stdout.splitlines():
		line = line.strip().rstrip(",")
		if not line:
			continue
		try:
			times.append(float(line))
		except ValueError:
			continue

	if len(times) < 2:
		# One keyframe (or none) in a whole minute is itself a reason not to copy,
		# but only if we actually saw the full window.
		return float(window_seconds) if times else None

	times.sort()
	return max(b - a for a, b in zip(times, times[1:], strict=False))


def compute_content_hash(path: str) -> str:
	digest = hashlib.sha256()
	with open(path, "rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _fps_flag(settings=None) -> str:
	"""`-fps_mode` replaced `-vsync` in ffmpeg 5.1; benches on older distros
	(Ubuntu 20.04 ships 4.2) still need the old spelling."""
	try:
		result = subprocess.run(
			[ffmpeg_binary(settings), "-hide_banner", "-loglevel", "quiet", "-h", "full"],
			stdin=subprocess.DEVNULL,
			capture_output=True,
			text=True,
			timeout=60,
		)
		return "-fps_mode" if "-fps_mode" in (result.stdout or "") else "-vsync"
	except Exception:
		return "-vsync"


def build_normalize_command(
	source: str,
	info: probe.MediaInfo,
	video_reason: str,
	audio_reasons: list[str],
	segment_duration: float,
	fps_flag: str,
	ffmpeg: str = "ffmpeg",
) -> tuple[list[str], str, list[str]]:
	"""One ffmpeg invocation producing one mp4 per stream.

	Multiple outputs from a single input means the source is decoded once, not
	once per audio track — which matters a lot for a lecture with four
	translations.

	Returns (argv, video_filename, audio_filenames).
	"""
	command = [ffmpeg, "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-i", source]

	video_name = "video.mp4"
	command += ["-map", "0:v:0"]
	command += probe.build_video_args(info.video, segment_duration, video_reason, fps_flag)
	command += ["-an", "-sn", "-dn", "-movflags", "+faststart", video_name]

	audio_names = []
	for position, (audio, reason) in enumerate(zip(info.audios, audio_reasons, strict=True)):
		name = f"audio_{position}.mp4"
		audio_names.append(name)
		# Map by absolute stream index, not by audio position: a container whose
		# audio streams are interleaved with data/subtitle streams would otherwise
		# be mismapped.
		command += ["-map", f"0:{audio.index}"]
		command += probe.build_audio_args(audio, reason)
		command += ["-vn", "-sn", "-dn", "-movflags", "+faststart", name]

	return command, video_name, audio_names


def build_packager_command(
	video_name: str,
	audio_names: list[str],
	audios: list[probe.AudioStream],
	segment_duration: int,
	launcher: list[str] | None = None,
) -> list[str]:
	"""Shaka Packager invocation, all paths relative to the output folder.

	Relative paths are load-bearing twice over: the packager writes the segment
	templates into the MPD verbatim, so absolute paths would leak this server's
	filesystem layout into a manifest the browser fetches — and they let the same
	arguments work unchanged whether the packager runs natively or inside a
	container where the folder is mounted somewhere else entirely.

	`launcher` is the argv prefix from `packager_launcher`.
	"""
	command = list(launcher or ["packager"])

	command.append(
		f"in={video_name},stream=video,"
		f"init_segment={paths.VIDEO_STREAM_DIR}/init.mp4,"
		f"segment_template={paths.VIDEO_STREAM_DIR}/$Number$.m4s"
	)

	# Exactly one audio track carries role=main, which is what a DASH player
	# treats as the default selection; without it the choice is arbitrary. Honour
	# the source's default disposition, else fall back to the first track.
	default_index = next((i for i, audio in enumerate(audios) if audio.is_default), 0)

	for index, (name, audio) in enumerate(zip(audio_names, audios, strict=True)):
		folder = audio_segment_dir(audio)
		descriptor = (
			f"in={name},stream=audio,"
			f"init_segment={folder}/init.mp4,"
			f"segment_template={folder}/$Number$.m4s,"
			f"lang={audio.manifest_lang}"
		)
		if index == default_index:
			descriptor += ",roles=main"
		command.append(descriptor)

	command += [
		"--segment_duration", str(segment_duration),
		"--generate_static_live_mpd",
		"--mpd_output", paths.MANIFEST_NAME,
	]
	return command


def read_manifest_audio_langs(manifest_path: str) -> dict[str, str]:
	"""Map each audio segment folder to the `lang` the packager actually wrote.

	Shaka Packager rewrites language codes on its way into the MPD: it collapses
	ISO 639-2 to 639-1 where an equivalent exists, so `lang=eng` comes back out as
	`lang="en"` and `lang=som` as `"so"`. Codes with no two-letter form — including
	every synthetic `qaa`-range code — pass through untouched.

	That matters because the player identifies a track by the manifest's `lang`,
	and `LMS Video Audio Track.manifest_lang` is the key we join the instructor's
	label to. Guessing the normalization rules would be fragile, so the truth is
	read back out of the artifact we just produced. The segment template still
	carries the folder name we chose, which ties each AdaptationSet
	unambiguously back to the stream it came from.
	"""
	import xml.etree.ElementTree as ElementTree

	try:
		root = ElementTree.parse(manifest_path).getroot()
	except (ElementTree.ParseError, OSError) as exc:
		raise VideoPipelineError(frappe._("The packager produced an unreadable manifest: {0}").format(exc))

	mapping: dict[str, str] = {}
	# Tag names are namespaced; compare on the local name so a namespace change
	# in a future packager release doesn't silently return an empty mapping.
	for node in root.iter():
		if not node.tag.endswith("}AdaptationSet") and node.tag != "AdaptationSet":
			continue
		if node.get("contentType") != "audio":
			continue

		lang = node.get("lang")
		template = next(
			(
				child.get("media")
				for child in node.iter()
				if (child.tag.endswith("}SegmentTemplate") or child.tag == "SegmentTemplate")
				and child.get("media")
			),
			None,
		)
		if lang and template and "/" in template:
			mapping[template.split("/", 1)[0]] = lang

	return mapping


def audio_segment_dir(audio: probe.AudioStream) -> str:
	"""Folder the packager writes this track's segments into.

	Named from the code we *request*, which is not always the code that ends up
	in the manifest — see read_manifest_audio_langs.
	"""
	return f"{paths.AUDIO_STREAM_DIR_PREFIX}{audio.manifest_lang}"


def absolute_file_path(file_url: str) -> str:
	"""Resolve a File doctype url to a path on disk, refusing to escape the files dir."""
	if not file_url:
		raise VideoPipelineError(frappe._("This video has no source file."))

	is_private = file_url.startswith("/private")
	relative = file_url.split("/files/", 1)[-1].lstrip("/")
	root = os.path.realpath(get_files_path(is_private=is_private))
	target = os.path.realpath(os.path.join(root, relative))

	if not target.startswith(root + os.sep):
		raise VideoPipelineError(frappe._("Invalid source file path."))
	if not os.path.isfile(target):
		raise VideoPipelineError(frappe._("Source file is missing from disk: {0}").format(file_url))

	return target


def _run_ffmpeg_with_progress(command: list[str], cwd: str, doc, total_duration: float):
	"""Run the encode, republishing progress as it goes.

	`-progress pipe:1` makes ffmpeg emit `key=value` blocks on stdout; `out_time_us`
	is how far into the source it has got, which against the probed duration gives
	a real percentage rather than a spinner. Publishing is throttled — a two-hour
	encode would otherwise emit thousands of socket events that every viewer in
	the website room receives.
	"""
	# stderr goes to a file rather than a second pipe. Draining only stdout while
	# stderr fills its 64 KB pipe buffer would deadlock: ffmpeg blocks writing a
	# warning, so it stops emitting progress, so this loop blocks reading it.
	with tempfile.TemporaryFile(mode="w+") as errors:
		try:
			process = subprocess.Popen(
				command,
				cwd=cwd,
				stdin=subprocess.DEVNULL,
				stdout=subprocess.PIPE,
				stderr=errors,
				text=True,
			)
		except OSError as exc:
			raise VideoPipelineError(frappe._("Could not run ffmpeg: {0}").format(exc))

		last_published = 0.0
		for line in process.stdout:
			key, _, value = line.strip().partition("=")
			if key not in ("out_time_us", "out_time_ms"):
				continue
			try:
				# Both keys are microseconds — `out_time_ms` is a long-standing
				# misnomer in ffmpeg, not a different unit.
				seconds = int(value) / 1_000_000
			except ValueError:
				continue

			now = time.monotonic()
			if now - last_published < PROGRESS_INTERVAL_SECONDS:
				continue
			last_published = now

			percent = min(99, int(seconds / total_duration * 100)) if total_duration > 0 else 0
			publish_progress(doc, percent)

		process.wait(timeout=SUBPROCESS_TIMEOUT)

		if process.returncode != 0:
			errors.seek(0)
			raise VideoPipelineError(frappe._("ffmpeg failed:\n{0}").format(errors.read().strip()[-4000:]))


def publish_progress(doc, percent: int):
	from frappe.realtime import get_website_room

	frappe.publish_realtime(
		event="lms_video_status",
		room=get_website_room(),
		message={"video_id": doc.video_id, "status": "Packaging", "progress": percent},
	)


def extract_poster(source: str, destination: str, duration: float, settings=None):
	"""Grab a still for the player's poster frame. Best-effort — a video that
	packages fine but has an unreadable first frame should still be playable."""
	timestamp = min(3.0, duration / 2) if duration > 0 else 0
	try:
		_run(
			[
				ffmpeg_binary(settings),
				"-nostdin", "-y", "-loglevel", "error",
				"-ss", f"{timestamp:.3f}",
				"-i", source,
				"-frames:v", "1",
				"-q:v", "3",
				destination,
			],
			label="poster extraction",
		)
	except VideoPipelineError:
		frappe.logger("lms").warning(f"Could not extract a poster frame from {source}", exc_info=True)


def _move_into_place(staging: str, final: str):
	"""Publish the staging folder as the live one, replacing any previous package.

	The rename is the commit point of the whole pipeline — until it runs, nothing
	under the live path has changed, so a crashed encode is invisible to readers.
	"""
	os.makedirs(os.path.dirname(final), exist_ok=True)

	superseded = f"{final}.superseded-{frappe.generate_hash(length=8)}"
	had_previous = os.path.exists(final)
	if had_previous:
		os.rename(final, superseded)

	try:
		try:
			os.rename(staging, final)
		except OSError:
			# private/ and public/ could be separate mounts, where rename gives EXDEV.
			shutil.move(staging, final)
	except BaseException:
		if had_previous:
			os.rename(superseded, final)
		raise

	if had_previous:
		shutil.rmtree(superseded, ignore_errors=True)


def package_video(video: str):
	"""Package one LMS Video. This is the enqueued job.

	Failures are recorded on the doc and swallowed rather than re-raised: the
	uploader needs to see *why* their file didn't package (the error log is shown
	in the editor), and the block already falls back to progressive playback of
	the original file, so a failure degrades rather than breaks the lesson.
	"""
	doc = frappe.get_doc("LMS Video", video)
	staging = paths.tmp_dir(doc.video_id)

	try:
		_package(doc, staging)
	except Exception as exc:
		message = str(exc) if isinstance(exc, VideoPipelineError) else frappe.get_traceback()
		frappe.logger("lms").error(f"Video packaging failed for {doc.video_id}: {message}")
		frappe.db.rollback()
		doc.set_status("Failed", error=message)
	finally:
		shutil.rmtree(staging, ignore_errors=True)


def _package(doc, staging: str):
	settings = get_video_settings()
	segment_duration = settings.video_segment_duration
	source = absolute_file_path(doc.source_file_url)

	shutil.rmtree(staging, ignore_errors=True)
	os.makedirs(staging, exist_ok=True)

	doc.set_status("Probing")
	raw_probe = run_ffprobe(source, settings)
	info = probe.parse_probe(raw_probe)

	if not info.has_video:
		raise VideoPipelineError(
			frappe._("This file has no video track. Upload it as audio instead.")
		)

	probe.assign_manifest_langs(info.audios)

	# The keyframe scan only matters if everything else already permits a copy;
	# it is the one probe step that reads into the file, so don't pay for it when
	# the codec check has already forced a re-encode.
	preliminary = probe.needs_video_reencode(info.video, None, segment_duration)
	keyframe_gap = probe_keyframe_gap(source, settings=settings) if not preliminary else None
	video_reason = probe.needs_video_reencode(info.video, keyframe_gap, segment_duration)
	audio_reasons = [probe.needs_audio_reencode(audio) for audio in info.audios]

	doc.set_status("Packaging")

	normalize_command, video_name, audio_names = build_normalize_command(
		source=source,
		info=info,
		video_reason=video_reason,
		audio_reasons=audio_reasons,
		segment_duration=segment_duration,
		fps_flag=_fps_flag(settings),
		ffmpeg=ffmpeg_binary(settings),
	)
	_run_ffmpeg_with_progress(normalize_command, staging, doc, info.duration)

	launcher, packager_cwd = packager_launcher(staging, settings)
	_run(
		build_packager_command(
			video_name=video_name,
			audio_names=audio_names,
			audios=info.audios,
			segment_duration=segment_duration,
			launcher=launcher,
		),
		cwd=packager_cwd,
		label="Shaka Packager",
	)

	manifest_langs = read_manifest_audio_langs(os.path.join(staging, paths.MANIFEST_NAME))

	extract_poster(source, os.path.join(staging, paths.POSTER_NAME), info.duration, settings)

	with open(os.path.join(staging, paths.PROBE_NAME), "w") as handle:
		json.dump(
			{
				"format": raw_probe.get("format"),
				"streams": raw_probe.get("streams"),
				"decisions": {"video": video_reason or "stream copy", "audio": audio_reasons},
			},
			handle,
			indent=2,
		)

	# The intermediates fed to the packager are dead weight once it has run.
	for name in [video_name, *audio_names]:
		_remove_quietly(os.path.join(staging, name))

	if cint(settings.keep_original_video):
		extension = os.path.splitext(doc.source_file_url)[1].lower() or ".bin"
		shutil.copy2(source, os.path.join(staging, f"source{extension}"))

	is_private = bool(cint(doc.is_private))
	_move_into_place(staging, paths.video_dir(doc.video_id, is_private=is_private))

	_write_result(doc, info, is_private, manifest_langs)


def _remove_quietly(path: str):
	try:
		os.remove(path)
	except OSError:
		pass


def _write_result(doc, info: probe.MediaInfo, is_private: bool, manifest_langs: dict[str, str]):
	"""Record the finished package and hand the player its track list."""
	doc.set("audio_tracks", [])
	for position, audio in enumerate(info.audios, start=1):
		segment_dir = audio_segment_dir(audio)
		doc.append(
			"audio_tracks",
			{
				"track_index": audio.index,
				"segment_dir": segment_dir,
				# What the packager actually wrote, not what we asked for — this is
				# the code the player will report back when the learner picks a track.
				"manifest_lang": manifest_langs.get(segment_dir, audio.manifest_lang),
				"detected_language": audio.detected_language,
				# Pre-fill the editable fields with the best guess available. An
				# instructor can correct them later without any repackaging,
				# because the manifest is keyed on manifest_lang, not on these.
				"language": audio.detected_language
				if audio.detected_language not in probe.UNKNOWN_LANGUAGES
				else "",
				"label": probe.default_track_label(audio, position),
				"codec": audio.codec_name,
				"channels": audio.channels,
				"is_default": audio.is_default,
			},
		)

	doc.manifest_url = paths.manifest_url(doc.video_id, is_private=is_private)
	doc.poster_url = paths.poster_url(doc.video_id, is_private=is_private)
	doc.duration = info.duration
	doc.width = info.video.width
	doc.height = info.video.height
	doc.status = "Ready"
	doc.error_log = ""
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	from lms.lms.doctype.lms_video.lms_video import publish_video_status

	publish_video_status(doc)


def enqueue_packaging(video: str, now: bool = False):
	frappe.enqueue(
		"lms.lms.video.pipeline.package_video",
		queue="long",
		timeout=SUBPROCESS_TIMEOUT,
		# One job per video: a lesson saved three times while its video is still
		# encoding should not start three encodes of the same file.
		job_id=f"lms-package-video::{video}",
		deduplicate=True,
		enqueue_after_commit=True,
		now=now,
		video=video,
	)
