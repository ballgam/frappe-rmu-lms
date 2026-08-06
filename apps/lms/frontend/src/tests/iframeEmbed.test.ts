import { describe, expect, it } from 'vitest'
import {
	DEFAULT_EMBED_HOSTS,
	isAllowedEmbedHost,
	matchKnownService,
	parseEmbedInput,
	parseHostList,
	resolveAllowedHosts,
} from '@/utils/iframeEmbed'

// `__` and `String.prototype.format` are frappe globals the error copy relies on.
globalThis.__ = (text: string) => text
// eslint-disable-next-line no-extend-native
String.prototype.format = function (...args: unknown[]) {
	return this.replace(/{(\d+)}/g, (match, index) =>
		args[index] !== undefined ? String(args[index]) : match
	)
}

describe('parseEmbedInput — iframe snippets', () => {
	it('extracts src, title and fullscreen from a provider snippet', () => {
		const result = parseEmbedInput(
			'<iframe src="https://h5p.org/h5p/embed/1234" width="1090" height="613" ' +
				'title="Interactive video" frameborder="0" allowfullscreen="allowfullscreen"></iframe>'
		)
		expect(result.ok).toBe(true)
		if (!result.ok) return
		expect(result.src).toBe('https://h5p.org/h5p/embed/1234')
		expect(result.title).toBe('Interactive video')
		expect(result.allowFullscreen).toBe(true)
		// 1090x613 is 16:9 within tolerance
		expect(result.aspectRatio).toBe('16:9')
	})

	it('derives 4:3 and 1:1 from the snippet dimensions', () => {
		const fourThree = parseEmbedInput(
			'<iframe src="https://miro.com/app/embed/abc/" width="800" height="600"></iframe>'
		)
		expect(fourThree.ok && fourThree.aspectRatio).toBe('4:3')

		const square = parseEmbedInput(
			'<iframe src="https://miro.com/app/embed/abc/" width="500" height="500"></iframe>'
		)
		expect(square.ok && square.aspectRatio).toBe('1:1')
	})

	it('falls back to a custom height for a shape no preset expresses', () => {
		// A tall embed (a form, a document) — forcing it into 16:9 is what makes
		// these render as a letterbox slit.
		const result = parseEmbedInput(
			'<iframe src="https://form.typeform.com/to/abc" width="640" height="1400"></iframe>'
		)
		expect(result.ok).toBe(true)
		if (!result.ok) return
		expect(result.aspectRatio).toBe('custom')
		expect(result.height).toBe(1400)
	})

	it('takes the first iframe out of a snippet wrapped in markup', () => {
		const result = parseEmbedInput(
			'<div style="position:relative"><iframe src="https://player.vimeo.com/video/76979871"></iframe></div>' +
				'<p><a href="https://vimeo.com">from Vimeo</a></p>'
		)
		expect(result.ok && result.src).toBe(
			'https://player.vimeo.com/video/76979871'
		)
	})
})

describe('parseEmbedInput — plain URLs', () => {
	it('accepts an https link and defaults to a responsive 16:9 frame', () => {
		const result = parseEmbedInput(
			'https://docs.google.com/document/d/abc/preview'
		)
		expect(result.ok).toBe(true)
		if (!result.ok) return
		expect(result.src).toBe('https://docs.google.com/document/d/abc/preview')
		expect(result.aspectRatio).toBe('16:9')
		expect(result.height).toBeNull()
	})

	it('trims surrounding whitespace', () => {
		const result = parseEmbedInput('  https://miro.com/app/board/abc  ')
		expect(result.ok && result.src).toBe('https://miro.com/app/board/abc')
	})

	it('resolves a protocol-relative src to https', () => {
		const result = parseEmbedInput(
			'<iframe src="//player.vimeo.com/video/1"></iframe>'
		)
		expect(result.ok && result.src).toBe('https://player.vimeo.com/video/1')
	})
})

