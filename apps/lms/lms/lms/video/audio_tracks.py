# Copyright (c) 2026, FOSS United and contributors
# For license information, please see license.txt

"""Adding and removing audio tracks on a video that is already packaged.

Translations arrive late. A lecture is recorded, packaged and published, and the
Somali narration turns up three months later — by which time re-uploading the
lecture would orphan its `LMS Video`, its watch-duration records and every
lesson that references it.

So a new track is packaged *on its own* and grafted onto the live package: its
segments go into a new `audio_<lang>/` folder beside the existing ones, and one
`<AdaptationSet>` is merged into `manifest.mpd`. The video's own segments are
never read, never rewritten, and never re-encoded. A learner watching while it
happens sees nothing at all until they reload.

Two things make that safe:

- **The manifest is the commit point.** Segments are copied in first, where
  nothing references them, and the manifest is swapped with `os.replace` — so
  every readable state of the folder is a consistent one.
- **One job per video.** Every add and remove for a video runs in the same
  serialized job, because two workers rewriting one manifest would lose an
  AdaptationSet.
"""

from __future__ import annotations

import os
import re
import shutil

import frappe
from frappe import _
from frappe.utils import cint, flt
from frappe.utils.file_lock import LockTimeoutError
from frappe.utils.synchronization import filelock

from lms.lms.video import manifest, paths, pipeline, probe

#: Statuses a row can hold while waiting for the worker.
QUEUED_STATUSES = ("Pending", "Removing")

#: A segment folder we are willing to delete. Everything we create matches it;
#: anything that does not is not ours to remove.
SEGMENT_DIR_RE = re.compile(rf"^{paths.AUDIO_STREAM_DIR_PREFIX}[A-Za-z0-9_]{{1,36}}$")


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


@frappe.whitelist()
def upload_audio_source() -> dict:
	"""Receive the audio file for a track, in place of Frappe's generic uploader.

	`frappe.handler.upload_file` refuses every `audio/*` mimetype for users
	without desk access — its ALLOWED_MIMETYPES admits `video/mp4` and
	`video/quicktime` and no audio at all. Course creators in this app are
	Website Users, so uploading a lecture works and uploading its translated
	narration returns 417 before any of our code runs.

	Rather than loosening that list for the whole site, the upload comes here,
	where it can be gated on the thing that actually matters: may this user edit
	*this video's* tracks. That is a narrower permission than the generic
	endpoint's, not a wider one — the file must be audio or video we can import,
	it is always private, and the site's own size ceiling still applies.

	Called by the editor's FileUploader through `upload_endpoint`, so the fields
	available are the ones that component sends: the file itself, plus
	doctype/docname naming the video.
	"""
	from lms.lms.video.api import _assert_can_edit, _get_video

	files = getattr(frappe.request, "files", None) or {}
	upload = files.get("file")
	if upload is None:
		frappe.throw(_("No file was uploaded."))

	video_id = frappe.form_dict.get("docname")
	meta = _get_video(video_id)
	_assert_can_edit(meta)

	filename = upload.filename or ""
	if not paths.is_importable_audio_source(filename):
		frappe.throw(_("{0} is not an audio or video file.").format(filename))

	content = upload.stream.read()
	_assert_within_size_limit(len(content))

	doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": filename,
			"content": content,
			"is_private": 1,
			"attached_to_doctype": "LMS Video",
			"attached_to_name": meta.name,
		}
	).insert(ignore_permissions=True)

	return {"file_url": doc.file_url, "file_name": doc.file_name}


def _assert_within_size_limit(size: int):
	"""Honour the site's upload ceiling, with a message that says how to raise it.

	Deliberately not bypassed: it is an administrator's setting, and a lecture's
	audio is large enough that silently ignoring it would be how a bench first
	learns its disk is full.
	"""
	from frappe.core.api.file import get_max_file_size

	limit = get_max_file_size()
	if size <= limit:
		return

	frappe.throw(
		_(
			"This file is {0} MB, over this site's {1} MB upload limit. Raise it with:"
			"\n\n    bench --site {2} set-config max_file_size <bytes>"
		).format(round(size / 1048576, 1), round(limit / 1048576, 1), frappe.local.site)
	)


