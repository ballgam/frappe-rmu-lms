# Copyright (c) 2026, FOSS United and Contributors
# See license.txt

"""Tests for grafting an audio track onto an existing DASH manifest.

`manifest` imports nothing from frappe, so these run under plain pytest without
a site as well as under `bench run-tests`.

The fixtures below are the shape Shaka Packager actually emits with
`--generate_static_live_mpd`: a static MPD, one Period, SegmentTemplate inside
each Representation, and exactly one audio AdaptationSet carrying `roles=main`.
"""

import unittest

from lms.lms.video import manifest

TWO_TRACK_MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="urn:mpeg:dash:schema:mpd:2011" xsi:schemaLocation="urn:mpeg:dash:schema:mpd:2011 DASH-MPD.xsd" profiles="urn:mpeg:dash:profile:isoff-live:2011" minBufferTime="PT2S" type="static" mediaPresentationDuration="PT118.866S">
  <Period id="0">
    <AdaptationSet id="0" contentType="video" width="1200" height="608" frameRate="30/1" segmentAlignment="true" par="150:76">
      <Representation id="0" bandwidth="1181396" codecs="avc1.640028" mimeType="video/mp4" sar="1:1">
        <SegmentTemplate timescale="30000" initialization="video/init.mp4" media="video/$Number$.m4s" startNumber="1" duration="120000"/>
      </Representation>
    </AdaptationSet>
    <AdaptationSet id="1" contentType="audio" lang="en" segmentAlignment="true">
      <Role schemeIdUri="urn:mpeg:dash:role:2011" value="main"/>
      <Representation id="1" bandwidth="128337" codecs="mp4a.40.2" mimeType="audio/mp4" audioSamplingRate="48000">
        <AudioChannelConfiguration schemeIdUri="urn:mpeg:dash:23003:3:audio_channel_configuration:2011" value="2"/>
        <SegmentTemplate timescale="48000" initialization="audio_eng/init.mp4" media="audio_eng/$Number$.m4s" startNumber="1" duration="192000"/>
      </Representation>
    </AdaptationSet>
    <AdaptationSet id="2" contentType="audio" lang="so" segmentAlignment="true">
      <Representation id="2" bandwidth="128110" codecs="mp4a.40.2" mimeType="audio/mp4" audioSamplingRate="48000">
        <AudioChannelConfiguration schemeIdUri="urn:mpeg:dash:23003:3:audio_channel_configuration:2011" value="2"/>
        <SegmentTemplate timescale="48000" initialization="audio_som/init.mp4" media="audio_som/$Number$.m4s" startNumber="1" duration="192000"/>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>"""

# What the packager writes for a single track packaged on its own: ids restart
# at 0, and the one track it knows about is nominated as main.
SINGLE_TRACK_MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" profiles="urn:mpeg:dash:profile:isoff-live:2011" minBufferTime="PT2S" type="static" mediaPresentationDuration="PT118.900S">
  <Period id="0">
    <AdaptationSet id="0" contentType="audio" lang="qaa" segmentAlignment="true">
      <Role schemeIdUri="urn:mpeg:dash:role:2011" value="main"/>
      <Representation id="0" bandwidth="128024" codecs="mp4a.40.2" mimeType="audio/mp4" audioSamplingRate="48000">
        <AudioChannelConfiguration schemeIdUri="urn:mpeg:dash:23003:3:audio_channel_configuration:2011" value="2"/>
        <SegmentTemplate timescale="48000" initialization="audio_qaa/init.mp4" media="audio_qaa/$Number$.m4s" startNumber="1" duration="192000"/>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>"""


def _dirs(xml: str) -> list[str]:
	root = manifest.parse(xml)
	return [manifest.segment_dir_of(node) for node in manifest.audio_adaptation_sets(root)]


def _mains(xml: str) -> list[str]:
	root = manifest.parse(xml)
	return [
		manifest.segment_dir_of(node)
		for node in manifest.audio_adaptation_sets(root)
		if manifest._has_main_role(node)
	]


