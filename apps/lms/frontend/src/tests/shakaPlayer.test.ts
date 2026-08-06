import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { extractSourceFileUrl, canonicalVideoSource } from '@/utils/video'

const SERVE_RESOURCE =
	'/api/method/lms.lms.doctype.course_lesson.course_lesson.serve_resource'

describe('extractSourceFileUrl', () => {
	it('unwraps the serve_resource endpoint back to the stored file path', () => {
		// Lesson content reaches the browser with private urls already rewritten,
		// but the packaged video is keyed on the original path.
		expect(
			extractSourceFileUrl(
				`${SERVE_RESOURCE}?file_url=%2Fprivate%2Ffiles%2Flecture.mp4`
			)
		).toBe('/private/files/lecture.mp4')
	})

	it('handles an absolute wrapped url', () => {
		expect(
			extractSourceFileUrl(
				`http://learning.test:8000${SERVE_RESOURCE}?file_url=%2Fprivate%2Ffiles%2Fa%20b.mp4`
			)
		).toBe('/private/files/a b.mp4')
	})

	it('survives filenames with characters that need escaping', () => {
		expect(
			extractSourceFileUrl(
				`${SERVE_RESOURCE}?file_url=%2Fprivate%2Ffiles%2FModule_1_Intro%20%2B%20Q%26A.mp4`
			)
		).toBe('/private/files/Module_1_Intro + Q&A.mp4')
	})

	it('passes an unwrapped url through untouched', () => {
		expect(extractSourceFileUrl('/files/intro.mp4')).toBe('/files/intro.mp4')
	})

	it('returns null for nothing', () => {
		expect(extractSourceFileUrl(null)).toBeNull()
		expect(extractSourceFileUrl('')).toBeNull()
	})
})

describe('canonicalVideoSource', () => {
	it('produces the absolute url the old progressive player reported', () => {
		// Watch-duration rows and resume positions were keyed on <video>.src,
		// which the browser resolved to an absolute url. Reproducing it exactly is
		// what stops every learner losing their history on upgrade.
		expect(canonicalVideoSource('/files/intro.mp4')).toBe(
			`${window.location.origin}/files/intro.mp4`
		)
	})

	it('leaves an already-absolute url alone', () => {
		expect(canonicalVideoSource('https://cdn.example.com/a.mp4')).toBe(
			'https://cdn.example.com/a.mp4'
		)
	})

	it('returns null for nothing', () => {
		expect(canonicalVideoSource(null)).toBeNull()
	})
})

// --- useShakaPlayer -------------------------------------------------------

const apiResponses = new Map<string, any>()
const shakaState: any = {}

vi.mock('frappe-ui', () => ({
	call: (method: string, args: any) => {
		const handler = apiResponses.get(method)
		if (!handler) return Promise.reject(new Error(`no mock for ${method}`))
		return Promise.resolve(handler(args))
	},
}))

vi.mock('shaka-player/dist/shaka-player.compiled.js', () => {
	class FakePlayer {
		requestFilter: any = null
		selected: any = null
		attach = vi.fn().mockResolvedValue(undefined)
		destroy = vi.fn().mockResolvedValue(undefined)
		load = vi.fn().mockImplementation((...args: any[]) => {
			shakaState.loadArgs = args
			return Promise.resolve()
		})
		addEventListener = vi.fn()
		getNetworkingEngine() {
			return {
				registerRequestFilter: (filter: any) => {
					shakaState.requestFilter = filter
				},
			}
		}
		getVariantTracks() {
			return shakaState.variantTracks ?? []
		}
		selectVariantTrack(track: any, clearBuffer: boolean) {
			shakaState.selected = { track, clearBuffer }
		}
		static isBrowserSupported() {
			return shakaState.supported !== false
		}
	}
	return {
		default: {
			Player: FakePlayer,
			polyfill: { installAll: vi.fn() },
		},
	}
})

const READY_INFO = {
	video_id: 'a1b2c3d4e5f60718',
	status: 'Ready',
	is_private: true,
	duration: 118.8,
	audio_tracks: [
		{ manifest_lang: 'en', label: 'English', language: 'eng', is_default: true },
		{ manifest_lang: 'so', label: 'Somali', language: 'som', is_default: false },
	],
	error: null,
	fallback_url: '/private/files/lecture.mp4',
	token: 'tok-123',
	token_expires_at: Math.floor(Date.now() / 1000) + 3600,
	manifest_url: '/api/method/lms.lms.video.api.serve_video_manifest?video_id=a1b2c3d4e5f60718',
	poster_url: null,
}

async function makePlayer() {
	vi.resetModules()
	const { useShakaPlayer } = await import('@/composables/useShakaPlayer')
	return useShakaPlayer()
}

