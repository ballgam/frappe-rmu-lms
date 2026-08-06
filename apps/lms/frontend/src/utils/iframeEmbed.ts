// Parser + allowlist for the `iframe` block (see utils/iframe.ts).
//
// Why this never stores HTML: CourseLesson.validate() runs sanitize_editorjs()
// over every saved lesson, and its sanitize_json() puts *any* string containing
// "<" or ">" through Frappe's sanitize_html — which strips <iframe>. The
// client-side sanitizeEditorJs (utils/index.js) does the same with DOMPurify on
// load and on view. So a pasted embed snippet is parsed here, at input time,
// down to a src URL plus a few primitive attributes; nothing with an angle
// bracket is ever persisted. The existing `embed` block survives for the same
// reason — it stores a service name and a bare id, and keeps its iframe HTML in
// client config.
//
// Kept in its own lean module (no imports at all) so it stays testable without
// index.js's heavy EditorJS/frappe-ui import chain — same rationale as
// ./sanitizeRichHTML.

export type AspectRatio = '16:9' | '4:3' | '1:1' | 'custom'

export type EmbedData = {
	src: string
	title: string
	caption: string
	aspectRatio: AspectRatio
	height: number | null
	allowFullscreen: boolean
}

export type ParsedEmbed =
	| ({ ok: true } & Omit<EmbedData, 'caption'>)
	| { ok: false; error: string }

// Domains allowed out of the box. An administrator can extend this from
// LMS Settings → Allowed Embed Domains; that list replaces these defaults
// rather than adding to them, so an admin can also narrow the set.
export const DEFAULT_EMBED_HOSTS: readonly string[] = [
	// video
	'youtube.com',
	'youtube-nocookie.com',
	'youtu.be',
	'vimeo.com',
	'cloudflarestream.com',
	'videodelivery.net',
	'mediadelivery.net',
	'bunnycdn.com',
	'wistia.com',
	'wistia.net',
	'aparat.com',
	// documents & slides
	'docs.google.com',
	'drive.google.com',
	'forms.gle',
	'slideshare.net',
	'scribd.com',
	'canva.com',
	'genially.com',
	// interactive / whiteboard / design
	'miro.com',
	'figma.com',
	'padlet.com',
	'h5p.org',
	'h5p.com',
	'loom.com',
	'typeform.com',
	'playfactile.com',
	// code
	'codesandbox.io',
	'codepen.io',
	'replit.com',
	'github.com',
	// audio
	'soundcloud.com',
	'spotify.com',
]

export type EmbedService = {
	regex: RegExp
	embedUrl: string
	id?: (groups: string[]) => string
}

