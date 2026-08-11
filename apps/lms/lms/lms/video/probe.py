# Copyright (c) 2026, FOSS United and contributors
# For license information, please see license.txt

"""Reading an ffprobe report and deciding what ffmpeg should do with it.

Everything here is pure: it takes parsed ffprobe JSON and returns dataclasses
and argv lists. No frappe, no subprocess, no filesystem — so the interesting
decisions (stream-copy vs re-encode, language assignment) are unit-testable
without a site.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Profiles the browser baseline (and Shaka's MSE path) can be relied on to decode.
COPYABLE_H264_PROFILES = {"baseline", "constrained baseline", "main", "high"}

#: The one pixel format that is universally safe. 10-bit / 4:2:2 sources get
#: re-encoded down to it.
TARGET_PIX_FMT = "yuv420p"

#: ffprobe reports these when the source is interlaced; they need deinterlacing
#: because H.264 in fMP4 for browser playback is expected to be progressive.
INTERLACED_FIELD_ORDERS = {"tt", "bb", "tb", "bt"}

#: Missing / meaningless language tags. Anything here gets a synthetic code.
UNKNOWN_LANGUAGES = {"", "und", "unk", "none", "null", "mis", "zxx"}

DEFAULT_AUDIO_BITRATE = "128k"
DEFAULT_AUDIO_CHANNELS = 2
DEFAULT_CRF = 21
DEFAULT_PRESET = "medium"

#: A track added to an existing package must run the length of the video it
#: joins, or the manifest's duration stops describing it. Anything inside this
#: is rounding and is left alone; anything past it up to the tolerance below is
#: padded or trimmed to fit; anything beyond that is the wrong file.
DURATION_EPSILON = 0.5
DURATION_TOLERANCE_RATIO = 0.02
DURATION_TOLERANCE_FLOOR = 5.0


@dataclass
class VideoStream:
	index: int
	codec_name: str = ""
	profile: str = ""
	pix_fmt: str = ""
	field_order: str = ""
	width: int = 0
	height: int = 0
	rotation: int = 0
	avg_frame_rate: float = 0.0
	#: 0.0 when the container reports no per-stream duration.
	duration: float = 0.0


@dataclass
class AudioStream:
	index: int
	codec_name: str = ""
	profile: str = ""
	channels: int = 0
	sample_rate: int = 0
	detected_language: str = "und"
	title: str = ""
	is_default: bool = False
	#: Assigned by `assign_manifest_langs`; the stable key baked into the MPD.
	manifest_lang: str = ""


@dataclass
class MediaInfo:
	duration: float = 0.0
	format_name: str = ""
	video: VideoStream | None = None
	audios: list[AudioStream] = field(default_factory=list)

	@property
	def has_video(self) -> bool:
		return self.video is not None

	@property
	def has_audio(self) -> bool:
		return bool(self.audios)

	@property
	def playable_duration(self) -> float:
		"""How long the picture runs, which is what the package will be.

		`duration` is the container's, and a container is as long as its
		longest stream — so a source carrying a dub that overruns the picture
		reports that dub's length. Storing that would leave the video's
		duration describing an audio track: imported tracks would be padded
		with `apad` past the last video segment, and the guard that rejects
		the wrong upload would be measuring against the wrong number.

		Falls back to the container for audio-only sources and for muxers that
		write no per-stream duration.
		"""
		if self.video and self.video.duration > 0:
			return self.video.duration
		return self.duration


def _to_float(value, default=0.0) -> float:
	try:
		return float(value)
	except (TypeError, ValueError):
		return default


def _to_int(value, default=0) -> int:
	try:
		return int(value)
	except (TypeError, ValueError):
		return default


def _parse_frame_rate(value) -> float:
	"""ffprobe frame rates are rationals like '30000/1001'; '0/0' means unknown."""
	if not value or not isinstance(value, str) or "/" not in value:
		return _to_float(value)
	num, _, den = value.partition("/")
	den_value = _to_float(den)
	if not den_value:
		return 0.0
	return _to_float(num) / den_value


def _parse_rotation(stream: dict) -> int:
	"""Display rotation in degrees clockwise, normalized to [0, 360).

	Two encodings exist. Modern ffprobe puts a Display Matrix in `side_data_list`
	whose `rotation` is the *counter*-clockwise angle (a portrait phone clip
	reports -90); older builds put a clockwise `tags.rotate`. Normalize both to
	clockwise-for-display.
	"""
	for side_data in stream.get("side_data_list") or []:
		if side_data.get("side_data_type") == "Display Matrix" and "rotation" in side_data:
			return int(round(-_to_float(side_data["rotation"]))) % 360

	tags = stream.get("tags") or {}
	if "rotate" in tags:
		return int(round(_to_float(tags["rotate"]))) % 360

	return 0


def parse_probe(data: dict) -> MediaInfo:
	"""Turn `ffprobe -show_streams -show_format` JSON into a MediaInfo.

	Only the first video stream is kept — the pipeline packages a single video
	rendition. Every audio stream is kept; that is the whole point of the feature.
	Attached cover art (mjpeg/png "video" streams) is skipped so an MP3-with-artwork
	is not mistaken for a video.
	"""
	info = MediaInfo()
	fmt = data.get("format") or {}
	info.duration = _to_float(fmt.get("duration"))
	info.format_name = fmt.get("format_name") or ""

	for stream in data.get("streams") or []:
		codec_type = stream.get("codec_type")
		tags = stream.get("tags") or {}
		disposition = stream.get("disposition") or {}

		if codec_type == "video":
			if disposition.get("attached_pic"):
				continue
			if info.video is not None:
				continue
			info.video = VideoStream(
				index=_to_int(stream.get("index")),
				codec_name=(stream.get("codec_name") or "").lower(),
				profile=(stream.get("profile") or "").lower(),
				pix_fmt=(stream.get("pix_fmt") or "").lower(),
				field_order=(stream.get("field_order") or "").lower(),
				width=_to_int(stream.get("width")),
				height=_to_int(stream.get("height")),
				rotation=_parse_rotation(stream),
				avg_frame_rate=_parse_frame_rate(stream.get("avg_frame_rate")),
				duration=_to_float(stream.get("duration")),
			)

		elif codec_type == "audio":
			info.audios.append(
				AudioStream(
					index=_to_int(stream.get("index")),
					codec_name=(stream.get("codec_name") or "").lower(),
					profile=(stream.get("profile") or "").lower(),
					channels=_to_int(stream.get("channels")),
					sample_rate=_to_int(stream.get("sample_rate")),
					detected_language=(tags.get("language") or "und").strip().lower(),
					title=(tags.get("title") or "").strip(),
					is_default=bool(disposition.get("default")),
				)
			)

	if info.duration <= 0:
		# Some containers (MKV from certain muxers) carry no format-level duration.
		info.duration = _to_float((fmt.get("tags") or {}).get("DURATION"))

	return info


def private_use_codes():
	"""ISO 639-2 private-use range, qaa..qtz — 520 codes, generated in order.

	Reserved by the standard for local use, so a synthetic code can never
	collide with a real language a source might legitimately declare.
	"""
	for second in "abcdefghijklmnopqrst":
		for third in "abcdefghijklmnopqrstuvwxyz":
			yield f"q{second}{third}"


def assign_manifest_langs(audios: list[AudioStream]) -> list[AudioStream]:
	"""Give every audio stream a unique `manifest_lang`.

	This is what makes the audio menu work at all. A DASH AdaptationSet is
	identified by its `lang`, and MP4/MOV exports almost never carry per-track
	language tags — so without this, a two-language lecture packages as two
	AdaptationSets both claiming `und` and every player collapses them into one
	entry.

	A usable detected tag is kept (so `eng`/`som` stay meaningful in the manifest
	and to any external tool). Anything unknown, or a duplicate of a code already
	taken, falls through to the next private-use code.

	The result is baked into the MPD and never changes. Display names live in
	`LMS Video Audio Track.label`, keyed on this code — which is why an instructor
	renaming a track is a database update rather than a re-encode.
	"""
	used: set[str] = set()

	for audio in audios:
		audio.manifest_lang = assign_manifest_lang(audio.detected_language, used)
		used.add(audio.manifest_lang)

	return audios


def assign_manifest_lang(detected: str, used: set[str]) -> str:
	"""Pick a `manifest_lang` for one stream, avoiding everything in `used`.

	Split out of `assign_manifest_langs` so a track imported into an existing
	package — months after the original upload — can reserve a code against the
	ones the live manifest already carries.
	"""
	code = (detected or "").strip().lower()
	if code not in UNKNOWN_LANGUAGES and code not in used and 2 <= len(code) <= 3:
		return code

	for candidate in private_use_codes():
		if candidate not in used:
			return candidate

	raise ValueError("ran out of private-use language codes")


def default_track_label(audio: AudioStream, position: int) -> str:
	"""Best label we can offer before an instructor reviews the tracks."""
	if audio.title:
		return audio.title
	detected = (audio.detected_language or "").strip().lower()
	if detected not in UNKNOWN_LANGUAGES:
		return detected.upper()
	return f"Audio {position}"


def needs_video_reencode(video: VideoStream, keyframe_gap: float | None, segment_duration: float) -> str:
	"""Why the video stream cannot be stream-copied, or "" if it can be.

	Returning the *reason* rather than a bool keeps the decision debuggable from
	the LMS Video error log, and makes the unit tests assert on intent.
	"""
	if video.codec_name != "h264":
		return f"source video codec is {video.codec_name or 'unknown'}, not h264"
	if video.profile not in COPYABLE_H264_PROFILES:
		return f"h264 profile {video.profile or 'unknown'} is not broadly decodable"
	if video.pix_fmt != TARGET_PIX_FMT:
		return f"pixel format {video.pix_fmt or 'unknown'} is not {TARGET_PIX_FMT}"
	if video.field_order in INTERLACED_FIELD_ORDERS:
		return f"source is interlaced ({video.field_order})"
	if video.rotation:
		# A copy keeps the rotation matrix, and Shaka Packager drops it when it
		# rewrites the container — the result plays sideways. Re-encoding lets
		# ffmpeg's autorotate bake the rotation into the pixels instead.
		return f"source carries a {video.rotation}deg rotation matrix"
	if keyframe_gap is not None and keyframe_gap > segment_duration * 1.5:
		# The packager can only cut a segment at a keyframe. Copying a source
		# whose GOP is much longer than the target segment gives long, uneven
		# segments and coarse seeking.
		return f"keyframes are up to {keyframe_gap:.1f}s apart, target segment is {segment_duration}s"
	return ""


def needs_audio_reencode(audio: AudioStream) -> str:
	"""Why an audio stream cannot be stream-copied, or "" if it can be."""
	if audio.codec_name != "aac":
		return f"source audio codec is {audio.codec_name or 'unknown'}, not aac"
	if audio.profile and audio.profile not in ("lc", "aac-lc"):
		# HE-AAC/xHE-AAC signal differently in DASH and are patchily supported.
		return f"aac profile {audio.profile} is not LC"
	if audio.channels > DEFAULT_AUDIO_CHANNELS:
		return f"{audio.channels} channels, downmixing to stereo"
	return ""


def build_video_args(video: VideoStream, segment_duration: float, reason: str, fps_flag: str) -> list[str]:
	"""ffmpeg output args for the single video rendition."""
	if not reason:
		return ["-c:v", "copy"]

	fps = video.avg_frame_rate or 30.0
	# Keyframe every `segment_duration` seconds, with scene-cut detection off, so
	# the packager can cut exactly on the target boundary every time.
	gop = max(1, int(round(fps * segment_duration)))

	args = [
		"-c:v", "libx264",
		"-crf", str(DEFAULT_CRF),
		"-preset", DEFAULT_PRESET,
		"-pix_fmt", TARGET_PIX_FMT,
		"-profile:v", "high",
		"-g", str(gop),
		"-keyint_min", str(gop),
		"-sc_threshold", "0",
		# Constant frame rate: variable-frame-rate sources (screen recordings,
		# phone slow-mo) otherwise produce segments whose real duration drifts
		# from the manifest's, and seeking desyncs from the audio.
		fps_flag, "cfr",
	]

	if video.field_order in INTERLACED_FIELD_ORDERS:
		args += ["-vf", "yadif"]

	return args


def build_audio_args(audio: AudioStream, reason: str) -> list[str]:
	"""ffmpeg output args for one audio rendition."""
	if not reason:
		return ["-c:a", "copy"]
	return [
		"-c:a", "aac",
		"-b:a", DEFAULT_AUDIO_BITRATE,
		"-ac", str(min(audio.channels or DEFAULT_AUDIO_CHANNELS, DEFAULT_AUDIO_CHANNELS)),
		"-ar", "48000",
	]


def duration_tolerance(target: float) -> float:
	"""How far an imported track may be from the video's length and still be it.

	Proportional, because two seconds adrift on a 90-second clip is a different
	file while two seconds adrift on a two-hour lecture is a trailing silence
	the editor trimmed.
	"""
	return max(DURATION_TOLERANCE_FLOOR, abs(target) * DURATION_TOLERANCE_RATIO)


def needs_duration_alignment(source: float, target: float) -> bool:
	"""Whether an imported track has to be padded or trimmed to fit the video."""
	if not target or not source:
		return False
	return abs(source - target) > DURATION_EPSILON


def duration_mismatch_reason(source: float, target: float) -> str:
	"""Why this file cannot be the audio for a video of `target` seconds, or "".

	Rejecting rather than padding a wildly wrong length is the point: silently
	appending fifty minutes of silence to a forty-minute file turns "you picked
	the wrong upload" into a translation that mysteriously stops half way.
	"""
	if not target:
		return ""
	if not source:
		return "the uploaded file reports no duration"

	drift = abs(source - target)
	tolerance = duration_tolerance(target)
	if drift <= tolerance:
		return ""

	return (
		f"the uploaded audio is {source:.1f}s long but the video is {target:.1f}s "
		f"({drift:.1f}s apart, at most {tolerance:.1f}s allowed)"
	)


def build_audio_align_args(target_duration: float) -> list[str]:
	"""Pad with silence / cut to exactly `target_duration`.

	`apad` alone would run forever; it is `-t` that ends the output, and the pair
	together mean "however long this file is, make it exactly that". Being a
	filter, it rules out a stream copy — which is why callers force a re-encode
	reason whenever alignment is on.
	"""
	return ["-af", "apad", "-t", f"{target_duration:.3f}"]