@frappe.whitelist()
def add_audio_track(
	video_id: str,
	file_url: str,
	label: str = None,
	language: str = None,
	stream_index: int = None,
) -> dict:
	"""Queue an audio track to be imported into an existing package.

	Validation happens here, synchronously, rather than in the worker: picking
	the wrong file is by far the most likely failure, and an author who is told
	so while the upload dialog is still open can just pick again.
	"""
	from lms.lms.video.api import _assert_can_edit, _audio_track_rows, _get_video

	meta = _get_video(video_id)
	_assert_can_edit(meta)

	if meta.status != "Ready":
		frappe.throw(
			_("This video is still being prepared. Audio tracks can be added once it is ready.")
		)

	if not paths.is_importable_audio_source(file_url):
		frappe.throw(_("{0} is not an audio or video file.").format(file_url))

	settings = pipeline.get_video_settings()
	# Refuses anything outside the site's files directory, and anything missing.
	source = pipeline.absolute_file_path(file_url)

	info = probe.parse_probe(pipeline.run_ffprobe(source, settings))
	if not info.has_audio:
		frappe.throw(_("{0} contains no audio track.").format(file_url))

	audio = _pick_stream(info, stream_index)

	mismatch = probe.duration_mismatch_reason(info.duration, flt(meta.duration))
	if mismatch:
		frappe.throw(
			_("This does not look like the audio for this video — {0}.").format(mismatch)
		)

	# Do not create a Pending row that can only fail in the long worker. This is
	# intentionally after source validation, so an author with a bad file still
	# sees that concrete problem first, but before the document/file attachment
	# changes that make a failed import visible in the editor.
	pipeline.check_video_pipeline(settings)

	doc = frappe.get_doc("LMS Video", meta.name)
	code = _reserve_lang(doc)

	row = doc.append(
		"audio_tracks",
		{
			"origin": "Added",
			"status": "Pending",
			"source_file_url": file_url,
			"source_stream_index": audio.index,
			"track_index": audio.index,
			"segment_dir": f"{paths.AUDIO_STREAM_DIR_PREFIX}{code}",
			# Provisional: replaced with whatever the packager actually writes
			# into the manifest, which is the code the player reports back.
			"manifest_lang": code,
			"detected_language": audio.detected_language,
			"language": (language or "").strip(),
			"label": (label or "").strip() or probe.default_track_label(audio, len(doc.audio_tracks) + 1),
			"codec": audio.codec_name,
			"channels": audio.channels,
			"is_default": 0,
		},
	)
	doc.save(ignore_permissions=True)

	_attach_source(file_url, doc.name)
	enqueue_track_operations(doc.name)

	return {"video_id": video_id, "track": _row_summary(row), "audio_tracks": _audio_track_rows(doc.name)}


@frappe.whitelist()
def remove_audio_track(video_id: str, manifest_lang: str) -> dict:
	"""Queue an audio track for removal from the package."""
	from lms.lms.video.api import _assert_can_edit, _audio_track_rows, _get_video

	meta = _get_video(video_id)
	_assert_can_edit(meta)

	doc = frappe.get_doc("LMS Video", meta.name)
	row = _find_row(doc, manifest_lang)

	published = _published_segment_dirs(doc)
	in_manifest = row.segment_dir in published

	# Only tracks that are actually in the manifest count towards the floor:
	# a queued or failed one is invisible to learners, so leaving it as the sole
	# survivor would be leaving the package with no audio at all.
	if in_manifest:
		remaining = [
			other
			for other in doc.audio_tracks
			if other.name != row.name
			and other.status == "Ready"
			and other.segment_dir in published
		]
		if not remaining:
			frappe.throw(_("A video must keep at least one audio track."))

	if not in_manifest and row.status in ("Pending", "Failed"):
		# Nothing in the manifest and nothing on disk, so drop it outright rather
		# than queueing work that would no-op. The manifest is re-checked rather
		# than inferred from the status, because a track can reach Failed *after*
		# its AdaptationSet was merged — and deleting the row then would leave an
		# entry in the audio menu pointing at segments no row remembers.
		doc.remove(row)
		doc.save(ignore_permissions=True)
		return {"video_id": video_id, "audio_tracks": _audio_track_rows(doc.name)}

	row.db_set("status", "Removing", update_modified=True)
	enqueue_track_operations(doc.name)

	return {"video_id": video_id, "audio_tracks": _audio_track_rows(doc.name)}


