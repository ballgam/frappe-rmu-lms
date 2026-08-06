import base64
import os

import frappe

from lms.lms.test_helpers import BaseTestUtils
from lms.lms.utils import validate_image

# 1x1 transparent GIF — small enough to inline, real enough for File's image handling.
_PIXEL = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


class TestValidateImage(BaseTestUtils):
	"""Regression: a course image made public must actually move to public/files.

	validate_image used to flip is_private with frappe.db.set_value, which skips
	File.handle_is_private_changed. The bytes stayed in private/files while the
	course rendered <img src="/files/..."> — every cover image 404'd.
	"""

	def _private_image(self):
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"cover_{frappe.generate_hash(length=6)}.gif",
				"is_private": 1,
				"content": base64.b64encode(_PIXEL).decode(),
				"decode": True,
			}
		).insert(ignore_permissions=True)
		self.cleanup_items.append(("File", file.name))
		return file

	def test_returns_public_url(self):
		file = self._private_image()
		self.assertTrue(file.file_url.startswith("/private/files/"))

		self.assertEqual(validate_image(file.file_url), file.file_url.replace("/private", "", 1))

	def test_moves_file_to_public_directory(self):
		file = self._private_image()
		# frappe appends a hash to the stored name, so read it off the url.
		name_on_disk = file.file_url.rsplit("/", 1)[-1]
		validate_image(file.file_url)

		self.assertFalse(os.path.exists(frappe.get_site_path("private", "files", name_on_disk)))
		self.assertTrue(os.path.exists(frappe.get_site_path("public", "files", name_on_disk)))

	def test_file_doc_is_left_consistent(self):
		file = self._private_image()
		public_url = validate_image(file.file_url)

		row = frappe.db.get_value("File", file.name, ["is_private", "file_url"], as_dict=True)
		self.assertEqual(row.is_private, 0)
		self.assertEqual(row.file_url, public_url)

	def test_public_and_empty_paths_pass_through(self):
		self.assertEqual(validate_image("/files/already-public.png"), "/files/already-public.png")
		self.assertEqual(validate_image(""), "")
		self.assertIsNone(validate_image(None))

	def test_unknown_private_path_is_returned_unchanged(self):
		"""No File row to move — don't hand back a url that would 404."""
		orphan = "/private/files/never-uploaded.png"
		self.assertEqual(validate_image(orphan), orphan)
