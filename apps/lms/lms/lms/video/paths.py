# Copyright (c) 2026, FOSS United and contributors
# For license information, please see license.txt

"""On-disk layout and URL shapes for packaged videos.

A packaged video is a *folder*, not a file:

    files/videos/<video_id>/
        manifest.mpd
        poster.jpg
        probe.json
        video/init.mp4  video/1.m4s ...
        audio_<lang>/init.mp4  audio_<lang>/1.m4s ...
        source.<ext>

`video_id` is a 16-char random hex string, so the folder name never needs
sanitizing and is not guessable. Everything that turns a video_id into a path
goes through here, and every such path is re-validated against the video root
before it is opened — segment paths arrive from the browser.
"""

import os
import re

import frappe
from frappe.utils import get_files_path

VIDEO_ROOT = "videos"
TMP_DIRNAME = ".tmp"

#: Staging for audio tracks imported into an already-packaged video. A sibling
#: of the per-video staging folder rather than a child of it, so a full
#: repackage's `rmtree` of its own staging cannot destroy an in-flight import.
TRACK_TMP_DIRNAME = "tracks"

#: Source containers accepted for packaging.
VIDEO_EXTENSIONS = ("mp4", "mov", "mkv", "avi", "webm", "m4v", "mpeg", "mpg", "wmv", "flv", "3gp")

#: Containers accepted as the source of an audio track added to an existing
#: video. Video containers are accepted for this too — a translation vendor
#: usually returns a re-dubbed mp4, not a bare audio file — so the full set of
#: importable extensions is this plus VIDEO_EXTENSIONS.
AUDIO_EXTENSIONS = ("mp3", "m4a", "aac", "wav", "flac", "ogg", "oga", "opus", "wma", "mka")

#: `frappe.generate_hash` is `secrets.token_hex`, so ids are always lowercase hex.
VIDEO_ID_RE = re.compile(r"^[a-f0-9]{16}$")

#: A relative path inside a video folder: exactly one directory level, then a
#: filename. Matches what the packager emits ("video/1.m4s", "audio_eng/init.mp4")
#: and nothing else — no traversal, no nesting, no absolute paths.
SEGMENT_PATH_RE = re.compile(r"^[A-Za-z0-9_]{1,40}/[A-Za-z0-9_.-]{1,80}$")

MANIFEST_NAME = "manifest.mpd"
POSTER_NAME = "poster.jpg"
PROBE_NAME = "probe.json"

#: Throwaway manifest the packager writes when a single audio track is packaged
#: on its own. Read for its one AdaptationSet, then discarded — it never reaches
#: the live video folder.
TRACK_MANIFEST_NAME = "track.mpd"

#: Sub-folders the packager writes into, one per stream. Kept here because
#: SEGMENT_PATH_RE has to admit exactly these shapes and nothing else.
VIDEO_STREAM_DIR = "video"
AUDIO_STREAM_DIR_PREFIX = "audio_"


def new_video_id() -> str:
	return frappe.generate_hash(length=16)


def is_valid_video_id(video_id: str) -> bool:
	return isinstance(video_id, str) and bool(VIDEO_ID_RE.match(video_id))


def is_valid_segment_path(path: str) -> bool:
	return isinstance(path, str) and bool(SEGMENT_PATH_RE.match(path))


def video_dir(video_id: str, is_private: bool = True) -> str:
	"""Absolute path of a packaged video's folder."""
	if not is_valid_video_id(video_id):
		frappe.throw(frappe._("Invalid video id"))
	return get_files_path(VIDEO_ROOT, video_id, is_private=is_private)


def tmp_dir(video_id: str) -> str:
	"""Staging folder. Packaging always writes here and the finished folder is
	moved into place with a single rename, so a worker killed mid-encode can
	never leave a partial manifest that a student would try to load."""
	if not is_valid_video_id(video_id):
		frappe.throw(frappe._("Invalid video id"))
	return get_files_path(VIDEO_ROOT, TMP_DIRNAME, video_id, is_private=True)


def tmp_root() -> str:
	return get_files_path(VIDEO_ROOT, TMP_DIRNAME, is_private=True)


def track_tmp_root() -> str:
	return get_files_path(VIDEO_ROOT, TMP_DIRNAME, TRACK_TMP_DIRNAME, is_private=True)


def track_tmp_dir(video_id: str, operation: str) -> str:
	"""Staging folder for one audio-track import.

	Keyed by operation as well as video so two imports queued against the same
	video never share a directory, and so the folder left behind by a killed
	worker names the row that owns it.
	"""
	if not is_valid_video_id(video_id):
		frappe.throw(frappe._("Invalid video id"))
	if not re.match(r"^[A-Za-z0-9_-]{1,64}$", operation or ""):
		frappe.throw(frappe._("Invalid track operation id"))
	return os.path.join(track_tmp_root(), video_id, operation)


def resolve_inside(video_id: str, relative_path: str, is_private: bool = True) -> str:
	"""Absolute path of `relative_path` within a video folder, or throw.

	The regex above already rejects "..", but a symlink inside the folder could
	still point out of it, so the resolved realpath is checked for containment.
	This is the only function that turns browser-supplied text into a path to open.
	"""
	if not is_valid_segment_path(relative_path):
		frappe.throw(frappe._("Invalid segment path"))

	root = os.path.realpath(video_dir(video_id, is_private=is_private))
	target = os.path.realpath(os.path.join(root, relative_path))

	if target != root and not target.startswith(root + os.sep):
		frappe.throw(frappe._("Invalid segment path"))

	return target


def manifest_path(video_id: str, is_private: bool = True) -> str:
	return os.path.join(video_dir(video_id, is_private=is_private), MANIFEST_NAME)


def video_url(video_id: str, filename: str, is_private: bool = True) -> str:
	prefix = "/private/files" if is_private else "/files"
	return f"{prefix}/{VIDEO_ROOT}/{video_id}/{filename}"


def manifest_url(video_id: str, is_private: bool = True) -> str:
	return video_url(video_id, MANIFEST_NAME, is_private=is_private)


def poster_url(video_id: str, is_private: bool = True) -> str:
	return video_url(video_id, POSTER_NAME, is_private=is_private)


def _extension(file_url: str) -> str:
	return os.path.splitext(file_url.split("?")[0])[1].lstrip(".").lower()


def is_video_file(file_url: str) -> bool:
	"""Whether a File's url looks like a source video we should package."""
	if not file_url:
		return False
	return _extension(file_url) in VIDEO_EXTENSIONS


def is_audio_file(file_url: str) -> bool:
	"""Whether a File's url looks like an audio-only container."""
	if not file_url:
		return False
	return _extension(file_url) in AUDIO_EXTENSIONS


def is_importable_audio_source(file_url: str) -> bool:
	"""Whether audio can be imported out of this file into an existing package."""
	return is_audio_file(file_url) or is_video_file(file_url)


def is_packaged_url(url: str) -> bool:
	"""Whether a url points into a packaged video folder.

	Used to keep `rewrite_private_media` away from manifests: rewriting one to
	`serve_resource?file_url=...` would make the player resolve every relative
	segment path against `/api/method/...`.
	"""
	return bool(url) and f"/files/{VIDEO_ROOT}/" in url


def video_id_from_url(url: str) -> str | None:
	"""Extract the video id from any url inside a packaged video folder."""
	if not url:
		return None
	match = re.search(rf"/files/{VIDEO_ROOT}/([a-f0-9]{{16}})/", url)
	return match.group(1) if match else None