@frappe.whitelist()
def retry_audio_track(video_id: str, manifest_lang: str) -> dict:
	"""Re-queue a track whose import failed."""
	from lms.lms.video.api import _assert_can_edit, _audio_track_rows, _get_video

	meta = _get_video(video_id)
	_assert_can_edit(meta)

	doc = frappe.get_doc("LMS Video", meta.name)
	row = _find_row(doc, manifest_lang)

	if row.status != "Failed":
		frappe.throw(_("This track is not in a failed state."))
	if not row.source_file_url:
		frappe.throw(_("This track has no source file to import from."))

	# The usual reason a track failed is that the tooling was not there. Say so
	# now rather than flipping the row back to Pending for a worker that is
	# still going to fail on exactly the same thing.
	pipeline.check_video_pipeline()

	row.db_set("status", "Pending", update_modified=False)
	row.db_set("error_log", "", update_modified=False)
	enqueue_track_operations(doc.name)

	return {"video_id": video_id, "audio_tracks": _audio_track_rows(doc.name)}


# --------------------------------------------------------------------------
# Queueing
# --------------------------------------------------------------------------


def enqueue_track_operations(video: str, now: bool = False):
	frappe.enqueue(
		"lms.lms.video.audio_tracks.process_track_operations",
		queue="long",
		timeout=pipeline.SUBPROCESS_TIMEOUT,
		# One job per video: every operation rewrites the same manifest, so they
		# have to run one after another. The job drains whatever is pending when
		# it gets there, which is also why deduplicating is safe.
		job_id=f"lms-audio-tracks::{video}",
		deduplicate=True,
		enqueue_after_commit=True,
		now=now,
		video=video,
	)


def pending_operations(video: str) -> list[str]:
	return frappe.get_all(
		"LMS Video Audio Track",
		filters={
			"parent": video,
			"parenttype": "LMS Video",
			"parentfield": "audio_tracks",
			"status": ["in", QUEUED_STATUSES],
		},
		order_by="idx asc",
		pluck="name",
	)


def process_track_operations(video: str):
	"""Drain every queued add and remove for one video. This is the enqueued job.

	Every operation is a read-modify-write of one `manifest.mpd`, so two of them
	running at once would lose an AdaptationSet. `enqueue_track_operations`
	deduplicates on the video, which covers the normal path — but a job enqueued
	in the instant an identical one is finishing, or a hand-run from `bench
	execute`, can still overlap. The lock makes that impossible rather than
	unlikely.

	A drain that cannot get the lock returns instead of waiting: whoever holds it
	re-queries for pending rows on every pass, so it will pick up ours too.
	"""
	from filelock import Timeout

	try:
		with filelock(f"lms-audio-tracks-{video}", timeout=1):
			_drain(video)
	except (Timeout, LockTimeoutError):
		frappe.logger("lms").info(
			f"Audio track operations for {video} are already being drained; leaving them to that job"
		)


def _drain(video: str):
	"""Re-queried each pass rather than snapshotted up front, so a track added
	while a long import is running is picked up by the same job instead of
	waiting for the next one."""
	# A row the query returns but the parent document does not carry cannot be
	# worked on. Remembering it bounds the loop: without this, one such row would
	# be re-queried forever, holding the lock and a long-queue worker until the
	# six-hour job timeout.
	unreachable: set[str] = set()

	while True:
		frappe.db.commit()
		names = [name for name in pending_operations(video) if name not in unreachable]
		if not names:
			return

		doc = frappe.get_doc("LMS Video", video)
		row = next((child for child in doc.audio_tracks if child.name == names[0]), None)
		if row is None:
			frappe.logger("lms").warning(
				f"Audio track row {names[0]} is queued but not on LMS Video {video}; skipping it"
			)
			unreachable.add(names[0])
			continue

		try:
			if row.status == "Removing":
				_remove(doc, row)
			else:
				_import(doc, row)
		except Exception as exc:
			message = str(exc) if isinstance(exc, pipeline.VideoPipelineError) else frappe.get_traceback()
			frappe.logger("lms").error(
				f"Audio track {row.manifest_lang} failed for video {doc.video_id}: {message}"
			)
			frappe.db.rollback()
			_set_row(row, status="Failed", error_log=message)
			publish_track_status(doc, row)


# --------------------------------------------------------------------------
# The work
# --------------------------------------------------------------------------


