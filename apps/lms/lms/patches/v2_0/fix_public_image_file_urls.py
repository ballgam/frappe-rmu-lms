import os

import frappe

# Doc fields that pass through lms.lms.utils.validate_image on save.
IMAGE_FIELDS = (
	("LMS Course", "image"),
	("Job Opportunity", "company_logo"),
)


def execute():
	"""Move images that `validate_image` marked public but never moved on disk.

	The old `validate_image` wrote `is_private = 0` with `frappe.db.set_value`,
	which skips the File document lifecycle: the bytes stayed in private/files
	and `file_url` kept its /private prefix, while LMS Course.image and
	Job Opportunity.company_logo were rewritten to /files/... and 404'd.
	"""
	_publish_stranded_files()
	_repair_references()


def _publish_stranded_files():
	"""The corrupt rows are those claiming to be public while still pointing
	at a private path. Saving the doc runs handle_is_private_changed, which
	moves the file and rewrites file_url."""
	names = frappe.get_all(
		"File",
		filters={"is_private": 0, "file_url": ["like", "/private/files/%"]},
		pluck="name",
	)

	for name in names:
		file = frappe.get_doc("File", name)
		# Put the column back in sync with disk so the save below is seen as a
		# real is_private change. db_set keeps the loaded doc and the row in
		# step; a bare frappe.db.set_value would leave the cached doc claiming
		# to be public and the save would be a no-op.
		file.db_set("is_private", 1, update_modified=False)
		file.is_private = 0
		try:
			file.save(ignore_permissions=True)
		except (FileNotFoundError, FileExistsError) as e:
			frappe.db.rollback()
			frappe.log_error(title="Could not make file public", message=f"{name}: {e}")
		else:
			frappe.db.commit()


def _repair_references():
	"""Point image fields at a url that is actually served.

	Beyond the /private rewrite, File.save dedupes rows sharing a content hash
	onto one file_url, so a doc can be left holding the url of a duplicate
	upload whose bytes were never moved.
	"""
	for doctype, fieldname in IMAGE_FIELDS:
		rows = frappe.get_all(
			doctype,
			filters={fieldname: ["like", "/files/%"]},
			fields=["name", fieldname],
		)
		for row in rows:
			url = row.get(fieldname)
			served = _served_url(url)
			if served and served != url:
				frappe.db.set_value(doctype, row.name, fieldname, served, update_modified=False)

	frappe.db.commit()


def _served_url(url: str) -> str | None:
	"""The url the browser can actually fetch this image from, or None."""
	basename = url.rsplit("/", 1)[-1]
	if os.path.exists(frappe.get_site_path("public", "files", basename)):
		return url

	# Look the file up the way it may still be recorded: by its old public url,
	# by the private url it was uploaded under, then by name.
	for filters in ({"file_url": url}, {"file_url": f"/private{url}"}, {"file_name": basename}):
		current = frappe.db.get_value("File", filters, "file_url")
		if not current or current.startswith("/private/"):
			continue
		if os.path.exists(frappe.get_site_path("public", "files", current.rsplit("/", 1)[-1])):
			return current

	return None
