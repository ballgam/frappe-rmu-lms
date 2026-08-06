"""Allowlist for the lesson editor's `iframe` block.

Mirrors frontend/src/utils/iframeEmbed.ts. The client copy is what gives the
author an error message while they're typing; this one is the actual control —
without it a crafted frappe.client.set_value on Course Lesson.content would
frame anything at all, since the frontend is never in that path.

Keep the default list below in sync with DEFAULT_EMBED_HOSTS in iframeEmbed.ts.
"""

from urllib.parse import urlparse

# Domains allowed out of the box. An administrator can replace (not extend) this
# from LMS Settings → Allowed Embed Domains, so the list can be narrowed too.
DEFAULT_EMBED_HOSTS = [
	# video
	"youtube.com",
	"youtube-nocookie.com",
	"youtu.be",
	"vimeo.com",
	"cloudflarestream.com",
	"videodelivery.net",
	"mediadelivery.net",
	"bunnycdn.com",
	"wistia.com",
	"wistia.net",
	"aparat.com",
	# documents & slides
	"docs.google.com",
	"drive.google.com",
	"forms.gle",
	"slideshare.net",
	"scribd.com",
	"canva.com",
	"genially.com",
	# interactive / whiteboard / design
	"miro.com",
	"figma.com",
	"padlet.com",
	"h5p.org",
	"h5p.com",
	"loom.com",
	"typeform.com",
	"playfactile.com",
	# code
	"codesandbox.io",
	"codepen.io",
	"replit.com",
	"github.com",
	# audio
	"soundcloud.com",
	"spotify.com",
]


def normalise_host(entry: str) -> str:
	"""Reduce an allowlist entry to a bare hostname.

	Administrators paste whatever they have to hand — a full URL, a leading dot,
	a wildcard — so strip scheme, path, port and stray punctuation rather than
	silently ignoring the line.
	"""
	host = (entry or "").strip().lower()
	if not host:
		return ""
	if "//" in host:
		host = host.split("//", 1)[1]
	host = host.lstrip("*.")
	for separator in ("/", "?", "#", ":"):
		host = host.split(separator, 1)[0]
	return host.rstrip(".")


def parse_host_list(raw: str) -> list[str]:
	"""Parse the LMS Settings → Allowed Embed Domains textarea."""
	if not raw:
		return []
	entries = (normalise_host(line) for line in raw.replace(",", "\n").splitlines())
	return [entry for entry in entries if entry]


def get_allowed_embed_hosts() -> list[str]:
	"""The effective allowlist: the configured one if set, else the defaults."""
	import frappe

	configured = parse_host_list(frappe.get_cached_value("LMS Settings", None, "allowed_embed_hosts"))
	return configured or list(DEFAULT_EMBED_HOSTS)


def is_allowed_embed_host(url: str, allowed_hosts: list[str] | None = None) -> bool:
	"""Is `url` an https link whose host is covered by `allowed_hosts`?

	A listed domain also covers its subdomains (figma.com → embed.figma.com).
	Deliberately not a substring test: `"figma.com" in url` would also accept
	evil-figma.com and figma.com.attacker.net, so matching is exact-or-dot-
	suffixed against the parsed hostname.
	"""
	if allowed_hosts is None:
		allowed_hosts = DEFAULT_EMBED_HOSTS

	try:
		parsed = urlparse((url or "").strip())
	except ValueError:
		return False

	# One check that covers javascript:, data:, blob: and plain http.
	if parsed.scheme != "https":
		return False

	host = (parsed.hostname or "").lower().rstrip(".")
	if not host:
		return False

	for entry in allowed_hosts:
		domain = normalise_host(entry)
		if domain and (host == domain or host.endswith("." + domain)):
			return True
	return False
