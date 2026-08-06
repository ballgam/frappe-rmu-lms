import { describe, it, expect, vi } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import VideoPreview from '@/components/VideoPreview.vue'

const global = { mocks: { __: (s: string) => s } }

describe('VideoPreview', () => {
	it('renders a YouTube iframe (not a <video>) for a youtube link', () => {
		const w = mount(VideoPreview, {
			props: { videoLink: 'https://youtu.be/O7FIiYsVy3U?si=22FPigXQedh7jAlz' },
			global,
		})
		const iframe = w.find('iframe')
		expect(iframe.exists()).toBe(true)
		expect(iframe.attributes('src')).toBe(
			'https://www.youtube.com/embed/O7FIiYsVy3U'
		)
		expect(w.find('video').exists()).toBe(false)
	})

	it('renders a <video> for an uploaded file path', () => {
		const w = mount(VideoPreview, {
			props: { videoLink: '/files/intro.mp4' },
			global,
		})
		const video = w.find('video')
		expect(video.exists()).toBe(true)
		expect(video.attributes('src')).toBe('/files/intro.mp4')
		expect(w.find('iframe').exists()).toBe(false)
	})

	it('tries the packaged video before giving up on a file it cannot decode', async () => {
		// A .mov the browser refuses is exactly what server-side packaging fixes,
		// so the first error reaches for the packaged version rather than
		// immediately surrendering to the poster image.
		const w = mount(VideoPreview, {
			props: {
				videoLink: '/files/intro.mov',
				fallbackImage: '/files/thumb.jpg',
			},
			global,
		})
		await w.find('video').trigger('error')
		expect(w.find('video').exists()).toBe(true)
		expect(w.find('img').exists()).toBe(false)
	})

	it('falls back to the image once the packaged video fails too', async () => {
		const w = mount(VideoPreview, {
			props: {
				videoLink: '/files/intro.mov',
				fallbackImage: '/files/thumb.jpg',
			},
			global,
		})
		await w.find('video').trigger('error')
		await w.find('video').trigger('error')
		expect(w.find('video').exists()).toBe(false)
		const img = w.find('img')
		expect(img.exists()).toBe(true)
		expect(img.attributes('src')).toBe('/files/thumb.jpg')
	})

	it('does not ask the server about a preview that plays normally', async () => {
		// VideoPreview renders once per card in the catalog; a lookup on mount
		// would add a request per card to a listing page.
		const calls: string[] = []
		vi.stubGlobal('fetch', (url: string) => {
			calls.push(String(url))
			return Promise.reject(new Error('no network in tests'))
		})
		mount(VideoPreview, {
			props: { videoLink: '/files/intro.mp4' },
			global,
		})
		await nextTick()
		expect(calls).toEqual([])
		vi.unstubAllGlobals()
	})

	it('renders nothing without a link', () => {
		const w = mount(VideoPreview, {
			props: { videoLink: null },
			global,
		})
		expect(w.find('iframe').exists()).toBe(false)
		expect(w.find('video').exists()).toBe(false)
		expect(w.find('img').exists()).toBe(false)
	})
})
