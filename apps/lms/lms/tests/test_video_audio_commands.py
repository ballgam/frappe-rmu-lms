# Copyright (c) 2026, FOSS United and Contributors
# See license.txt

"""Tests for the ffmpeg and packager invocations that import one audio track.

The builders are pure functions over dataclasses, so these run without a site
even though `pipeline` imports frappe at module level.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

import frappe

from lms.lms.video import paths, pipeline, probe


def _audio(**overrides) -> probe.AudioStream:
	defaults = {"index": 1, "codec_name": "aac", "profile": "lc", "channels": 2}
	return probe.AudioStream(**{**defaults, **overrides})


class TestAudioImportCommand(unittest.TestCase):
	def test_conforming_aac_is_stream_copied(self):
		command, name = pipeline.build_audio_import_command("/x/dub.m4a", _audio(), "")

		self.assertEqual(name, "track.mp4")
		self.assertIn("-c:a", command)
		self.assertEqual(command[command.index("-c:a") + 1], "copy")

	def test_the_stream_is_mapped_by_absolute_index(self):
		"""A translator usually returns a full re-dubbed video, where the audio is
		not stream 1 — mapping by audio position would take the wrong one."""
		command, _ = pipeline.build_audio_import_command("/x/dub.mp4", _audio(index=3), "")
		self.assertEqual(command[command.index("-map") + 1], "0:3")

	def test_video_and_subtitles_are_dropped(self):
		"""Importing from a re-dubbed video must yield audio only; the package
		already has its video and a second one would be packaged as a track."""
		command, _ = pipeline.build_audio_import_command("/x/dub.mp4", _audio(), "")
		for flag in ("-vn", "-sn", "-dn"):
			self.assertIn(flag, command)

	def test_a_non_aac_source_is_reencoded(self):
		command, _ = pipeline.build_audio_import_command(
			"/x/dub.mp3", _audio(codec_name="mp3"), probe.needs_audio_reencode(_audio(codec_name="mp3"))
		)
		self.assertEqual(command[command.index("-c:a") + 1], "aac")

	def test_alignment_pins_the_output_to_the_videos_duration(self):
		command, _ = pipeline.build_audio_import_command(
			"/x/dub.mp3", _audio(), "aligning", align_to=118.866
		)

		self.assertEqual(command[command.index("-af") + 1], "apad")
		self.assertEqual(command[command.index("-t") + 1], "118.866")

	def test_alignment_never_rides_on_a_stream_copy(self):
		"""apad is a filter, so `-c:a copy` cannot take it. Callers pass a reason
		whenever they align; this pins that the two never combine."""
		command, _ = pipeline.build_audio_import_command(
			"/x/dub.m4a", _audio(), "aligning duration", align_to=118.866
		)

		self.assertEqual(command[command.index("-c:a") + 1], "aac")
		self.assertNotIn("copy", command)

	def test_progress_is_requested(self):
		"""Without it the editor shows a spinner rather than a percentage."""
		command, _ = pipeline.build_audio_import_command("/x/dub.m4a", _audio(), "")
		self.assertEqual(command[command.index("-progress") + 1], "pipe:1")


class TestAudioPackagerCommand(unittest.TestCase):
	def test_it_writes_into_the_tracks_own_folder(self):
		command = pipeline.build_audio_packager_command("track.mp4", "audio_qaa", "qaa", 4.0)
		descriptor = command[1]

		self.assertIn("init_segment=audio_qaa/init.mp4", descriptor)
		self.assertIn("segment_template=audio_qaa/$Number$.m4s", descriptor)
		self.assertIn("lang=qaa", descriptor)

	def test_it_never_claims_the_main_role(self):
		"""The manifest it is merged into already nominates a default track; a
		second `main` makes the player's choice arbitrary again."""
		command = pipeline.build_audio_packager_command("track.mp4", "audio_qaa", "qaa", 4.0)
		self.assertNotIn("roles=main", " ".join(command))

	def test_it_packages_no_video(self):
		command = pipeline.build_audio_packager_command("track.mp4", "audio_qaa", "qaa", 4.0)
		self.assertNotIn("stream=video", " ".join(command))

	def test_the_manifest_it_writes_is_the_throwaway_one(self):
		"""Never `manifest.mpd`: that name belongs to the live package it is about
		to be merged into, and the packager would overwrite it wholesale."""
		command = pipeline.build_audio_packager_command("track.mp4", "audio_qaa", "qaa", 4.0)

		self.assertEqual(command[command.index("--mpd_output") + 1], paths.TRACK_MANIFEST_NAME)
		self.assertNotEqual(paths.TRACK_MANIFEST_NAME, paths.MANIFEST_NAME)

	def test_every_path_stays_relative_to_the_working_directory(self):
		"""Absolute paths would leak the server's filesystem layout into a manifest
		the browser fetches, and would break the containerised packager outright."""
		command = pipeline.build_audio_packager_command(
			"track.mp4", "audio_qaa", "qaa", 4.0, launcher=["docker", "run", "packager"]
		)
		self.assertNotIn("/work", command[3])
		self.assertFalse(command[3].startswith("in=/"))

	def test_the_launcher_prefix_is_preserved(self):
		launcher = ["docker", "run", "--rm", "image", "packager"]
		command = pipeline.build_audio_packager_command("track.mp4", "audio_qaa", "qaa", 4.0, launcher)

		self.assertEqual(command[: len(launcher)], launcher)

	def test_the_segment_duration_is_whatever_the_package_used(self):
		"""Read from the live manifest rather than LMS Settings, which may have
		been changed in the months since the video was packaged."""
		command = pipeline.build_audio_packager_command("track.mp4", "audio_qaa", "qaa", 6.0)
		self.assertEqual(command[command.index("--segment_duration") + 1], "6.0")