describe('parseEmbedInput — rejections', () => {
	it('rejects javascript: and data: URLs', () => {
		expect(
			parseEmbedInput('<iframe src="javascript:alert(1)"></iframe>').ok
		).toBe(false)
		expect(
			parseEmbedInput(
				'<iframe src="data:text/html,<script>alert(1)</script>"></iframe>'
			).ok
		).toBe(false)
		expect(parseEmbedInput('javascript:alert(1)').ok).toBe(false)
	})

	it('rejects plain http', () => {
		expect(
			parseEmbedInput('<iframe src="http://example.test/x"></iframe>').ok
		).toBe(false)
		expect(parseEmbedInput('http://example.test/x').ok).toBe(false)
	})

	it('rejects markup that contains no iframe', () => {
		expect(parseEmbedInput('<script>alert(1)</script>').ok).toBe(false)
		expect(parseEmbedInput('<p>just some text</p>').ok).toBe(false)
	})

	it('rejects an iframe with no src', () => {
		expect(parseEmbedInput('<iframe width="100"></iframe>').ok).toBe(false)
	})

	it('handles empty and garbage input without throwing', () => {
		expect(parseEmbedInput('').ok).toBe(false)
		expect(parseEmbedInput('   ').ok).toBe(false)
		expect(parseEmbedInput(null).ok).toBe(false)
		expect(parseEmbedInput(undefined).ok).toBe(false)
		expect(parseEmbedInput('not a link at all').ok).toBe(false)
	})
})

// The whole design rests on never persisting HTML: CourseLesson.validate ->
// sanitize_editorjs -> sanitize_html strips any string containing < or >.
// If this ever fails, saved embeds silently disappear on reload.
describe('parseEmbedInput — output survives the sanitizers', () => {
	it('emits no angle brackets in any string field', () => {
		const result = parseEmbedInput(
			'<iframe src="https://h5p.org/h5p/embed/1?a=1&b=2" title="A <b>bold</b> title" ' +
				'width="800" height="450" allowfullscreen></iframe>'
		)
		expect(result.ok).toBe(true)
		if (!result.ok) return
		for (const value of Object.values(result)) {
			if (typeof value !== 'string') continue
			expect(value).not.toMatch(/[<>]/)
		}
	})
})

describe('matchKnownService', () => {
	it('recognises a YouTube watch URL and stores the bare id Plyr expects', () => {
		const known = matchKnownService(
			'https://www.youtube.com/watch?v=QhA4h6qD4wY'
		)
		expect(known).not.toBeNull()
		expect(known!.service).toBe('youtube')
		// The LMS youtube service uses embedUrl '<%= remote_id %>', so `embed` is
		// the raw id — matching the shape already in the database.
		expect(known!.embed).toBe('QhA4h6qD4wY')
	})

	it('recognises youtu.be and the /embed/ form used in copied snippets', () => {
		expect(matchKnownService('https://youtu.be/QhA4h6qD4wY')?.embed).toBe(
			'QhA4h6qD4wY'
		)
		expect(
			matchKnownService('https://www.youtube.com/embed/QhA4h6qD4wY?si=xyz')
				?.service
		).toBe('youtube')
	})

	it('recognises Vimeo as both a watch URL and a player URL', () => {
		// @editorjs/embed assigns data.embed straight to the element src, so it
		// must be the full templated player URL, not the id.
		expect(matchKnownService('https://vimeo.com/76979871')?.embed).toBe(
			'https://player.vimeo.com/video/76979871'
		)
		expect(
			matchKnownService('https://player.vimeo.com/video/76979871')?.embed
		).toBe('https://player.vimeo.com/video/76979871')
	})

	it('carries a private Vimeo hash through', () => {
		expect(matchKnownService('https://vimeo.com/76979871/abc123')?.embed).toBe(
			'https://player.vimeo.com/video/76979871?h=abc123'
		)
	})

	it('recognises Cloudflare and Bunny stream URLs', () => {
		expect(
			matchKnownService(
				'https://customer-abc123.cloudflarestream.com/' +
					'a'.repeat(32) +
					'/watch'
			)?.service
		).toBe('cloudflareStream')
		expect(
			matchKnownService('https://iframe.mediadelivery.net/play/1234/abc-def')
				?.service
		).toBe('bunnyStream')
	})

	it('returns null for anything else, so it falls through to a plain iframe', () => {
		expect(matchKnownService('https://miro.com/app/board/abc')).toBeNull()
		expect(
			matchKnownService('https://docs.google.com/document/d/abc/preview')
		).toBeNull()
	})
})

