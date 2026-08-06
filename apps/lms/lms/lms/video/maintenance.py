# Copyright (c) 2026, FOSS United and contributors
# For license information, please see license.txt

"""Backfilling existing lesson videos, and cleaning up after crashed jobs."""

from __future__ import annotations

import os
import shutil
import time

import frappe
from frappe.utils import add_to_date, now_datetime

from lms.lms.video import paths

#: A job still claiming to be running after this long has lost its worker —
#: RQ's own timeout is SUBPROCESS_TIMEOUT (6h), so this leaves a wide margin.
STALE_JOB_HOURS = 8

#: Staging folders are deleted by the job's own `finally`; anything older than
#: this outlived the process that owned it.
STALE_STAGING_HOURS = 12


def find_lesson_videos(lesson: str = None) -> list[dict]:
	"""Every video referenced by an upload block in lesson content.

	Reads the blocks rather than the File table because a lesson's authoritative
	list of media is what its content embeds — files get attached, detached and
	re-uploaded, but the block is what actually plays.
	"""
	from lms.lms.utils import get_editorjs_blocks

	filters = {"name": lesson} if lesson else {}
	found: dict[str, dict] = {}

	for row in frappe.get_all("Course Lesson", filters=filters, fields=["name", "content"]):
		for block in get_editorjs_blocks(row.content):
			if block.get("type") != "upload":
				continue
			data = block.get("data") or {}
			file_url = data.get("file_url")
			if not file_url or not paths.is_video_file(file_url):
				continue
			# Same file embedded in several lessons is still one video.
			found.setdefault(file_url, {"file_url": file_url, "lesson": row.name})

	return list(found.values())


def find_unpackaged_lesson_videos(lesson: str = None, include_failed: bool = False) -> list[dict]:
	"""Lesson videos with no usable package yet."""
	candidates = find_lesson_videos(lesson)
	if not candidates:
		return []

	statuses = {
		row.source_file_url: row.status
		for row in frappe.get_all(
			"LMS Video",
			filters={"source_file_url": ["in", [c["file_url"] for c in candidates]]},
			fields=["source_file_url", "status"],
		)
	}

	pending = []
	for candidate in candidates:
		status = statuses.get(candidate["file_url"])
		if status == "Ready":
			continue
		if status in ("Pending", "Probing", "Packaging"):
			continue
		if status == "Failed" and not include_failed:
			continue
		pending.append({**candidate, "status": status})

	return pending


def backfill_lesson_videos(limit: int = None, lesson: str = None, include_failed: bool = False) -> list[str]:
	"""Queue packaging for existing lesson videos. Returns the queued file urls.

	Deliberately manual and batched: one worker packaging every video on a large
	site would monopolise the `long` queue, which also carries course progress
	recalculation and course import/export.
	"""
	from lms.lms.video.uploads import ensure_video_for_file

	pending = find_unpackaged_lesson_videos(lesson=lesson, include_failed=include_failed)
	if limit:
		pending = pending[: int(limit)]

	queued = []
	for candidate in pending:
		file_url = candidate["file_url"]
		file_row = frappe.db.get_value(
			"File",
			{"file_url": file_url},
			["file_name", "is_private", "content_hash", "attached_to_doctype", "attached_to_name"],
			as_dict=True,
		) or frappe._dict()

		try:
			ensure_video_for_file(
				file_url=file_url,
				title=file_row.file_name,
				is_private=file_row.is_private if file_row.is_private is not None else None,
				attached_to_doctype=file_row.attached_to_doctype or "Course Lesson",
				attached_to_name=file_row.attached_to_name or candidate.get("lesson"),
				content_hash=file_row.content_hash,
			)
			queued.append(file_url)
		except Exception:
			frappe.logger("lms").warning(f"Could not queue {file_url} for packaging", exc_info=True)

	frappe.db.commit()
	return queued


def sweep_stale_packaging():
	"""Daily cleanup of work abandoned by a crashed or killed worker.

	Two kinds of debris: docs that still claim to be mid-encode, and staging
	folders whose job never reached its `finally`. Both are invisible to users
	but the folders hold a full copy of every video that was being processed.
	"""
	_fail_stuck_videos()
	_remove_stale_staging()


def _fail_stuck_videos():
	cutoff = add_to_date(now_datetime(), hours=-STALE_JOB_HOURS)
	stuck = frappe.get_all(
		"LMS Video",
		filters={"status": ["in", ("Pending", "Probing", "Packaging")], "modified": ["<", cutoff]},
		pluck="name",
	)
	for name in stuck:
		frappe.db.set_value(
			"LMS Video",
			name,
			{
				"status": "Failed",
				"error_log": frappe._(
					"Packaging did not finish. The worker handling it stopped before completing "
					"(the site may have been restarted, or the job ran out of memory). Retry from the lesson editor."
				),
			},
		)
		frappe.logger("lms").warning(f"Marked stale LMS Video {name} as Failed")

	if stuck:
		frappe.db.commit()


def _remove_stale_staging():
	root = paths.tmp_root()
	if not os.path.isdir(root):
		return

	cutoff = time.time() - STALE_STAGING_HOURS * 3600
	for entry in os.listdir(root):
		folder = os.path.join(root, entry)
		try:
			if not os.path.isdir(folder) or os.path.getmtime(folder) > cutoff:
				continue
		except OSError:
			continue

		shutil.rmtree(folder, ignore_errors=True)
		frappe.logger("lms").info(f"Removed stale video staging folder {entry}")
