import json
import os

import frappe
from frappe.utils import cint, flt

from lms.lms.video import paths


def execute():
	"""Restate every packaged video's duration as the length of its picture.

	`duration` used to be copied from ffprobe's container-level value, and a
	container is as long as its longest stream. A source carrying a dub that
	overruns the picture — a 156s Spanish track over a 119s lecture — therefore
	stored the dub's length as the video's.

	That number is what added audio tracks are aligned to and validated
	against, so leaving it wrong means `apad` writing audio past the last video
	segment, and the guard that rejects a mismatched upload measuring against
	a duration no part of the package has.

	The retained `probe.json` already carries per-stream durations, so this
	needs no re-probe and no ffprobe on the bench.
	"""
	videos = frappe.get_all(
		"LMS Video",
		filters={"status": "Ready"},
		fields=["name", "video_id", "is_private", "duration"],
	)

	for video in videos:
		duration = _video_stream_duration(video.video_id, bool(cint(video.is_private)))
		if not duration:
			# No probe kept, or a muxer that wrote no per-stream duration.
			# The stored value is the best available answer.
			continue

		if abs(duration - flt(video.duration)) < 0.001:
			continue

		frappe.db.set_value("LMS Video", video.name, "duration", duration, update_modified=False)


def _video_stream_duration(video_id: str, is_private: bool) -> float:
	if not video_id or not paths.is_valid_video_id(video_id):
		return 0.0

	probe_file = os.path.join(paths.video_dir(video_id, is_private=is_private), paths.PROBE_NAME)

	try:
		with open(probe_file) as handle:
			data = json.load(handle)
	except (OSError, ValueError):
		return 0.0

	for stream in data.get("streams") or []:
		if stream.get("codec_type") != "video":
			continue
		# Cover art is a "video" stream with no meaningful duration.
		if (stream.get("disposition") or {}).get("attached_pic"):
			continue
		return flt(stream.get("duration"))

	return 0.0