class TestReading(unittest.TestCase):
	def test_finds_every_audio_adaptation_set(self):
		root = manifest.parse(TWO_TRACK_MANIFEST)
		self.assertEqual(len(manifest.audio_adaptation_sets(root)), 2)

	def test_segment_dir_is_read_off_the_template_not_the_lang(self):
		"""The packager rewrites `eng` to `en` in the manifest but leaves the
		segment template's folder alone, so the folder is the reliable join key."""
		root = manifest.parse(TWO_TRACK_MANIFEST)
		by_lang = {node.get("lang"): manifest.segment_dir_of(node) for node in manifest.audio_adaptation_sets(root)}

		self.assertEqual(by_lang, {"en": "audio_eng", "so": "audio_som"})

	def test_used_langs_and_dirs(self):
		root = manifest.parse(TWO_TRACK_MANIFEST)
		self.assertEqual(manifest.used_langs(root), {"en", "so"})
		self.assertEqual(manifest.used_segment_dirs(root), {"video", "audio_eng", "audio_som"})

	def test_segment_duration_comes_from_the_video_track(self):
		"""120000/30000, not 192000/48000 — both are 4s here, but the video's is
		the one the package was cut on."""
		self.assertEqual(manifest.segment_duration(manifest.parse(TWO_TRACK_MANIFEST)), 4.0)

	def test_presentation_duration(self):
		self.assertAlmostEqual(
			manifest.presentation_duration(manifest.parse(TWO_TRACK_MANIFEST)), 118.866, places=3
		)

	def test_iso_durations(self):
		self.assertAlmostEqual(manifest.parse_iso_duration("PT118.866S"), 118.866, places=3)
		self.assertAlmostEqual(manifest.parse_iso_duration("PT1H2M3.5S"), 3723.5, places=3)
		self.assertAlmostEqual(manifest.parse_iso_duration("PT2M"), 120.0)
		with self.assertRaises(manifest.ManifestError):
			manifest.parse_iso_duration("two minutes")

	def test_next_ids_skip_everything_in_use(self):
		root = manifest.parse(TWO_TRACK_MANIFEST)
		self.assertEqual(manifest.next_adaptation_id(root), 3)
		self.assertEqual(manifest.next_representation_id(root), 3)

	def test_an_unparseable_manifest_raises(self):
		with self.assertRaises(manifest.ManifestError):
			manifest.parse("<MPD><Period></MPD>")


class TestMerge(unittest.TestCase):
	def setUp(self):
		self.merged = manifest.merge_audio_adaptation_set(
			TWO_TRACK_MANIFEST, SINGLE_TRACK_MANIFEST, "audio_qaa"
		)

	def test_the_new_track_is_added(self):
		self.assertEqual(_dirs(self.merged), ["audio_eng", "audio_som", "audio_qaa"])

	def test_the_video_track_is_untouched(self):
		"""The whole point: the video's segments and its entry in the manifest are
		exactly what they were, so nothing has to be re-encoded or re-fetched."""
		self.assertIn('initialization="video/init.mp4"', self.merged)
		self.assertIn('media="video/$Number$.m4s"', self.merged)
		self.assertIn('bandwidth="1181396"', self.merged)

	def test_namespaces_are_not_mangled(self):
		"""ElementTree writes `ns0:AdaptationSet` unless the DASH namespace is
		registered as the default. Players cope; humans debugging do not."""
		self.assertNotIn("ns0:", self.merged)
		self.assertIn('xmlns="urn:mpeg:dash:schema:mpd:2011"', self.merged)

	def test_ids_stay_unique(self):
		root = manifest.parse(self.merged)
		adaptation_ids = [node.get("id") for node in manifest._find_all(root, "AdaptationSet")]
		representation_ids = [node.get("id") for node in manifest._find_all(root, "Representation")]

		self.assertEqual(len(set(adaptation_ids)), len(adaptation_ids))
		self.assertEqual(len(set(representation_ids)), len(representation_ids))

	def test_the_fragments_main_role_is_stripped(self):
		"""The base already nominates a default track; a second `main` makes the
		player's choice arbitrary again."""
		self.assertEqual(_mains(self.merged), ["audio_eng"])

	def test_the_presentation_duration_covers_the_new_track(self):
		"""Never shorter than a track it lists, or that track's tail is truncated."""
		self.assertAlmostEqual(
			manifest.presentation_duration(manifest.parse(self.merged)), 118.900, places=3
		)

	def test_a_shorter_new_track_does_not_shrink_the_presentation(self):
		short = SINGLE_TRACK_MANIFEST.replace("PT118.900S", "PT118.000S")
		merged = manifest.merge_audio_adaptation_set(TWO_TRACK_MANIFEST, short, "audio_qaa")

		self.assertAlmostEqual(manifest.presentation_duration(manifest.parse(merged)), 118.866, places=3)

	def test_merging_the_same_track_twice_replaces_rather_than_duplicates(self):
		"""A job retried after crashing between the segment copy and the manifest
		write has to converge, not list the track twice."""
		again = manifest.merge_audio_adaptation_set(self.merged, SINGLE_TRACK_MANIFEST, "audio_qaa")

		self.assertEqual(_dirs(again), ["audio_eng", "audio_som", "audio_qaa"])

	def test_the_merged_manifest_can_be_merged_into_again(self):
		third = SINGLE_TRACK_MANIFEST.replace("qaa", "qab")
		again = manifest.merge_audio_adaptation_set(self.merged, third, "audio_qab")

		self.assertEqual(_dirs(again), ["audio_eng", "audio_som", "audio_qaa", "audio_qab"])
		self.assertEqual(_mains(again), ["audio_eng"])

	def test_a_fragment_with_no_audio_is_rejected(self):
		with self.assertRaises(manifest.ManifestError):
			manifest.merge_audio_adaptation_set(
				TWO_TRACK_MANIFEST, TWO_TRACK_MANIFEST, "audio_nope"
			)


