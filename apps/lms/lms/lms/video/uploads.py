# Copyright (c) 2026, FOSS United and contributors
# For license information, please see license.txt

"""Turning an uploaded File into a packaging job.

Two entry points, both idempotent and both landing on `ensure_video_for_file`:

- the `File` `after_insert` hook, so any video reaching the site gets packaged
  regardless of which upload path produced it;
- the whitelisted lookup the editor calls straight after an upload, so the block
  learns its `video_id` without having to guess when the hook ran.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint

from lms.lms.video import paths, pipeline

#: Doctypes whose attachments are course media. Restricting to these keeps
#: unrelated video attachments (assignment submissions, chat uploads) out of a
#: queue where one job can occupy a worker for an hour.
VIDEO_HOST_DOCTYPES = ("Course Lesson", "LMS Course", "LMS Batch")


def on_file_insert(doc, method=None):
	"""`File` after_insert hook. Never raises — a packaging problem must not
	fail the upload the user just made."""
	try:
		if doc.attached_to_doctype not in VIDEO_HOST_DOCTYPES:
			return
		if not paths.is_video_file(doc.file_url):
			return
		if not cint(pipeline.get_video_settings().video_transcoding_enabled):
			return

		ensure_video_for_file(
			file_url=doc.file_url,
			title=doc.file_name,
			is_private=cint(doc.is_private),
			attached_to_doctype=doc.attached_to_doctype,
			attached_to_name=doc.attached_to_name,
			content_hash=doc.content_hash,
		)
	except Exception:
		frappe.log_error(title="LMS video packaging could not be queued", message=frappe.get_traceback())


@frappe.whitelist()
def ensure_video_for_file(
	file_url: str,
	title: str = None,
	is_private: int = None,
	attached_to_doctype: str = None,
	attached_to_name: str = None,
	content_hash: str = None,
) -> dict:
	"""Return the LMS Video for `file_url`, creating and queueing one if needed.

	Idempotent on `source_file_url`, which is also what gives us deduplication
	for free: Frappe's File doctype already collapses identical uploads onto one
	row and one url, so re-uploading the same lecture finds the package that was
	built the first time instead of transcoding it again.
	"""
	if not paths.is_video_file(file_url):
		frappe.throw(frappe._("{0} is not a video file.").format(file_url))

	existing = frappe.db.get_value(
		"LMS Video",
		{"source_file_url": file_url},
		["name", "video_id", "status"],
		as_dict=True,
	)
	if existing:
		# A previous attempt that failed is worth retrying — the cause is often a
		# missing binary or a full disk, both of which get fixed and then need a
		# nudge rather than a re-upload.
		if existing.status == "Failed":
			pipeline.enqueue_packaging(existing.name)
		return {"video_id": existing.video_id, "status": existing.status}

	if is_private is None:
		is_private = 1 if str(file_url).startswith("/private") else 0

	doc = frappe.get_doc(
		{
			"doctype": "LMS Video",
			"title": title or file_url.rsplit("/", 1)[-1],
			"source_file_url": file_url,
			"is_private": cint(is_private),
			"content_hash": content_hash,
			"attached_to_doctype": attached_to_doctype,
			"attached_to_name": attached_to_name,
			"status": "Pending",
		}
	)
	doc.insert(ignore_permissions=True)

	pipeline.enqueue_packaging(doc.name)
	return {"video_id": doc.video_id, "status": doc.status}


@frappe.whitelist()
def retry_packaging(video_id: str) -> dict:
	"""Re-run packaging for a video, from the editor's failure state."""
	from lms.lms.video.api import _assert_can_edit, _get_video

	doc = _get_video(video_id)
	_assert_can_edit(doc)

	frappe.db.set_value("LMS Video", doc.name, {"status": "Pending", "error_log": ""})
	pipeline.enqueue_packaging(doc.name)
	return {"video_id": video_id, "status": "Pending"}
