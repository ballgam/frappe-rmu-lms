# Copyright (c) 2026, FOSS United and contributors
# For license information, please see license.txt

"""Reading and editing a DASH manifest in place.

Adding a translated narration to a lecture that is already packaged does not
need the video touched at all: its segments are immutable and correct. Only the
manifest has to learn that another `<AdaptationSet>` exists. So a new audio
track is packaged on its own, into its own folder, and the one AdaptationSet the
packager produced for it is grafted onto the live manifest.

Everything here is pure — it takes and returns XML strings. No frappe, no
subprocess, no filesystem, so the graft logic is unit-testable without a site,
the same discipline as `probe.py` and `tokens.py`.
"""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ElementTree
from xml.etree.ElementTree import Element

DASH_NS = "urn:mpeg:dash:schema:mpd:2011"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
CENC_NS = "urn:mpeg:cenc:2013"

ROLE_SCHEME = "urn:mpeg:dash:role:2011"

#: The role a DASH player reads as "select this one unless told otherwise".
MAIN_ROLE = "main"

#: PT1H2M3.5S and every subset of it.
ISO_DURATION_RE = re.compile(
	r"^P(?:(?P<days>[\d.]+)D)?"
	r"(?:T(?:(?P<hours>[\d.]+)H)?(?:(?P<minutes>[\d.]+)M)?(?:(?P<seconds>[\d.]+)S)?)?$"
)


class ManifestError(ValueError):
	"""The manifest is not shaped the way the rest of this module assumes."""


def _register_namespaces():
	"""Make ElementTree serialize DASH as the default namespace.

	Without this every tag comes back out as `ns0:AdaptationSet`. Players cope,
	but the manifest stops being diffable against the packager's own output,
	which is the first thing anyone reaches for when a track will not play.
	"""
	ElementTree.register_namespace("", DASH_NS)
	ElementTree.register_namespace("xsi", XSI_NS)
	ElementTree.register_namespace("cenc", CENC_NS)


def parse(xml_text: str) -> Element:
	try:
		return ElementTree.fromstring(xml_text)
	except ElementTree.ParseError as exc:
		raise ManifestError(f"could not parse manifest: {exc}") from exc


def serialize(root: Element) -> str:
	_register_namespaces()
	ElementTree.indent(root, space="  ")
	return ElementTree.tostring(root, encoding="unicode", xml_declaration=True) + "\n"


def _local(tag) -> str:
	"""Local name of a possibly-namespaced tag.

	Every lookup here goes through this rather than matching `{ns}Tag` directly,
	so a namespace bump in a future packager release degrades to a wrong answer
	we can see rather than an empty result we cannot.
	"""
	return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _find_all(root: Element, name: str) -> list[Element]:
	return [node for node in root.iter() if _local(node.tag) == name]


def _qname(name: str) -> str:
	return f"{{{DASH_NS}}}{name}"


def first_period(root: Element) -> Element:
	periods = _find_all(root, "Period")
	if not periods:
		raise ManifestError("manifest has no Period")
	return periods[0]


def _detach(root: Element, node: Element) -> bool:
	"""Remove `node` from whichever element holds it.

	`Element.remove` only works on a direct child, and an AdaptationSet is not
	guaranteed to sit directly under the Period we happen to have picked.
	"""
	for parent in root.iter():
		if node in list(parent):
			parent.remove(node)
			return True
	return False


def is_audio(adaptation_set: Element) -> bool:
	"""Whether an AdaptationSet carries audio.

	`contentType` is what Shaka Packager writes, but it is optional in the spec,
	so fall back to the Representation mime type before concluding it is not audio.
	"""
	content_type = adaptation_set.get("contentType")
	if content_type:
		return content_type == "audio"

	mime = adaptation_set.get("mimeType") or ""
	if mime:
		return mime.startswith("audio/")

	return any(
		(node.get("mimeType") or "").startswith("audio/")
		for node in _find_all(adaptation_set, "Representation")
	)


def audio_adaptation_sets(root: Element) -> list[Element]:
	return [node for node in _find_all(root, "AdaptationSet") if is_audio(node)]


def segment_dir_of(adaptation_set: Element) -> str | None:
	"""The folder this AdaptationSet's segments live in, read off its templates.

	This is the join key between a manifest entry and everything else — the
	`LMS Video Audio Track` row, and the directory on disk. The `lang` attribute
	cannot serve: the packager rewrites language codes on their way into the MPD
	(see `pipeline.read_manifest_audio_langs`), while the segment template keeps
	the folder name verbatim.
	"""
	for template in _find_all(adaptation_set, "SegmentTemplate"):
		for attribute in ("media", "initialization"):
			value = template.get(attribute)
			if value and "/" in value and "://" not in value and not value.startswith("/"):
				return value.split("/", 1)[0]
	return None


def used_langs(root: Element) -> set[str]:
	return {
		lang for lang in (node.get("lang") for node in audio_adaptation_sets(root)) if lang
	}


def used_segment_dirs(root: Element) -> set[str]:
	dirs = set()
	for node in _find_all(root, "AdaptationSet"):
		folder = segment_dir_of(node)
		if folder:
			dirs.add(folder)
	return dirs


def _max_int_attr(nodes: list[Element], attribute: str) -> int:
	highest = -1
	for node in nodes:
		try:
			highest = max(highest, int(node.get(attribute)))
		except (TypeError, ValueError):
			continue
	return highest


def next_adaptation_id(root: Element) -> int:
	return _max_int_attr(_find_all(root, "AdaptationSet"), "id") + 1


