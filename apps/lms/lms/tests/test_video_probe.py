# Copyright (c) 2026, FOSS United and Contributors
# See license.txt

"""Tests for the pure decision layer of the video pipeline.

`probe` and `tokens` import nothing from frappe, so these run under plain pytest
without a site as well as under `bench run-tests`.
"""

import unittest

from lms.lms.video import probe, tokens

# An MP4 carrying two AAC audio tracks tagged eng and som — the exact shape the
# multi-language lecture feature exists for.
TWO_LANGUAGE_MP4 = {
	"format": {"duration": "118.866016", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
	"streams": [
		{
			"index": 0,
			"codec_type": "video",
			"codec_name": "h264",
			"profile": "High",
			"pix_fmt": "yuv420p",
			"field_order": "progressive",
			"width": 1200,
			"height": 608,
			"avg_frame_rate": "30/1",
			"tags": {"language": "und"},
		},
		{
			"index": 1,
			"codec_type": "audio",
			"codec_name": "aac",
			"profile": "LC",
			"channels": 2,
			"sample_rate": "48000",
			"tags": {"language": "eng"},
			"disposition": {"default": 1},
		},
		{
			"index": 2,
			"codec_type": "audio",
			"codec_name": "aac",
			"profile": "LC",
			"channels": 2,
			"sample_rate": "48000",
			"tags": {"language": "som"},
			"disposition": {"default": 0},
		},
	],
}


def _audio(**overrides) -> probe.AudioStream:
	defaults = {"index": 1, "codec_name": "aac", "profile": "lc", "channels": 2}
	return probe.AudioStream(**{**defaults, **overrides})


def _video(**overrides) -> probe.VideoStream:
	defaults = {
		"index": 0,
		"codec_name": "h264",
		"profile": "high",
		"pix_fmt": "yuv420p",
		"field_order": "progressive",
		"width": 1280,
		"height": 720,
		"avg_frame_rate": 30.0,
	}
	return probe.VideoStream(**{**defaults, **overrides})


class TestParseProbe(unittest.TestCase):
	def test_parses_video_and_every_audio_track(self):
		info = probe.parse_probe(TWO_LANGUAGE_MP4)

		self.assertAlmostEqual(info.duration, 118.866, places=2)
		self.assertEqual(info.video.codec_name, "h264")
		self.assertEqual(info.video.width, 1200)
		self.assertEqual(info.video.avg_frame_rate, 30.0)
		self.assertEqual([a.detected_language for a in info.audios], ["eng", "som"])
		self.assertEqual([a.index for a in info.audios], [1, 2])
		self.assertTrue(info.audios[0].is_default)

	def test_only_the_first_video_stream_is_kept(self):
		data = {"format": {}, "streams": [
			{"index": 0, "codec_type": "video", "codec_name": "h264"},
			{"index": 1, "codec_type": "video", "codec_name": "h264"},
		]}
		info = probe.parse_probe(data)
		self.assertEqual(info.video.index, 0)

	def test_cover_art_is_not_mistaken_for_video(self):
		"""An MP3 with embedded artwork reports a mjpeg 'video' stream; treating
		it as a video would send an audio file down the packaging pipeline."""
		data = {"format": {}, "streams": [
			{"index": 0, "codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}},
			{"index": 1, "codec_type": "audio", "codec_name": "mp3", "channels": 2},
		]}
		info = probe.parse_probe(data)
		self.assertFalse(info.has_video)
		self.assertTrue(info.has_audio)

	def test_playable_duration_is_the_pictures_not_the_containers(self):
		"""A dub that overruns the picture makes the container longer than the
		video. Storing that leaves added tracks padded past the last segment,
		and the mismatched-upload guard measuring against nothing real."""
		data = {"format": {"duration": "156.386"}, "streams": [
			{"index": 0, "codec_type": "video", "codec_name": "h264", "duration": "118.866"},
			{"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "duration": "118.912"},
			{"index": 2, "codec_type": "audio", "codec_name": "aac", "channels": 2, "duration": "156.386"},
		]}
		info = probe.parse_probe(data)

		self.assertAlmostEqual(info.duration, 156.386, places=3)
		self.assertAlmostEqual(info.video.duration, 118.866, places=3)
		self.assertAlmostEqual(info.playable_duration, 118.866, places=3)

	def test_playable_duration_falls_back_when_no_stream_duration(self):
		"""Some muxers write only a container duration."""
		data = {"format": {"duration": "42.5"}, "streams": [
			{"index": 0, "codec_type": "video", "codec_name": "h264"},
		]}
		info = probe.parse_probe(data)

		self.assertEqual(info.video.duration, 0.0)
		self.assertAlmostEqual(info.playable_duration, 42.5, places=3)

	def test_playable_duration_of_an_audio_only_file_is_the_containers(self):
		data = {"format": {"duration": "118.9"}, "streams": [
			{"index": 0, "codec_type": "audio", "codec_name": "mp3", "channels": 2, "duration": "118.9"},
		]}
		info = probe.parse_probe(data)

		self.assertFalse(info.has_video)
		self.assertAlmostEqual(info.playable_duration, 118.9, places=3)

	def test_rotation_from_display_matrix_is_clockwise(self):
		data = {"format": {}, "streams": [{
			"index": 0, "codec_type": "video", "codec_name": "h264",
			"side_data_list": [{"side_data_type": "Display Matrix", "rotation": -90}],
		}]}
		self.assertEqual(probe.parse_probe(data).video.rotation, 90)

	def test_rotation_from_legacy_tag(self):
		data = {"format": {}, "streams": [{
			"index": 0, "codec_type": "video", "codec_name": "h264", "tags": {"rotate": "270"},
		}]}
		self.assertEqual(probe.parse_probe(data).video.rotation, 270)

	def test_fractional_frame_rate(self):
		data = {"format": {}, "streams": [{
			"index": 0, "codec_type": "video", "codec_name": "h264", "avg_frame_rate": "30000/1001",
		}]}
		self.assertAlmostEqual(probe.parse_probe(data).video.avg_frame_rate, 29.97, places=2)

	def test_unknown_frame_rate_does_not_divide_by_zero(self):
		data = {"format": {}, "streams": [{
			"index": 0, "codec_type": "video", "codec_name": "h264", "avg_frame_rate": "0/0",
		}]}
		self.assertEqual(probe.parse_probe(data).video.avg_frame_rate, 0.0)


class TestManifestLanguages(unittest.TestCase):
	"""The audio menu only works if every AdaptationSet has a distinct lang."""

	def test_tagged_languages_are_kept(self):
		audios = probe.assign_manifest_langs([
			_audio(detected_language="eng"), _audio(detected_language="som"),
		])
		self.assertEqual([a.manifest_lang for a in audios], ["eng", "som"])

	def test_untagged_tracks_get_distinct_private_use_codes(self):
		"""The common MP4/MOV case: no per-track language tags at all. Without
		distinct codes both tracks claim 'und' and every player collapses them."""
		audios = probe.assign_manifest_langs([
			_audio(detected_language="und"), _audio(detected_language="und"),
			_audio(detected_language=""),
		])
		codes = [a.manifest_lang for a in audios]
		self.assertEqual(codes, ["qaa", "qab", "qac"])
		self.assertEqual(len(set(codes)), 3)

	def test_duplicate_real_languages_are_disambiguated(self):
		"""Narration and commentary both tagged 'eng' still need to be separable."""
		audios = probe.assign_manifest_langs([
			_audio(detected_language="eng"), _audio(detected_language="eng"),
		])
		self.assertEqual([a.manifest_lang for a in audios], ["eng", "qaa"])

	def test_mixed_tagged_and_untagged(self):
		audios = probe.assign_manifest_langs([
			_audio(detected_language="und"), _audio(detected_language="swa"),
			_audio(detected_language="und"),
		])
		self.assertEqual([a.manifest_lang for a in audios], ["qaa", "swa", "qab"])

	def test_placeholder_tags_are_treated_as_unknown(self):
		audios = probe.assign_manifest_langs([_audio(detected_language="zxx")])
		self.assertEqual(audios[0].manifest_lang, "qaa")

	def test_private_use_range_is_valid_iso_639_2(self):
		codes = list(probe.private_use_codes())
		self.assertEqual(codes[0], "qaa")
		self.assertEqual(codes[-1], "qtz")
		self.assertEqual(len(codes), 520)
		self.assertEqual(len(set(codes)), 520)

	def test_labels_prefer_title_then_language_then_position(self):
		self.assertEqual(probe.default_track_label(_audio(title="Somali dub"), 1), "Somali dub")
		self.assertEqual(probe.default_track_label(_audio(detected_language="som"), 2), "SOM")
		self.assertEqual(probe.default_track_label(_audio(detected_language="und"), 2), "Audio 2")


class TestReservingOneLanguage(unittest.TestCase):
	"""`assign_manifest_lang` reserves a code for a track added to a package that
	already exists, months after the original upload."""

	def test_an_unused_real_code_is_kept(self):
		self.assertEqual(probe.assign_manifest_lang("swa", {"eng", "som"}), "swa")

	def test_a_taken_code_falls_through_to_private_use(self):
		self.assertEqual(probe.assign_manifest_lang("eng", {"eng"}), "qaa")

	def test_an_empty_request_always_gets_a_private_use_code(self):
		"""Added tracks ask for nothing, because the packager rewrites real codes
		on their way into the MPD (`fra` becomes `fr`) and a code that collides
		after that rewrite would merge two tracks into one menu entry."""
		self.assertEqual(probe.assign_manifest_lang("", set()), "qaa")

	def test_it_skips_every_code_already_in_the_manifest(self):
		self.assertEqual(probe.assign_manifest_lang("", {"qaa", "qab", "qad"}), "qac")

	def test_it_matches_the_bulk_assignment_it_was_extracted_from(self):
		audios = [_audio(detected_language="eng"), _audio(detected_language="und")]
		probe.assign_manifest_langs(audios)

		used = set()
		one_by_one = []
		for audio in audios:
			code = probe.assign_manifest_lang(audio.detected_language, used)
			used.add(code)
			one_by_one.append(code)

		self.assertEqual([a.manifest_lang for a in audios], one_by_one)


class TestImportedTrackDuration(unittest.TestCase):
	"""A track added to an existing package has to run the length of the video it
	joins, or the manifest's duration stops describing it."""

	def test_tolerance_is_proportional_with_a_floor(self):
		self.assertEqual(probe.duration_tolerance(60), 5.0)
		self.assertEqual(probe.duration_tolerance(7200), 144.0)

	def test_a_close_enough_file_is_accepted(self):
		self.assertEqual(probe.duration_mismatch_reason(7201.2, 7200), "")

	def test_a_wildly_wrong_file_is_rejected_with_both_durations(self):
		reason = probe.duration_mismatch_reason(2400, 5400)
		self.assertIn("2400.0s", reason)
		self.assertIn("5400.0s", reason)

	def test_a_file_with_no_duration_is_rejected(self):
		self.assertIn("no duration", probe.duration_mismatch_reason(0, 5400))

	def test_sub_second_drift_needs_no_alignment(self):
		self.assertFalse(probe.needs_duration_alignment(7200.1, 7200))

	def test_a_second_of_drift_is_aligned(self):
		self.assertTrue(probe.needs_duration_alignment(7201.2, 7200))

	def test_alignment_pads_and_cuts_to_the_exact_length(self):
		"""apad alone runs forever; it is -t that ends the output."""
		self.assertEqual(probe.build_audio_align_args(7200), ["-af", "apad", "-t", "7200.000"])


class TestEncodeDecisions(unittest.TestCase):
	def test_conforming_h264_can_be_copied(self):
		self.assertEqual(probe.needs_video_reencode(_video(), keyframe_gap=3.5, segment_duration=4), "")

	def test_non_h264_is_reencoded(self):
		reason = probe.needs_video_reencode(_video(codec_name="hevc"), 1.0, 4)
		self.assertIn("hevc", reason)

	def test_ten_bit_pixel_format_is_reencoded(self):
		reason = probe.needs_video_reencode(_video(pix_fmt="yuv420p10le"), 1.0, 4)
		self.assertIn("pixel format", reason)

	def test_interlaced_source_is_reencoded(self):
		reason = probe.needs_video_reencode(_video(field_order="tt"), 1.0, 4)
		self.assertIn("interlaced", reason)

	def test_rotated_source_is_reencoded(self):
		"""A stream copy keeps the rotation matrix, which the packager drops when
		it rewrites the container — the video would play sideways."""
		reason = probe.needs_video_reencode(_video(rotation=90), 1.0, 4)
		self.assertIn("rotation", reason)

	def test_sparse_keyframes_force_a_reencode(self):
		"""The packager can only cut segments at keyframes, so a 10s GOP cannot
		produce 4s segments."""
		reason = probe.needs_video_reencode(_video(), keyframe_gap=10.0, segment_duration=4)
		self.assertIn("keyframes", reason)

	def test_unknown_keyframe_gap_is_not_an_objection(self):
		self.assertEqual(probe.needs_video_reencode(_video(), keyframe_gap=None, segment_duration=4), "")

	def test_aac_lc_stereo_can_be_copied(self):
		self.assertEqual(probe.needs_audio_reencode(_audio()), "")

	def test_non_aac_audio_is_reencoded(self):
		self.assertIn("ac3", probe.needs_audio_reencode(_audio(codec_name="ac3")))

	def test_surround_audio_is_downmixed(self):
		self.assertIn("downmix", probe.needs_audio_reencode(_audio(channels=6)))

	def test_he_aac_is_reencoded(self):
		self.assertIn("profile", probe.needs_audio_reencode(_audio(profile="he-aac")))


class TestFfmpegArgs(unittest.TestCase):
	def test_copy_produces_no_encoder_settings(self):
		self.assertEqual(probe.build_video_args(_video(), 4, "", "-fps_mode"), ["-c:v", "copy"])
		self.assertEqual(probe.build_audio_args(_audio(), ""), ["-c:a", "copy"])

	def test_reencode_pins_the_gop_to_the_segment_duration(self):
		"""Segments can only start on keyframes, so the GOP has to divide evenly
		into the target segment length or the manifest gets uneven segments."""
		args = probe.build_video_args(_video(avg_frame_rate=30.0), 4, "codec", "-fps_mode")
		self.assertEqual(args[args.index("-g") + 1], "120")
		self.assertEqual(args[args.index("-keyint_min") + 1], "120")
		self.assertEqual(args[args.index("-sc_threshold") + 1], "0")

	def test_reencode_forces_constant_frame_rate(self):
		args = probe.build_video_args(_video(), 4, "codec", "-fps_mode")
		self.assertEqual(args[args.index("-fps_mode") + 1], "cfr")

	def test_old_ffmpeg_gets_the_vsync_spelling(self):
		args = probe.build_video_args(_video(), 4, "codec", "-vsync")
		self.assertIn("-vsync", args)
		self.assertNotIn("-fps_mode", args)

	def test_interlaced_source_gets_a_deinterlace_filter(self):
		args = probe.build_video_args(_video(field_order="tt"), 4, "interlaced", "-fps_mode")
		self.assertEqual(args[args.index("-vf") + 1], "yadif")

	def test_unknown_frame_rate_falls_back_to_a_sane_gop(self):
		args = probe.build_video_args(_video(avg_frame_rate=0.0), 4, "codec", "-fps_mode")
		self.assertEqual(args[args.index("-g") + 1], "120")

	def test_surround_audio_is_downmixed_to_stereo(self):
		args = probe.build_audio_args(_audio(channels=6), "surround")
		self.assertEqual(args[args.index("-ac") + 1], "2")


class TestPlaybackTokens(unittest.TestCase):
	KEY = "test-encryption-key"

	def test_round_trip(self):
		token = tokens.mint("a1b2c3d4e5f60718", "learner@example.com", self.KEY)
		self.assertTrue(tokens.verify(token, "a1b2c3d4e5f60718", "learner@example.com", self.KEY))

	def test_emails_containing_dots_round_trip(self):
		"""The payload separator is '.', which is also legal in an email local
		part — splitting naively would corrupt first.last@example.com."""
		user = "first.last@sub.example.co.uk"
		token = tokens.mint("a1b2c3d4e5f60718", user, self.KEY)
		self.assertTrue(tokens.verify(token, "a1b2c3d4e5f60718", user, self.KEY))

	def test_unicode_usernames_do_not_raise(self):
		user = "aliché@example.com"
		token = tokens.mint("a1b2c3d4e5f60718", user, self.KEY)
		self.assertTrue(tokens.verify(token, "a1b2c3d4e5f60718", user, self.KEY))

	def test_token_for_another_video_is_rejected(self):
		token = tokens.mint("a1b2c3d4e5f60718", "learner@example.com", self.KEY)
		with self.assertRaises(tokens.InvalidToken):
			tokens.verify(token, "ffffffffffffffff", "learner@example.com", self.KEY)

	def test_token_for_another_user_is_rejected(self):
		token = tokens.mint("a1b2c3d4e5f60718", "learner@example.com", self.KEY)
		with self.assertRaises(tokens.InvalidToken):
			tokens.verify(token, "a1b2c3d4e5f60718", "someone.else@example.com", self.KEY)

	def test_expired_token_is_rejected(self):
		token = tokens.mint("a1b2c3d4e5f60718", "learner@example.com", self.KEY, ttl_hours=1, now=0)
		with self.assertRaises(tokens.InvalidToken):
			tokens.verify(token, "a1b2c3d4e5f60718", "learner@example.com", self.KEY, now=3601)

	def test_token_signed_with_another_key_is_rejected(self):
		token = tokens.mint("a1b2c3d4e5f60718", "learner@example.com", "other-key")
		with self.assertRaises(tokens.InvalidToken):
			tokens.verify(token, "a1b2c3d4e5f60718", "learner@example.com", self.KEY)

	def test_tampered_payload_is_rejected(self):
		token = tokens.mint("a1b2c3d4e5f60718", "learner@example.com", self.KEY)
		payload, _, signature = token.rpartition(".")
		with self.assertRaises(tokens.InvalidToken):
			tokens.verify(f"{payload}x.{signature}", "a1b2c3d4e5f60718", "learner@example.com", self.KEY)

	def test_malformed_tokens_are_rejected_without_crashing(self):
		for bad in ("", None, "nodot", "a.b.c.d", "!!!.!!!"):
			with self.assertRaises(tokens.InvalidToken):
				tokens.verify(bad, "a1b2c3d4e5f60718", "learner@example.com", self.KEY)


if __name__ == "__main__":
	unittest.main()