def _import(doc, row):
	"""Package one audio file and graft it onto the live manifest."""
	settings = pipeline.get_video_settings()
	is_private = bool(cint(doc.is_private))
	video_folder = paths.video_dir(doc.video_id, is_private=is_private)
	manifest_path = paths.manifest_path(doc.video_id, is_private=is_private)

	if not os.path.isfile(manifest_path):
		raise pipeline.VideoPipelineError(
			_("This video has no manifest to add a track to. Repackage it first.")
		)

	_set_row(row, status="Processing", error_log="")
	publish_track_status(doc, row, progress=0)

	source = pipeline.absolute_file_path(row.source_file_url)
	staging = paths.track_tmp_dir(doc.video_id, row.name)
	shutil.rmtree(staging, ignore_errors=True)
	os.makedirs(staging, exist_ok=True)

	segment_dir = row.segment_dir
	destination = os.path.join(video_folder, segment_dir)
	moved = False
	committed = False

	try:
		info = probe.parse_probe(pipeline.run_ffprobe(source, settings))
		if not info.has_audio:
			raise pipeline.VideoPipelineError(_("The source file no longer contains any audio."))

		audio = _pick_stream(info, row.source_stream_index)

		target_duration = flt(doc.duration)
		align = probe.needs_duration_alignment(info.duration, target_duration)
		reason = probe.needs_audio_reencode(audio)
		if align and not reason:
			# apad is a filter, so aligning rules out the stream copy that would
			# otherwise have been possible.
			reason = f"aligning {info.duration:.1f}s of audio to the video's {target_duration:.1f}s"

		command, name = pipeline.build_audio_import_command(
			source=source,
			audio=audio,
			reason=reason,
			align_to=target_duration if align else None,
			ffmpeg=pipeline.ffmpeg_binary(settings),
		)
		pipeline._run_ffmpeg_with_progress(
			command,
			staging,
			doc,
			info.duration,
			on_progress=lambda _doc, percent: publish_track_status(doc, row, progress=percent),
		)

		launcher, packager_cwd = pipeline.packager_launcher(staging, settings)
		pipeline._run(
			pipeline.build_audio_packager_command(
				name=name,
				segment_dir=segment_dir,
				lang=row.manifest_lang,
				segment_duration=_segment_duration(manifest_path, settings),
				launcher=launcher,
			),
			cwd=packager_cwd,
			label="Shaka Packager",
		)

		track_manifest = os.path.join(staging, paths.TRACK_MANIFEST_NAME)
		written_lang = _written_lang(track_manifest, segment_dir, row.manifest_lang)
		_assert_lang_free(manifest_path, segment_dir, written_lang)

		staged_segments = os.path.join(staging, segment_dir)
		if not os.path.isdir(staged_segments):
			raise pipeline.VideoPipelineError(
				_("The packager produced no segments for this track.")
			)

		# Segments first. Nothing points at this folder until the manifest does,
		# so a crash between here and the swap below leaves the package exactly
		# as it was, plus some bytes the next attempt overwrites.
		_replace_dir(staged_segments, destination)
		moved = True

		with open(track_manifest) as handle:
			fragment = handle.read()
		with open(manifest_path) as handle:
			base = handle.read()

		_atomic_write(manifest_path, manifest.merge_audio_adaptation_set(base, fragment, segment_dir))
		committed = True

		_set_row(
			row,
			# An author who asked for this track to be removed while it was still
			# importing must not have that request overwritten by the import
			# finishing. The manifest merge has already happened, so the removal is
			# real work now; leave the row queued for it.
			status="Removing" if _requested_removal(row) else "Ready",
			manifest_lang=written_lang,
			codec=audio.codec_name,
			channels=audio.channels,
			detected_language=audio.detected_language,
			error_log="",
		)
		publish_track_status(doc, row)

	except BaseException:
		# Only before the manifest names this folder. Once it does, deleting the
		# segments would point the live manifest at nothing — leave them for the
		# removal that a Failed row invites.
		if moved and not committed:
			shutil.rmtree(destination, ignore_errors=True)
		raise
	finally:
		shutil.rmtree(staging, ignore_errors=True)


def _requested_removal(row) -> bool:
	"""Whether this row was marked for removal while its import was running."""
	return frappe.db.get_value("LMS Video Audio Track", row.name, "status") == "Removing"