def next_representation_id(root: Element) -> int:
	return _max_int_attr(_find_all(root, "Representation"), "id") + 1


def segment_duration(root: Element) -> float | None:
	"""Segment length in seconds, read off the video's SegmentTemplate.

	A track added months later has to be cut on the same boundaries as the rest
	of the package, and `LMS Settings` may well have been changed since — so the
	manifest, not the setting, is the authority on what this video used.
	"""
	video_sets = [node for node in _find_all(root, "AdaptationSet") if not is_audio(node)]
	for group in (video_sets, _find_all(root, "AdaptationSet")):
		for adaptation_set in group:
			for template in _find_all(adaptation_set, "SegmentTemplate"):
				try:
					duration = float(template.get("duration"))
					timescale = float(template.get("timescale") or 1)
				except (TypeError, ValueError):
					continue
				if duration > 0 and timescale > 0:
					return duration / timescale
	return None


def parse_iso_duration(value: str) -> float:
	match = ISO_DURATION_RE.match((value or "").strip())
	if not match:
		raise ManifestError(f"unrecognised duration {value!r}")

	parts = {key: float(raw or 0) for key, raw in match.groupdict().items()}
	return parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]


def format_iso_duration(seconds: float) -> str:
	return f"PT{max(seconds, 0):.3f}S"


def presentation_duration(root: Element) -> float | None:
	raw = root.get("mediaPresentationDuration")
	if not raw:
		return None
	try:
		return parse_iso_duration(raw)
	except ManifestError:
		return None


def _has_main_role(adaptation_set: Element) -> bool:
	return any(
		node.get("value") == MAIN_ROLE
		for node in _find_all(adaptation_set, "Role")
	)


def _strip_main_role(adaptation_set: Element):
	for node in list(adaptation_set):
		if _local(node.tag) == "Role" and node.get("value") == MAIN_ROLE:
			adaptation_set.remove(node)


def _add_main_role(adaptation_set: Element):
	if _has_main_role(adaptation_set):
		return
	role = Element(_qname("Role"), {"schemeIdUri": ROLE_SCHEME, "value": MAIN_ROLE})
	# The DASH schema orders Role before Representation.
	adaptation_set.insert(0, role)


def _renumber(adaptation_set: Element, root: Element):
	"""Give a grafted AdaptationSet ids that do not collide with the base.

	The fragment came out of its own packager run, so its ids restart at 0 and
	would duplicate the video's.
	"""
	adaptation_set.set("id", str(next_adaptation_id(root)))

	next_id = next_representation_id(root)
	for representation in _find_all(adaptation_set, "Representation"):
		representation.set("id", str(next_id))
		next_id += 1


def find_audio_set(root: Element, segment_dir: str) -> Element | None:
	for adaptation_set in audio_adaptation_sets(root):
		if segment_dir_of(adaptation_set) == segment_dir:
			return adaptation_set
	return None


def merge_audio_adaptation_set(base_xml: str, fragment_xml: str, segment_dir: str) -> str:
	"""Graft the audio AdaptationSet for `segment_dir` from `fragment_xml` into `base_xml`.

	`fragment_xml` is the throwaway manifest the packager wrote for the new track
	on its own. Only its AdaptationSet is wanted; its Period, its ids and its
	`roles=main` all belong to a package of one track.

	Replacing rather than appending when the folder is already present keeps the
	operation idempotent, so a job retried after a crash between the segment copy
	and the manifest write converges instead of listing the track twice.
	"""
	base = parse(base_xml)
	fragment = parse(fragment_xml)

	incoming = find_audio_set(fragment, segment_dir)
	if incoming is None:
		# A single-track package has exactly one audio set; accept it under any
		# folder name rather than failing on a packager that templated differently.
		candidates = audio_adaptation_sets(fragment)
		if len(candidates) != 1:
			raise ManifestError(
				f"expected one audio AdaptationSet for {segment_dir} in the packaged track, "
				f"found {len(candidates)}"
			)
		incoming = candidates[0]

	period = first_period(base)

	existing = find_audio_set(base, segment_dir)
	if existing is not None:
		_detach(base, existing)

	grafted = copy.deepcopy(incoming)
	# The base already nominates a default track; a second `main` makes the
	# choice arbitrary again.
	_strip_main_role(grafted)
	_renumber(grafted, base)
	period.append(grafted)

	_extend_presentation_duration(base, fragment)

	return serialize(base)


def _extend_presentation_duration(base: Element, fragment: Element):
	"""Never let the manifest claim to be shorter than the track just added.

	The importer pads or trims new audio to the video's exact duration, so any
	difference here is sub-segment rounding — but a manifest that ends before a
	track does truncates that track's tail, which sounds like a bug in the
	translation rather than in the packaging.
	"""
	base_duration = presentation_duration(base)
	fragment_duration = presentation_duration(fragment)

	if base_duration is None or fragment_duration is None:
		return
	if fragment_duration > base_duration:
		base.set("mediaPresentationDuration", format_iso_duration(fragment_duration))


def remove_audio_adaptation_set(base_xml: str, segment_dir: str) -> str:
	"""Drop the AdaptationSet whose segments live in `segment_dir`.

	A no-op when it is already gone, so a retried removal converges.
	"""
	base = parse(base_xml)

	target = find_audio_set(base, segment_dir)
	if target is None:
		return serialize(base)

	was_main = _has_main_role(target)
	_detach(base, target)

	remaining = audio_adaptation_sets(base)
	if was_main and remaining:
		# Removing the track the packager nominated would leave no default at all,
		# and a player's fallback choice is arbitrary.
		_add_main_role(remaining[0])

	return serialize(base)
