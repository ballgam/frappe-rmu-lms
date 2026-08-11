import json
import os
import shutil
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase as UnitTestCase

from lms.lms.test_helpers import BaseTestUtils
from lms.lms.video import api, audio_tracks, paths, pipeline, tokens

# The same shape the packager writes for this fixture's two tracks, kept in one
# place rather than copied.
from lms.tests.test_video_manifest import TWO_TRACK_MANIFEST


class TestVideoAccess(BaseTestUtils, UnitTestCase):
	"""Who can reach a private lesson video's manifest and segments.

	A packaged video is hundreds of files that never appear in any lesson's
	content, so they cannot be gated the way `serve_resource` gates an ordinary
	upload. Instead the lesson gate runs once, in `get_playback_info`, and mints a
	token that authorizes the segment requests that follow. These tests pin the
	properties that split relies on: the gate really runs, and the token is
	useless to anyone it was not issued to.

	Packaging itself is not exercised here (it needs ffmpeg and Shaka Packager);
	the LMS Video row is written directly in the Ready state.
	"""

	def setUp(self):
		super().setUp()
		h = frappe.generate_hash(length=6)
		self.instructor = self._create_user(
			f"vid-instr-{h}@example.com", "Ada", "Instr", ["Course Creator", "Moderator"]
		)
		self.student = self._create_user(f"vid-stud-{h}@example.com", "Sam", "Student", ["LMS Student"])
		self.outsider = self._create_user(f"vid-out-{h}@example.com", "Otto", "Outsider", ["LMS Student"])

		self.course = self._create_course(title=f"Video Course {h}", instructor=self.instructor.email)
		self.chapter = self._create_chapter(f"Chapter {h}", self.course.name)
		self.lesson = self._create_lesson(f"Lesson {h}", self.chapter.name, self.course.name)
		self._create_chapter_reference(self.course.name, self.chapter.name, idx=1)
		self._create_lesson_reference(self.chapter.name, self.lesson.name)
		self._create_enrollment(self.student.email, self.course.name)

		self.file_url = f"/private/files/lecture_{h}.mp4"
		self.lesson.content = json.dumps(
			{"blocks": [{"type": "upload", "data": {"file_url": self.file_url, "file_type": "mp4"}}]}
		)
		self.lesson.save(ignore_permissions=True)

		self.video = frappe.get_doc(
			{
				"doctype": "LMS Video",
				"title": "lecture.mp4",
				"source_file_url": self.file_url,
				"is_private": 1,
				"status": "Ready",
				"duration": 118.8,
				"manifest_url": None,
				"audio_tracks": [
					{
						"manifest_lang": "en",
						"segment_dir": "audio_eng",
						"label": "English",
						"language": "eng",
						"is_default": 1,
						"origin": "Source File",
						"status": "Ready",
					},
					{
						"manifest_lang": "so",
						"segment_dir": "audio_som",
						"label": "Somali",
						"language": "som",
						"is_default": 0,
						"origin": "Source File",
						"status": "Ready",
					},
				],
			}
		).insert(ignore_permissions=True)
		self.video.db_set("manifest_url", paths.manifest_url(self.video.video_id, is_private=True))
		self.cleanup_items.append(("LMS Video", self.video.name))
		self.video_id = self.video.video_id
		self._write_manifest()
		frappe.db.commit()

	def _write_manifest(self):
		"""Put a real MPD on disk for the fixture's two tracks.

		Anything that decides whether a track is really published asks the
		manifest rather than the rows, so without this every row looks
		unpublished and the guards keyed on that never engage.
		"""
		self.video_folder = paths.video_dir(self.video_id, is_private=True)
		os.makedirs(self.video_folder, exist_ok=True)
		with open(paths.manifest_path(self.video_id, is_private=True), "w") as handle:
			handle.write(TWO_TRACK_MANIFEST)

	def tearDown(self):
		frappe.set_user("Administrator")
		shutil.rmtree(getattr(self, "video_folder", ""), ignore_errors=True)
		super().tearDown()

	# --- the gate ---------------------------------------------------------

	def test_enrolled_student_gets_playback_info_and_a_token(self):
		frappe.set_user(self.student.email)
		info = api.get_playback_info(file_url=self.file_url)

		self.assertEqual(info["status"], "Ready")
		self.assertTrue(info["token"])
		self.assertIn(api.MANIFEST_ENDPOINT, info["manifest_url"])
		self.assertEqual([t["label"] for t in info["audio_tracks"]], ["English", "Somali"])

	def test_non_enrolled_user_is_denied(self):
		frappe.set_user(self.outsider.email)
		with self.assertRaises(frappe.PermissionError):
			api.get_playback_info(file_url=self.file_url)

	def test_guest_is_denied_on_a_non_preview_lesson(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			api.get_playback_info(file_url=self.file_url)

	def test_video_not_referenced_by_any_lesson_is_denied(self):
		"""Fail closed: a package nothing embeds has no lesson to authorize it."""
		orphan = frappe.get_doc(
			{
				"doctype": "LMS Video",
				"title": "orphan.mp4",
				"source_file_url": "/private/files/orphan_video.mp4",
				"is_private": 1,
				"status": "Ready",
			}
		).insert(ignore_permissions=True)
		self.cleanup_items.append(("LMS Video", orphan.name))
		frappe.db.commit()

		frappe.set_user(self.student.email)
		with self.assertRaises(frappe.PermissionError):
			api.get_playback_info(video_id=orphan.video_id)

	# --- the token --------------------------------------------------------

	def test_token_issued_to_one_user_is_useless_to_another(self):
		frappe.set_user(self.student.email)
		token = api.get_playback_info(file_url=self.file_url)["token"]

		frappe.set_user(self.outsider.email)
		with self.assertRaises(frappe.PermissionError):
			api._verify_token(self.video_id, token)

	def test_token_issued_for_one_video_is_useless_for_another(self):
		frappe.set_user(self.student.email)
		token = api.get_playback_info(file_url=self.file_url)["token"]

		with self.assertRaises(frappe.PermissionError):
			api._verify_token("f" * 16, token)

	def test_expired_token_is_rejected(self):
		frappe.set_user(self.student.email)
		expired = tokens.mint(self.video_id, self.student.email, api._signing_key(), ttl_hours=-1)

		with self.assertRaises(frappe.PermissionError):
			api._verify_token(self.video_id, expired)

	def test_malformed_tokens_are_rejected(self):
		frappe.set_user(self.student.email)
		for bad in ("", None, "garbage", "a.b.c"):
			with self.assertRaises(frappe.PermissionError):
				api._verify_token(self.video_id, bad)

	# --- path safety ------------------------------------------------------

	def test_segment_paths_cannot_escape_the_video_folder(self):
		for bad in (
			"../../../../site_config.json",
			"video/../../../site_config.json",
			"/etc/passwd",
			"video/1.m4s;rm -rf /",
			"..%2f..%2fsite_config.json",
			"a/b/c.m4s",
		):
			with self.assertRaises(Exception, msg=f"{bad!r} was not rejected"):
				paths.resolve_inside(self.video_id, bad)

	def test_a_normal_segment_path_is_accepted(self):
		resolved = paths.resolve_inside(self.video_id, "video/1.m4s")
		self.assertTrue(
			resolved.startswith(os.path.realpath(paths.video_dir(self.video_id, is_private=True)))
		)

	def test_invalid_video_ids_are_rejected(self):
		for bad in ("../etc", "ZZZZ", "a" * 32, ""):
			self.assertFalse(paths.is_valid_video_id(bad), f"{bad!r} was accepted")

	# --- authoring --------------------------------------------------------

	def test_students_cannot_rename_audio_tracks(self):
		frappe.set_user(self.student.email)
		with self.assertRaises(frappe.PermissionError):
			api.update_audio_tracks(self.video_id, [{"manifest_lang": "en", "label": "Hacked"}])

	def test_instructor_can_rename_audio_tracks_without_repackaging(self):
		"""The whole point of keeping labels out of the manifest: renaming a track
		is a database write, not a re-encode."""
		frappe.set_user(self.instructor.email)
		result = api.update_audio_tracks(
			self.video_id,
			[{"manifest_lang": "so", "label": "Somali narration", "language": "som", "is_default": 0}],
		)

		labels = {t["manifest_lang"]: t["label"] for t in result["audio_tracks"]}
		self.assertEqual(labels["so"], "Somali narration")
		# The join key is untouched, so the manifest on disk stays valid.
		self.assertEqual(sorted(labels), ["en", "so"])

	# --- adding and removing tracks ---------------------------------------

	def test_students_cannot_add_an_audio_track(self):
		frappe.set_user(self.student.email)
		with self.assertRaises(frappe.PermissionError):
			audio_tracks.add_audio_track(self.video_id, "/private/files/dub.mp3", label="Hacked")

	def test_students_cannot_remove_an_audio_track(self):
		frappe.set_user(self.student.email)
		with self.assertRaises(frappe.PermissionError):
			audio_tracks.remove_audio_track(self.video_id, "so")

	def test_students_cannot_read_the_authoring_track_list(self):
		"""It carries the source file urls and error logs of every import."""
		frappe.set_user(self.student.email)
		with self.assertRaises(frappe.PermissionError):
			api.list_audio_tracks(self.video_id)

	def test_an_outsider_cannot_add_a_track(self):
		frappe.set_user(self.outsider.email)
		with self.assertRaises(frappe.PermissionError):
			audio_tracks.add_audio_track(self.video_id, "/private/files/dub.mp3")

	def test_a_file_outside_the_files_directory_is_refused(self):
		"""The upload url is browser-supplied, so it is the one input that could
		point the importer at something it has no business reading."""
		frappe.set_user(self.instructor.email)
		for bad in ("/private/files/../../site_config.json", "/etc/passwd.mp3"):
			with self.assertRaises(Exception, msg=f"{bad!r} was not rejected"):
				audio_tracks.add_audio_track(self.video_id, bad)

	def test_a_file_that_is_neither_audio_nor_video_is_refused(self):
		frappe.set_user(self.instructor.email)
		with self.assertRaises(frappe.ValidationError):
			audio_tracks.add_audio_track(self.video_id, "/private/files/notes.pdf")

	def test_a_failed_preflight_does_not_create_a_pending_track(self):
		"""A stopped Docker daemon is an environment error, not a failed import."""
		frappe.set_user(self.instructor.email)
		before = len(frappe.get_doc("LMS Video", self.video.name).audio_tracks)
		probe_output = {
			"format": {"duration": "118.8"},
			"streams": [{"index": 0, "codec_type": "audio", "codec_name": "aac", "channels": 2}],
		}

		with (
			patch.object(pipeline, "absolute_file_path", return_value="/tmp/dub.mp3"),
			patch.object(pipeline, "run_ffprobe", return_value=probe_output),
			patch.object(
				pipeline,
				"check_video_pipeline",
				side_effect=pipeline.VideoPipelineError("Docker is not running"),
			),
			self.assertRaisesRegex(pipeline.VideoPipelineError, "Docker is not running"),
		):
			audio_tracks.add_audio_track(self.video_id, "/private/files/dub.mp3")

		after = len(frappe.get_doc("LMS Video", self.video.name).audio_tracks)
		self.assertEqual(after, before)

	def test_the_last_track_cannot_be_removed(self):
		"""A package with no audio AdaptationSet at all plays silently, with no way
		back short of a full repackage."""
		frappe.set_user(self.instructor.email)
		audio_tracks.remove_audio_track(self.video_id, "so")

		with self.assertRaises(frappe.ValidationError):
			audio_tracks.remove_audio_track(self.video_id, "en")

	def test_removing_a_track_that_never_packaged_skips_the_worker(self):
		"""Nothing on disk and nothing in the manifest, so queueing work for it
		would only produce a no-op job."""
		frappe.set_user("Administrator")
		doc = frappe.get_doc("LMS Video", self.video.name)
		doc.append(
			"audio_tracks",
			{"manifest_lang": "qaa", "segment_dir": "audio_qaa", "label": "Pending dub",
			 "origin": "Added", "status": "Pending", "source_file_url": "/private/files/dub.mp3"},
		)
		doc.save(ignore_permissions=True)

		frappe.set_user(self.instructor.email)
		result = audio_tracks.remove_audio_track(self.video_id, "qaa")

		self.assertEqual(
			sorted(t["manifest_lang"] for t in result["audio_tracks"]), ["en", "so"]
		)

	# --- what the player is allowed to see ---------------------------------

	def test_a_track_still_importing_is_hidden_from_the_player(self):
		"""Its segments are not on disk yet, so offering it would put a dead entry
		in the learner's audio menu."""
		frappe.set_user("Administrator")
		doc = frappe.get_doc("LMS Video", self.video.name)
		doc.append(
			"audio_tracks",
			{"manifest_lang": "qaa", "segment_dir": "audio_qaa", "label": "Somali dub",
			 "origin": "Added", "status": "Processing"},
		)
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		frappe.set_user(self.student.email)
		info = api.get_playback_info(video_id=self.video_id)
		self.assertEqual(sorted(t["manifest_lang"] for t in info["audio_tracks"]), ["en", "so"])

		frappe.set_user(self.instructor.email)
		authoring = api.list_audio_tracks(self.video_id)
		self.assertEqual(
			sorted(t["manifest_lang"] for t in authoring["audio_tracks"]), ["en", "qaa", "so"]
		)

	def test_rows_predating_the_status_field_are_still_offered(self):
		"""Existing sites' tracks carry no status until the patch runs; treating a
		blank one as not-Ready would empty every audio menu on the site."""
		frappe.db.sql(
			"update `tabLMS Video Audio Track` set status = null where parent = %s", self.video.name
		)
		frappe.db.commit()

		frappe.set_user(self.student.email)
		info = api.get_playback_info(video_id=self.video_id)
		self.assertEqual(sorted(t["manifest_lang"] for t in info["audio_tracks"]), ["en", "so"])


class TestPrivateMediaRewrite(BaseTestUtils, UnitTestCase):
	"""`rewrite_private_media` must leave packaged videos alone.

	It rewrites private urls to the serve_resource endpoint. Doing that to a
	manifest url would make the player resolve every relative segment path
	against "/api/method/...", and nothing would load.
	"""

	def test_ordinary_private_files_are_still_rewritten(self):
		from lms.lms.utils import rewrite_private_media

		out = rewrite_private_media('{"file_url": "/private/files/notes.pdf"}')
		self.assertIn("serve_resource?file_url=", out)

	def test_packaged_video_urls_are_left_alone(self):
		from lms.lms.utils import rewrite_private_media

		manifest = "/private/files/videos/a1b2c3d4e5f60718/manifest.mpd"
		out = rewrite_private_media(f'{{"manifest": "{manifest}"}}')

		self.assertIn(manifest, out)
		self.assertNotIn("serve_resource", out)

	def test_a_mixed_content_body_rewrites_only_the_ordinary_file(self):
		from lms.lms.utils import rewrite_private_media

		manifest = "/private/files/videos/a1b2c3d4e5f60718/manifest.mpd"
		out = rewrite_private_media(
			f'{{"pdf": "/private/files/notes.pdf", "manifest": "{manifest}"}}'
		)

		self.assertEqual(out.count("serve_resource"), 1)
		self.assertIn(manifest, out)


class TestVideoSettings(BaseTestUtils, UnitTestCase):
	def test_transcoding_defaults_to_on_when_never_configured(self):
		"""Regression: reading the settings with get_cached_value reports an unset
		Check field as 0, which is indistinguishable from an admin switching it
		off — every migrated site would have had packaging silently disabled."""
		for field in ("video_transcoding_enabled", "keep_original_video"):
			frappe.db.delete("Singles", {"doctype": "LMS Settings", "field": field})
		frappe.clear_cache()

		settings = pipeline.get_video_settings()
		self.assertEqual(settings.video_transcoding_enabled, 1)
		self.assertEqual(settings.keep_original_video, 1)
		self.assertEqual(settings.video_segment_duration, 4)

	def test_an_explicit_off_is_respected(self):
		frappe.db.set_single_value("LMS Settings", "video_transcoding_enabled", 0)
		frappe.clear_cache()
		try:
			self.assertEqual(pipeline.get_video_settings().video_transcoding_enabled, 0)
		finally:
			frappe.db.set_single_value("LMS Settings", "video_transcoding_enabled", 1)
			frappe.clear_cache()


class TestManifestRewrite(BaseTestUtils, UnitTestCase):
	"""Segment templates must be absolute, or relative resolution breaks them."""

	MANIFEST = (
		'<SegmentTemplate timescale="15360" initialization="video/init.mp4" '
		'media="video/$Number$.m4s" startNumber="1"/>'
	)

	def test_templates_are_rewritten_to_the_segment_endpoint(self):
		out = api.rewrite_manifest_urls(self.MANIFEST, "a1b2c3d4e5f60718")

		self.assertIn(f"{api.SEGMENT_ENDPOINT}?video_id=a1b2c3d4e5f60718&path=video/init.mp4", out)
		self.assertIn(f"{api.SEGMENT_ENDPOINT}?video_id=a1b2c3d4e5f60718&path=video/$Number$.m4s", out)

	def test_the_number_placeholder_survives(self):
		"""The player substitutes $Number$ textually before building a request."""
		self.assertIn("$Number$", api.rewrite_manifest_urls(self.MANIFEST, "a1b2c3d4e5f60718"))

	def test_already_absolute_urls_are_not_rewritten_twice(self):
		absolute = '<SegmentTemplate media="/api/method/x?path=video/1.m4s"/>'
		self.assertEqual(api.rewrite_manifest_urls(absolute, "a1b2c3d4e5f60718"), absolute)