def _remove(doc, row):
	"""Drop a track from the manifest, then from disk, then from the doc."""
	is_private = bool(cint(doc.is_private))
	manifest_path = paths.manifest_path(doc.video_id, is_private=is_private)
	segment_dir = row.segment_dir

	# Manifest first: once it no longer lists the track, no player can ask for a
	# segment that is about to disappear.
	if os.path.isfile(manifest_path) and segment_dir:
		with open(manifest_path) as handle:
			base = handle.read()
		_atomic_write(manifest_path, manifest.remove_audio_adaptation_set(base, segment_dir))

	if segment_dir and SEGMENT_DIR_RE.match(segment_dir):
		from lms.lms.doctype.lms_video.lms_video import _rmtree_if_inside_site

		_rmtree_if_inside_site(os.path.join(paths.video_dir(doc.video_id, is_private=is_private), segment_dir))

	removed_lang = row.manifest_lang
	doc.remove(row)
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	publish_track_status(doc, None, removed=removed_lang)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _published_segment_dirs(doc) -> set[str]:
	"""Segment folders the live manifest actually lists.

	The rows record what a job intended; the manifest is what learners can reach.
	They diverge whenever a worker dies between merging an AdaptationSet and
	recording that it did, so anything that decides whether a track is really
	published has to ask the manifest.
	"""
	try:
		with open(paths.manifest_path(doc.video_id, is_private=bool(cint(doc.is_private)))) as handle:
			root = manifest.parse(handle.read())
	except (OSError, manifest.ManifestError):
		return set()

	return {
		folder
		for folder in (manifest.segment_dir_of(node) for node in manifest.audio_adaptation_sets(root))
		if folder
	}


def _attach_source(file_url: str, video: str):
	"""Record the upload against the video it was imported into.

	The editor uploads it unattached — attaching client-side would demand write
	permission on LMS Video, which an instructor who is not also a Course Creator
	does not have. Doing it here, after `_assert_can_edit` has already run, keeps
	the file out of the site's orphaned-attachment sweeps and makes the source of
	a translation visible from the video in Desk.

	Best-effort: a track whose file is never linked still imports fine.
	"""
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		return

	if frappe.db.get_value("File", name, "attached_to_doctype"):
		# Already belongs to something — a re-used upload, say. Leave it alone.
		return

	frappe.db.set_value(
		"File",
		name,
		{"attached_to_doctype": "LMS Video", "attached_to_name": video},
		update_modified=False,
	)


def _pick_stream(info: probe.MediaInfo, stream_index) -> probe.AudioStream:
	"""The audio stream to import: the requested one, else the first."""
	if stream_index is not None and str(stream_index) != "":
		wanted = cint(stream_index)
		match = next((audio for audio in info.audios if audio.index == wanted), None)
		if match is None:
			frappe.throw(_("The selected file has no audio stream at index {0}.").format(wanted))
		return match
	return info.audios[0]


def _reserve_lang(doc) -> str:
	"""A manifest language code no other track on this video is using.

	Added tracks always get a code from the ISO 639-2 private-use range rather
	than the real language, because the packager rewrites real codes on their way
	into the MPD (`fra` becomes `fr`) and a code that collides after that rewrite
	would silently merge two tracks into one entry in the player's menu.
	Private-use codes pass through untouched, so a collision is impossible.

	The instructor's actual language lives in `language` and the display name in
	`label` — as it already does for the untagged tracks that make up most real
	uploads.
	"""
	used = set()

	for row in doc.audio_tracks:
		if row.manifest_lang:
			used.add(row.manifest_lang.strip().lower())
		if row.segment_dir:
			used.add(row.segment_dir[len(paths.AUDIO_STREAM_DIR_PREFIX) :].strip().lower())

	# The manifest is the authority on what is actually in the package; the rows
	# can only ever be a view of it that drifted.
	try:
		with open(paths.manifest_path(doc.video_id, is_private=bool(cint(doc.is_private)))) as handle:
			root = manifest.parse(handle.read())
		used |= {lang.lower() for lang in manifest.used_langs(root)}
		used |= {
			folder[len(paths.AUDIO_STREAM_DIR_PREFIX) :].lower()
			for folder in manifest.used_segment_dirs(root)
			if folder.startswith(paths.AUDIO_STREAM_DIR_PREFIX)
		}
	except (OSError, manifest.ManifestError):
		# Falling back to the rows alone is safe: the collision check before the
		# manifest is written catches anything this missed.
		pass

	return probe.assign_manifest_lang("", used)