// The four video services the `embed` block handles, defined here rather than
// inline in getEditorTools() so this module and that config can't drift: a URL
// we route to `embed` must be one @editorjs/embed will actually render.
// utils/index.js imports these and adds each service's `html` (which reads
// window.innerWidth, so it stays out of this DOM-light module).
//
// Only the video services live here. The other eight (Google Docs, CodeSandbox,
// GitHub, …) gain nothing from the handoff — the generic iframe block renders
// them just as well — so they stay in index.js untouched.
export const EMBED_SERVICES: Record<string, EmbedService> = {
	youtube: {
		regex:
			/^(?:https?:\/\/)?(?:www\.)?(?:(?:youtu\.be\/)|(?:youtube\.com)\/(?:v\/|u\/\w\/|embed\/|watch))(?:(?:\?v=)?([^#&?=]*))?((?:[?&]\w*=\w*)*)$/,
		// Not a URL: the .video-player div hands this to Plyr, which resolves the
		// bare id itself (see extractYouTubeId in utils/plyr.js).
		embedUrl: '<%= remote_id %>',
		id: ([id]) => id,
	},
	vimeo: {
		// Broadened from the watch-URL-only form to also accept
		// player.vimeo.com/video/<id> — that's what a copied Vimeo *embed
		// snippet* contains, and this block accepts snippets.
		regex:
			/^(?:http[s]?:\/\/)?(?:www\.)?(?:player\.)?vimeo\.com\/(?:video\/)?(\d+)(?:\/([a-zA-Z0-9]+))?(?:\?[^\s]*)?$/,
		embedUrl: 'https://player.vimeo.com/video/<%= remote_id %>',
		id: ([id, hash]) => (hash ? `${id}?h=${hash}` : id),
	},
	cloudflareStream: {
		regex:
			/^https:\/\/customer-[a-z0-9]+\.cloudflarestream\.com\/([a-f0-9]{32})\/watch$/,
		embedUrl: 'https://iframe.videodelivery.net/<%= remote_id %>',
	},
	bunnyStream: {
		regex:
			/^https:\/\/(?:iframe\.mediadelivery\.net|video\.bunnycdn\.com|player\.mediadelivery\.net)\/play\/([a-zA-Z0-9]+\/[a-zA-Z0-9-]+)$/,
		embedUrl: 'https://player.mediadelivery.net/embed/<%= remote_id %>',
	},
}

export type KnownService = {
	service: string
	source: string
	embed: string
}

/**
 * Detect a URL the existing `embed` block already handles, so the caller can
 * hand off to it instead of building a generic iframe. That handoff is what
 * keeps the Plyr player, hasVideoContent() (utils/video.ts) and the
 * `icon-youtube` course-outline icon (get_lesson_icon in lms/utils.py) working —
 * all three key off `type === 'embed'`.
 *
 * `embed` is built exactly as @editorjs/embed's own onPaste builds it (the
 * embedUrl template with the id substituted), because its render() assigns
 * data.embed straight to the element's src.
 */
export function matchKnownService(url: string): KnownService | null {
	for (const [service, config] of Object.entries(EMBED_SERVICES)) {
		const match = config.regex.exec(url)
		if (!match) continue
		const groups = match.slice(1).filter((group) => group !== undefined)
		const id = config.id ? config.id(groups) : groups[0]
		if (!id) continue
		return {
			service,
			source: url,
			embed: config.embedUrl.replace(/<%= remote_id %>/g, id),
		}
	}
	return null
}

/**
 * Is `url`'s host covered by `allowedHosts`? A listed domain also covers its
 * subdomains (figma.com → embed.figma.com).
 *
 * Deliberately not a substring test: `includes('figma.com')` would also accept
 * evil-figma.com and figma.com.attacker.net. Matching is exact-or-dot-suffixed
 * against the parsed hostname, never against the raw URL string.
 */
export function isAllowedEmbedHost(
	url: string,
	allowedHosts: readonly string[] = DEFAULT_EMBED_HOSTS
): boolean {
	let host: string
	try {
		host = new URL(url).hostname.toLowerCase().replace(/\.$/, '')
	} catch {
		return false
	}
	if (!host) return false

	return allowedHosts.some((entry) => {
		const domain = normaliseHost(entry)
		if (!domain) return false
		return host === domain || host.endsWith(`.${domain}`)
	})
}

/** Strip scheme, path, port, leading dot and whitespace off an allowlist entry. */
function normaliseHost(entry: string): string {
	return String(entry ?? '')
		.trim()
		.toLowerCase()
		.replace(/^[a-z][a-z0-9+.-]*:\/\//, '')
		.replace(/^\*?\.?/, '')
		.split('/')[0]
		.split('?')[0]
		.split(':')[0]
		.replace(/\.$/, '')
}

/** Parse the textarea contents of LMS Settings → Allowed Embed Domains. */
export function parseHostList(raw?: string | null): string[] {
	if (!raw) return []
	return raw.split(/[\n,]/).map(normaliseHost).filter(Boolean)
}

/** The effective allowlist: the configured one if set, otherwise the defaults. */
export function resolveAllowedHosts(raw?: string | null): readonly string[] {
	const configured = parseHostList(raw)
	return configured.length ? configured : DEFAULT_EMBED_HOSTS
}

/**
 * Turn what the author pasted — a provider's <iframe …> snippet or a bare URL —
 * into the primitives the block persists.
 *
 * Both forms go through one input on purpose: providers' "Share" dialogs hand
 * out either, and asking the author which one they hold is a question they
 * shouldn't have to answer.
 */
export function parseEmbedInput(input?: string | null): ParsedEmbed {
	const raw = String(input ?? '').trim()
	if (!raw) {
		return { ok: false, error: __('Paste an embed code or a link first.') }
	}

	return raw.startsWith('<') ? parseHtml(raw) : parseUrl(raw)
}

function parseHtml(raw: string): ParsedEmbed {
	// DOMParser builds an inert document: unlike assigning to innerHTML on a
	// live node, it won't load the frame or run anything while we're still
	// deciding whether the src is even allowed.
	let iframe: HTMLIFrameElement | null = null
	try {
		iframe = new DOMParser()
			.parseFromString(raw, 'text/html')
			.querySelector('iframe')
	} catch {
		iframe = null
	}

	if (!iframe) {
		return {
			ok: false,
			error: __(
				"That doesn't look like an embed code. Paste the <iframe> snippet from the site's share menu, or paste the link itself."
			),
		}
	}

	const src =
		iframe.getAttribute('src') || iframe.getAttribute('data-src') || ''
	if (!src) {
		return { ok: false, error: __('That embed code has no src to load.') }
	}

	const width = toNumber(iframe.getAttribute('width'))
	const height = toNumber(iframe.getAttribute('height'))
	// Providers hand out wildly different frame sizes; derive a ratio from them
	// when both are real numbers rather than trusting the pixel values, which is
	// what breaks embeds on phones. The author's height is only kept when no
	// preset fits — a tall form or document.
	const aspectRatio = ratioFrom(width, height)

	return parseUrl(src, {
		// Angle brackets are stripped, not escaped: a title carrying markup would
		// be rewritten by sanitize_html on save and come back mangled, and this
		// value only ever lands in an attribute.
		title: stripAngleBrackets(iframe.getAttribute('title')),
		aspectRatio,
		height: aspectRatio === 'custom' ? height : null,
		allowFullscreen:
			iframe.hasAttribute('allowfullscreen') ||
			iframe.hasAttribute('allowFullScreen') ||
			(iframe.getAttribute('allow') || '').includes('fullscreen'),
	})
}

type HtmlAttrs = {
	title: string
	aspectRatio: AspectRatio
	height: number | null
	allowFullscreen: boolean
}

function parseUrl(raw: string, attrs?: HtmlAttrs): ParsedEmbed {
	// Protocol-relative URLs ("//example.com/x") are legal in a src attribute
	// but have no scheme for URL() to check, so resolve them to https first.
	const candidate = raw.startsWith('//') ? `https:${raw}` : raw

	let url: URL
	try {
		url = new URL(candidate)
	} catch {
		return {
			ok: false,
			error: __('{0} is not a valid link.').format(truncate(raw)),
		}
	}

	// One check that covers javascript:, data:, blob: and file: as well as
	// plain http (which the browser would block as mixed content anyway).
	if (url.protocol !== 'https:') {
		return {
			ok: false,
			error: __('Embeds must use a secure https:// link.'),
		}
	}

	return {
		ok: true,
		src: url.href,
		title: attrs?.title ?? '',
		aspectRatio: attrs?.aspectRatio ?? '16:9',
		height: attrs?.height ?? null,
		allowFullscreen: attrs?.allowFullscreen ?? true,
	}
}

/**
 * Remove angle brackets from a value destined for block data.
 *
 * Not escaping — stripping. sanitize_editorjs (client) and sanitize_html
 * (server) both rewrite any stored string containing < or >, so a title or
 * caption carrying them would come back altered after a save/reload round trip.
 * Neither value is ever rendered as markup, so there's nothing to preserve.
 */
export function stripAngleBrackets(value?: string | null): string {
	return (value || '').replace(/[<>]/g, '').trim()
}

function toNumber(value: string | null): number | null {
	if (!value) return null
	const parsed = Number.parseInt(value, 10)
	return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

function ratioFrom(width: number | null, height: number | null): AspectRatio {
	if (!width || !height) return '16:9'
	const ratio = width / height
	if (Math.abs(ratio - 16 / 9) < 0.12) return '16:9'
	if (Math.abs(ratio - 4 / 3) < 0.12) return '4:3'
	if (Math.abs(ratio - 1) < 0.12) return '1:1'
	// Anything else (tall forms, wide banners) keeps the author's own height.
	return 'custom'
}

function truncate(value: string, max = 60): string {
	return value.length > max ? `${value.slice(0, max)}…` : value
}

/** CSS aspect-ratio value for a preset, or null when a fixed height is used. */
export function aspectRatioValue(ratio: AspectRatio): string | null {
	switch (ratio) {
		case '4:3':
			return '4 / 3'
		case '1:1':
			return '1 / 1'
		case 'custom':
			return null
		default:
			return '16 / 9'
	}
}