class TestRemove(unittest.TestCase):
	def test_the_named_track_is_dropped(self):
		out = manifest.remove_audio_adaptation_set(TWO_TRACK_MANIFEST, "audio_som")

		self.assertEqual(_dirs(out), ["audio_eng"])
		self.assertIn('media="video/$Number$.m4s"', out)

	def test_removing_the_main_track_moves_the_role(self):
		"""Otherwise the package has no default at all and a player's fallback
		choice is arbitrary."""
		out = manifest.remove_audio_adaptation_set(TWO_TRACK_MANIFEST, "audio_eng")

		self.assertEqual(_dirs(out), ["audio_som"])
		self.assertEqual(_mains(out), ["audio_som"])

	def test_removing_a_non_main_track_leaves_the_role_alone(self):
		out = manifest.remove_audio_adaptation_set(TWO_TRACK_MANIFEST, "audio_som")
		self.assertEqual(_mains(out), ["audio_eng"])

	def test_removing_a_track_that_is_already_gone_is_a_no_op(self):
		out = manifest.remove_audio_adaptation_set(TWO_TRACK_MANIFEST, "audio_qaa")
		self.assertEqual(_dirs(out), ["audio_eng", "audio_som"])

	def test_namespaces_are_not_mangled(self):
		out = manifest.remove_audio_adaptation_set(TWO_TRACK_MANIFEST, "audio_som")
		self.assertNotIn("ns0:", out)


class TestRoundTrip(unittest.TestCase):
	def test_adding_then_removing_returns_the_same_track_list(self):
		merged = manifest.merge_audio_adaptation_set(
			TWO_TRACK_MANIFEST, SINGLE_TRACK_MANIFEST, "audio_qaa"
		)
		back = manifest.remove_audio_adaptation_set(merged, "audio_qaa")

		self.assertEqual(_dirs(back), ["audio_eng", "audio_som"])
		self.assertEqual(_mains(back), ["audio_eng"])

	def test_the_segment_endpoint_rewrite_still_works_on_a_merged_manifest(self):
		"""`api.rewrite_manifest_urls` runs over the manifest every time it is
		served, including after a graft — a merged manifest that it could no longer
		rewrite would 404 every segment."""
		from lms.lms.video import api

		merged = manifest.merge_audio_adaptation_set(
			TWO_TRACK_MANIFEST, SINGLE_TRACK_MANIFEST, "audio_qaa"
		)
		out = api.rewrite_manifest_urls(merged, "a1b2c3d4e5f60718")

		self.assertIn("path=audio_qaa/init.mp4", out)
		self.assertIn("path=audio_qaa/$Number$.m4s", out)
		self.assertIn("path=video/$Number$.m4s", out)