def _written_lang(track_manifest: str, segment_dir: str, requested: str) -> str:
	"""The `lang` the packager actually wrote for this track.

	`manifest_lang` is the key the player reports back when a learner picks a
	track, so it has to be read out of the artifact rather than assumed — the
	same reason `pipeline.read_manifest_audio_langs` exists.
	"""
	langs = pipeline.read_manifest_audio_langs(track_manifest)
	return langs.get(segment_dir) or requested


def _assert_lang_free(manifest_path: str, segment_dir: str, lang: str):
	"""Refuse to merge a track whose lang another AdaptationSet already claims.

	Two AdaptationSets sharing a `lang` collapse into one entry in every player,
	which would lose a track rather than add one.
	"""
	try:
		with open(manifest_path) as handle:
			root = manifest.parse(handle.read())
	except (OSError, manifest.ManifestError):
		return

	for adaptation_set in manifest.audio_adaptation_sets(root):
		if manifest.segment_dir_of(adaptation_set) == segment_dir:
			continue
		if (adaptation_set.get("lang") or "").lower() == (lang or "").lower():
			raise pipeline.VideoPipelineError(
				_("Another audio track in this video already uses the language code {0}.").format(lang)
			)


def _segment_duration(manifest_path: str, settings) -> float:
	"""Segment length this package was built with.

	Read from the manifest rather than LMS Settings: the setting may well have
	been changed in the months between the original upload and this translation,
	and segments of two different lengths in one package make a player's
	buffering decisions erratic.
	"""
	try:
		with open(manifest_path) as handle:
			found = manifest.segment_duration(manifest.parse(handle.read()))
	except (OSError, manifest.ManifestError):
		found = None

	return found or flt(settings.video_segment_duration) or 4.0


def _replace_dir(source: str, destination: str):
	shutil.rmtree(destination, ignore_errors=True)
	os.makedirs(os.path.dirname(destination), exist_ok=True)
	try:
		os.rename(source, destination)
	except OSError:
		# Staging is always private; a public video's folder can be on another mount.
		shutil.move(source, destination)


def _atomic_write(path: str, content: str):
	"""Replace a file's contents without any reader seeing a partial one.

	The temporary file is deliberately a sibling: `os.replace` is only atomic
	within a filesystem, and the manifest is the one thing a player must never
	read half of.
	"""
	temporary = f"{path}.{frappe.generate_hash(length=8)}.tmp"
	try:
		with open(temporary, "w") as handle:
			handle.write(content)
			handle.flush()
			os.fsync(handle.fileno())
		os.replace(temporary, path)
	except BaseException:
		try:
			os.remove(temporary)
		except OSError:
			pass
		raise


def _find_row(doc, manifest_lang: str):
	row = next((child for child in doc.audio_tracks if child.manifest_lang == manifest_lang), None)
	if row is None:
		frappe.throw(_("This video has no audio track {0}.").format(manifest_lang))
	return row


def _set_row(row, **values):
	"""Write a track row's state straight to the database.

	`modified` is deliberately bumped: `_fail_stuck_tracks` decides an import has
	lost its worker by how long the row has sat in `Processing`, so a row that
	never touched `modified` on entering that state would look stale from the
	moment it started and a concurrent sweep would fail a healthy import.
	"""
	frappe.db.set_value("LMS Video Audio Track", row.name, values, update_modified=True)
	row.update(values)
	frappe.db.commit()


def _row_summary(row) -> dict:
	return {
		"manifest_lang": row.manifest_lang,
		"label": row.label,
		"language": row.language or "",
		"status": row.status,
		"origin": row.origin,
	}


def publish_track_status(doc, row, progress: int = None, removed: str = None):
	"""Tell any open editor how an import is going.

	A channel of its own rather than `lms_video_status`: the parent video stays
	Ready throughout, and a player that saw a "Packaging" event would drop back
	to the progressive fallback mid-lesson for no reason.
	"""
	from frappe.realtime import get_website_room

	message = {"video_id": doc.video_id, "removed": removed}
	if row is not None:
		message.update(
			{
				"manifest_lang": row.manifest_lang,
				"status": row.status,
				"label": row.label,
				"error": row.error_log,
			}
		)
	if progress is not None:
		message["progress"] = progress

	frappe.publish_realtime(
		event="lms_video_track_status",
		room=get_website_room(),
		message=message,
	)