class TestVideoProcessingSettings(unittest.TestCase):
	"""`validate_video_processing_settings` runs on every LMS Settings save.

	These exercise the real `_resolve_binary` rather than patching it, because
	the distinction that matters — a path that was typed in versus a path that
	was left empty — lives inside it.
	"""

	def setUp(self):
		translate = patch.object(pipeline.frappe, "_", side_effect=lambda message: message)
		translate.start()
		self.addCleanup(translate.stop)

		# Nothing at all on PATH, so a fallback lookup can only fail.
		which = patch.object(pipeline.shutil, "which", return_value=None)
		which.start()
		self.addCleanup(which.stop)

		self.missing = os.path.join(tempfile.gettempdir(), "lms-packager-does-not-exist")
		self.assertFalse(os.path.exists(self.missing))

	def _settings(self, **overrides):
		return frappe._dict(
			{
				"video_transcoding_enabled": 1,
				"video_packager_mode": "Docker",
				"packager_path": "",
				"docker_path": "",
				"ffmpeg_path": "",
				"ffprobe_path": "",
				**overrides,
			}
		)

	def test_absent_tooling_does_not_block_a_save(self):
		"""The regression that made every LMS Settings field unsavable.

		Nothing is configured and nothing is installed, which is the state of a
		bench that has not set video processing up yet. Refusing the save here
		would also refuse unrelated fields — signup, contact us, dwell time.
		"""
		pipeline.validate_video_processing_settings(self._settings())
		pipeline.validate_video_processing_settings(self._settings(video_packager_mode="Binary"))

	def test_a_configured_path_that_does_not_exist_is_rejected(self):
		with self.assertRaisesRegex(pipeline.VideoPipelineError, "Shaka Packager"):
			pipeline.validate_video_processing_settings(
				self._settings(video_packager_mode="Binary", packager_path=self.missing)
			)

	def test_a_configured_path_that_is_not_executable_is_rejected(self):
		with tempfile.NamedTemporaryFile(suffix="-ffmpeg") as handle:
			os.chmod(handle.name, 0o644)
			with self.assertRaisesRegex(pipeline.VideoPipelineError, "ffmpeg"):
				pipeline.validate_video_processing_settings(self._settings(ffmpeg_path=handle.name))

	def test_a_stale_path_is_rejected_even_when_its_mode_is_inactive(self):
		"""`depends_on` hides `packager_path` in Docker mode, it does not clear
		it — and switching back to Binary would resurrect it."""
		with self.assertRaisesRegex(pipeline.VideoPipelineError, "Shaka Packager"):
			pipeline.validate_video_processing_settings(
				self._settings(video_packager_mode="Docker", packager_path=self.missing)
			)

	def test_nothing_is_checked_when_transcoding_is_off(self):
		pipeline.validate_video_processing_settings(
			self._settings(video_transcoding_enabled=0, packager_path=self.missing)
		)


class TestSourceExtensions(unittest.TestCase):
	def test_audio_containers_are_importable(self):
		for url in ("/private/files/dub.mp3", "/files/dub.M4A", "/private/files/dub.flac"):
			self.assertTrue(paths.is_importable_audio_source(url), url)

	def test_video_containers_are_importable_too(self):
		"""A translation vendor usually returns a re-dubbed mp4, not a bare audio
		file, and sending the instructor away to extract it by hand helps nobody."""
		self.assertTrue(paths.is_importable_audio_source("/private/files/dub.mp4"))
		self.assertTrue(paths.is_importable_audio_source("/private/files/dub.mkv"))

	def test_everything_else_is_not(self):
		for url in ("/private/files/notes.pdf", "/private/files/slides.pptx", "", None):
			self.assertFalse(paths.is_importable_audio_source(url), url)

	def test_an_audio_file_is_not_mistaken_for_a_source_video(self):
		"""`is_video_file` gates the packaging hook — an mp3 uploaded to a lesson
		must not start a video transcode."""
		self.assertFalse(paths.is_video_file("/private/files/dub.mp3"))
		self.assertTrue(paths.is_audio_file("/private/files/dub.mp3"))

	def test_the_editors_upload_filter_is_not_narrower_than_the_server(self):
		"""The modal pre-filters uploads to save a round trip, so a list that has
		drifted narrower silently blocks files the pipeline would have taken."""
		import os
		import re

		modal = os.path.join(
			os.path.dirname(__file__),
			"..", "..", "frontend", "src", "components", "Modals", "VideoAudioTracks.vue",
		)
		with open(os.path.abspath(modal)) as handle:
			source = handle.read()

		# The name appears twice: the check in validateFile, then the declaration.
		listed = set(re.findall(r"'([a-z0-9]{2,5})',", source.split("ALLOWED_EXTENSIONS")[-1]))
		missing = set(paths.AUDIO_EXTENSIONS + paths.VIDEO_EXTENSIONS) - listed

		self.assertEqual(missing, set(), f"the editor rejects extensions the server accepts: {missing}")