describe('useShakaPlayer', () => {
	beforeEach(() => {
		apiResponses.clear()
		shakaState.variantTracks = [
			{ id: 1, language: 'en', label: null, audioId: 10, active: true },
			{ id: 2, language: 'so', label: null, audioId: 11, active: false },
		]
		shakaState.supported = true
		shakaState.requestFilter = null
		shakaState.selected = null
		shakaState.loadArgs = null
	})

	afterEach(() => {
		vi.restoreAllMocks()
	})

	it('plays the file progressively when it has no package', async () => {
		// An upload from before this feature existed. It must still play.
		const player = await makePlayer()
		const video = document.createElement('video')

		await player.attach(video, { file: '/files/old.mp4' })

		expect(player.status.value).toBe('progressive')
		expect(video.src).toContain('/files/old.mp4')
		expect(player.audioTracks.value).toEqual([])
	})

	it('shows a processing state while packaging is still running', async () => {
		apiResponses.set('lms.lms.video.api.get_playback_info', () => ({
			...READY_INFO,
			status: 'Packaging',
			audio_tracks: [],
			manifest_url: null,
		}))
		const player = await makePlayer()
		const video = document.createElement('video')

		await player.attach(video, { file: '/private/files/lecture.mkv' })

		expect(player.status.value).toBe('processing')
		// Still points at the original upload so the lesson isn't blank.
		expect(video.src).toContain('/private/files/lecture.mp4')
	})

	it('falls back to the original file when packaging failed', async () => {
		apiResponses.set('lms.lms.video.api.get_playback_info', () => ({
			...READY_INFO,
			status: 'Failed',
			error: 'ffmpeg exploded',
			audio_tracks: [],
		}))
		const player = await makePlayer()
		const video = document.createElement('video')

		await player.attach(video, { file: '/private/files/lecture.mp4' })

		expect(player.status.value).toBe('failed')
		expect(player.errorMessage.value).toBe('ffmpeg exploded')
		expect(video.src).toContain('/private/files/lecture.mp4')
	})

	it('loads the manifest with an explicit DASH mime type', async () => {
		// The manifest is served from an /api/method/ url with no .mpd extension,
		// so Shaka cannot infer the parser from the path.
		apiResponses.set('lms.lms.video.api.get_playback_info', () => READY_INFO)
		const player = await makePlayer()

		await player.attach(document.createElement('video'), {
			file: '/private/files/lecture.mp4',
		})

		expect(player.status.value).toBe('ready')
		expect(shakaState.loadArgs[0]).toBe(READY_INFO.manifest_url)
		expect(shakaState.loadArgs[2]).toBe('application/dash+xml')
	})

	it('builds the audio menu from the instructor labels', async () => {
		apiResponses.set('lms.lms.video.api.get_playback_info', () => READY_INFO)
		const player = await makePlayer()

		await player.attach(document.createElement('video'), {
			file: '/private/files/lecture.mp4',
		})

		expect(player.audioTracks.value.map((t) => t.label)).toEqual([
			'English',
			'Somali',
		])
	})

	it('falls back to the language code when no label matches', async () => {
		// Selection must keep working even if a label lookup misses, so the menu
		// is built from Shaka's tracks and only decorated by the backend.
		apiResponses.set('lms.lms.video.api.get_playback_info', () => ({
			...READY_INFO,
			audio_tracks: [],
		}))
		const player = await makePlayer()

		await player.attach(document.createElement('video'), {
			file: '/private/files/lecture.mp4',
		})

		expect(player.audioTracks.value.map((t) => t.label)).toEqual(['en', 'so'])
	})

	it('selects a track by variant id, not by language', async () => {
		// Two tracks can share a language (narration + commentary); selecting by
		// language could not tell them apart.
		apiResponses.set('lms.lms.video.api.get_playback_info', () => READY_INFO)
		const player = await makePlayer()
		await player.attach(document.createElement('video'), {
			file: '/private/files/lecture.mp4',
		})

		player.selectAudioTrack(2)

		expect(shakaState.selected.track.id).toBe(2)
		// Switch what the learner hears now, rather than after the already
		// buffered seconds of the old language finish playing.
		expect(shakaState.selected.clearBuffer).toBe(true)
		expect(player.audioTracks.value.find((t) => t.active)?.id).toBe(2)
	})

	it('appends the playback token to every request', async () => {
		apiResponses.set('lms.lms.video.api.get_playback_info', () => READY_INFO)
		const player = await makePlayer()
		await player.attach(document.createElement('video'), {
			file: '/private/files/lecture.mp4',
		})

		const request = { uris: ['/api/method/seg?video_id=x&path=video/1.m4s'] }
		await shakaState.requestFilter(0, request)

		expect(request.uris[0]).toContain('&t=tok-123')
	})

	it('renews a token that is about to expire, once, not per request', async () => {
		apiResponses.set('lms.lms.video.api.get_playback_info', () => ({
			...READY_INFO,
			token_expires_at: Math.floor(Date.now() / 1000) + 5,
		}))
		let refreshes = 0
		apiResponses.set('lms.lms.video.api.refresh_playback_token', () => {
			refreshes++
			return {
				token: 'tok-fresh',
				token_expires_at: Math.floor(Date.now() / 1000) + 3600,
			}
		})

		const player = await makePlayer()
		await player.attach(document.createElement('video'), {
			file: '/private/files/lecture.mp4',
		})

		const requests = [
			{ uris: ['/seg/1.m4s'] },
			{ uris: ['/seg/2.m4s'] },
			{ uris: ['/seg/3.m4s'] },
		]
		await Promise.all(requests.map((r) => shakaState.requestFilter(0, r)))

		expect(refreshes).toBe(1)
		requests.forEach((r) => expect(r.uris[0]).toContain('t=tok-fresh'))
	})

	it('plays progressively on a browser without MSE', async () => {
		shakaState.supported = false
		apiResponses.set('lms.lms.video.api.get_playback_info', () => READY_INFO)
		const player = await makePlayer()
		const video = document.createElement('video')

		await player.attach(video, { file: '/private/files/lecture.mp4' })

		expect(player.status.value).toBe('progressive')
		expect(video.src).toContain('/private/files/lecture.mp4')
	})

	it('reaches a terminal status when loading twice in a row', async () => {
		// The internal teardown must not cancel the attach that triggered it.
		apiResponses.set('lms.lms.video.api.get_playback_info', () => READY_INFO)
		const player = await makePlayer()
		const video = document.createElement('video')

		await player.attach(video, { file: '/private/files/lecture.mp4' })
		await player.attach(video, { file: '/private/files/lecture.mp4' })

		expect(player.status.value).toBe('ready')
	})
})