describe('isAllowedEmbedHost', () => {
	it('allows a listed domain and its subdomains', () => {
		expect(isAllowedEmbedHost('https://figma.com/x', ['figma.com'])).toBe(true)
		expect(isAllowedEmbedHost('https://embed.figma.com/x', ['figma.com'])).toBe(
			true
		)
		expect(isAllowedEmbedHost('https://a.b.figma.com/x', ['figma.com'])).toBe(
			true
		)
	})

	// The reason this is not a substring test.
	it('rejects lookalike hosts', () => {
		expect(isAllowedEmbedHost('https://evil-figma.com/x', ['figma.com'])).toBe(
			false
		)
		expect(
			isAllowedEmbedHost('https://figma.com.attacker.test/x', ['figma.com'])
		).toBe(false)
		expect(isAllowedEmbedHost('https://notfigma.com/x', ['figma.com'])).toBe(
			false
		)
		// host is attacker.test — the allowed domain is only in the path/query
		expect(
			isAllowedEmbedHost('https://attacker.test/?u=figma.com', ['figma.com'])
		).toBe(false)
		expect(
			isAllowedEmbedHost('https://attacker.test/figma.com', ['figma.com'])
		).toBe(false)
	})

	it('ignores case and a trailing dot on the host', () => {
		expect(isAllowedEmbedHost('https://EMBED.Figma.COM/x', ['figma.com'])).toBe(
			true
		)
		expect(isAllowedEmbedHost('https://figma.com./x', ['figma.com'])).toBe(true)
	})

	it('rejects an unlisted host and unparseable input', () => {
		expect(isAllowedEmbedHost('https://example.test/x', ['figma.com'])).toBe(
			false
		)
		expect(isAllowedEmbedHost('not a url', ['figma.com'])).toBe(false)
		expect(isAllowedEmbedHost('', ['figma.com'])).toBe(false)
	})

	it('rejects everything when the allowlist is empty', () => {
		expect(isAllowedEmbedHost('https://figma.com/x', [])).toBe(false)
	})

	it('defaults to the built-in list', () => {
		expect(
			isAllowedEmbedHost('https://docs.google.com/document/d/a/preview')
		).toBe(true)
		expect(isAllowedEmbedHost('https://attacker.test/x')).toBe(false)
	})

	it('covers the services the embed handoff can produce', () => {
		// A URL routed to the `embed` block skips the allowlist check, so these
		// hosts must be listed for the two paths to agree.
		for (const url of [
			'https://www.youtube.com/watch?v=abc',
			'https://youtu.be/abc',
			'https://player.vimeo.com/video/1',
			'https://iframe.videodelivery.net/abc',
			'https://player.mediadelivery.net/embed/1/abc',
		]) {
			expect(isAllowedEmbedHost(url, DEFAULT_EMBED_HOSTS)).toBe(true)
		}
	})
})

describe('parseHostList / resolveAllowedHosts', () => {
	it('accepts whatever shape an administrator pastes', () => {
		expect(
			parseHostList(
				' https://Figma.com/foo \n *.miro.com\n\n h5p.org:443 , loom.com '
			)
		).toEqual(['figma.com', 'miro.com', 'h5p.org', 'loom.com'])
	})

	it('is empty for blank input', () => {
		expect(parseHostList('')).toEqual([])
		expect(parseHostList(null)).toEqual([])
		expect(parseHostList('  \n  ')).toEqual([])
	})

	it('falls back to the defaults when nothing is configured', () => {
		expect(resolveAllowedHosts('')).toBe(DEFAULT_EMBED_HOSTS)
		expect(resolveAllowedHosts(null)).toBe(DEFAULT_EMBED_HOSTS)
	})

	it('replaces rather than extends the defaults, so the list can be narrowed', () => {
		expect(resolveAllowedHosts('figma.com')).toEqual(['figma.com'])
		expect(
			isAllowedEmbedHost(
				'https://youtube.com/x',
				resolveAllowedHosts('figma.com')
			)
		).toBe(false)
	})
})
