# Copyright (c) 2021, FOSS United and Contributors
# See license.txt

import re
import unittest
from pathlib import Path

from lms.lms.embed_hosts import (
	DEFAULT_EMBED_HOSTS,
	is_allowed_embed_host,
	normalise_host,
	parse_host_list,
)

# Mirrors frontend/src/tests/iframeEmbed.test.ts. Both copies of the allowlist
# have to agree, otherwise an author sees an embed accepted in the editor and
# silently dropped on save (or the reverse).


class TestIsAllowedEmbedHost(unittest.TestCase):
	def test_allows_a_listed_domain_and_its_subdomains(self):
		self.assertTrue(is_allowed_embed_host("https://figma.com/x", ["figma.com"]))
		self.assertTrue(is_allowed_embed_host("https://embed.figma.com/x", ["figma.com"]))
		self.assertTrue(is_allowed_embed_host("https://a.b.figma.com/x", ["figma.com"]))

	def test_rejects_lookalike_hosts(self):
		"""The reason this is not a substring test."""
		for url in (
			"https://evil-figma.com/x",
			"https://figma.com.attacker.test/x",
			"https://notfigma.com/x",
			# the allowed domain appears only in the path / query
			"https://attacker.test/figma.com",
			"https://attacker.test/?u=figma.com",
			# userinfo trick: the host is still attacker.test
			"https://figma.com@attacker.test/x",
		):
			with self.subTest(url=url):
				self.assertFalse(is_allowed_embed_host(url, ["figma.com"]))

	def test_rejects_non_https_schemes(self):
		for url in (
			"http://figma.com/x",
			"javascript:alert(1)",
			"data:text/html,<script>alert(1)</script>",
			"blob:https://figma.com/abc",
			"file:///etc/passwd",
			"//figma.com/x",
		):
			with self.subTest(url=url):
				self.assertFalse(is_allowed_embed_host(url, ["figma.com"]))

	def test_ignores_case_and_trailing_dot(self):
		self.assertTrue(is_allowed_embed_host("https://EMBED.Figma.COM/x", ["figma.com"]))
		self.assertTrue(is_allowed_embed_host("https://figma.com./x", ["figma.com"]))

	def test_rejects_unlisted_empty_and_unparseable(self):
		self.assertFalse(is_allowed_embed_host("https://example.test/x", ["figma.com"]))
		self.assertFalse(is_allowed_embed_host("not a url", ["figma.com"]))
		self.assertFalse(is_allowed_embed_host("", ["figma.com"]))
		self.assertFalse(is_allowed_embed_host(None, ["figma.com"]))

	def test_empty_allowlist_rejects_everything(self):
		self.assertFalse(is_allowed_embed_host("https://figma.com/x", []))

	def test_defaults_to_the_builtin_list(self):
		self.assertTrue(is_allowed_embed_host("https://docs.google.com/document/d/a/preview"))
		self.assertFalse(is_allowed_embed_host("https://attacker.test/x"))

	def test_covers_the_services_the_embed_handoff_can_produce(self):
		"""A URL the editor routes to the `embed` block skips the allowlist check,
		so those hosts must be listed for both paths to agree."""
		for url in (
			"https://www.youtube.com/watch?v=abc",
			"https://youtu.be/abc",
			"https://player.vimeo.com/video/1",
			"https://iframe.videodelivery.net/abc",
			"https://player.mediadelivery.net/embed/1/abc",
		):
			with self.subTest(url=url):
				self.assertTrue(is_allowed_embed_host(url, DEFAULT_EMBED_HOSTS))


class TestParseHostList(unittest.TestCase):
	def test_accepts_whatever_shape_an_administrator_pastes(self):
		raw = " https://Figma.com/foo \n *.miro.com\n\n h5p.org:443 , loom.com "
		self.assertEqual(parse_host_list(raw), ["figma.com", "miro.com", "h5p.org", "loom.com"])

	def test_is_empty_for_blank_input(self):
		self.assertEqual(parse_host_list(""), [])
		self.assertEqual(parse_host_list(None), [])
		self.assertEqual(parse_host_list("  \n  "), [])

	def test_default_list_matches_the_frontend_copy(self):
		"""The allowlist is duplicated in TypeScript for the editor's inline
		validation. A domain added to one copy but not the other means an author
		is either told an embed is fine and then loses it on save, or is refused
		one the server would have accepted — so pin them together.
		"""
		ts_file = (
			Path(__file__).resolve().parents[2] / "frontend" / "src" / "utils" / "iframeEmbed.ts"
		)
		source = ts_file.read_text()
		block = re.search(
			r"DEFAULT_EMBED_HOSTS:\s*readonly string\[\]\s*=\s*\[(.*?)\]", source, re.DOTALL
		)
		self.assertIsNotNone(block, "DEFAULT_EMBED_HOSTS not found in iframeEmbed.ts")

		frontend_hosts = re.findall(r"'([^']+)'", block.group(1))
		self.assertEqual(sorted(frontend_hosts), sorted(DEFAULT_EMBED_HOSTS))

	def test_normalise_host_strips_scheme_path_port_and_punctuation(self):
		self.assertEqual(normalise_host("https://embed.figma.com/proto/1?x=2"), "embed.figma.com")
		self.assertEqual(normalise_host("*.miro.com"), "miro.com")
		self.assertEqual(normalise_host(".h5p.org."), "h5p.org")
		self.assertEqual(normalise_host(""), "")
