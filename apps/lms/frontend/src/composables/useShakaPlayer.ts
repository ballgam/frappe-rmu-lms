import { ref, shallowRef, type Ref } from 'vue'
import { extractSourceFileUrl } from '@/utils/video'

/**
 * frappe-ui's `call` is reached through a dynamic import rather than a top-level
 * one so that merely importing this composable doesn't drag the whole resource
 * layer into a component's module graph — which breaks component tests that
 * mount without a configured frappe-ui.
 */
async function apiCall(method: string, args: Record<string, unknown>) {
	const { call } = await import('frappe-ui')
	return call(method, args)
}

/**
 * Plays a lesson video, with a menu for its audio tracks.
 *
 * Uploaded videos are packaged as MPEG-DASH with one AdaptationSet per audio
 * track, which is the only way a browser will expose the translated narrations
 * a lecture file carries — a plain <video> only ever decodes the first one.
 *
 * Shaka is loaded lazily and every failure degrades to progressive playback of
 * the original upload, so a lesson is never dark: no packaged version yet, a
 * failed transcode, an unsupported browser, and a Shaka load error all end up
 * playing the file the instructor uploaded.
 */

export type AudioTrack = {
	/** Shaka's own track id — what selection actually acts on. */
	id: number
	language: string
	label: string
	active: boolean
}

export type PlaybackStatus =
	| 'idle'
	| 'loading'
	| 'processing'
	| 'ready'
	| 'progressive'
	| 'failed'

type PlaybackInfo = {
	video_id: string
	status: 'Pending' | 'Probing' | 'Packaging' | 'Ready' | 'Failed'
	is_private: boolean
	duration: number
	audio_tracks: {
		manifest_lang: string
		label: string
		language: string
		is_default: boolean
	}[]
	error: string | null
	fallback_url: string | null
	token: string | null
	token_expires_at: number | null
	manifest_url: string | null
	poster_url: string | null
}

/** Renew this many seconds before expiry rather than after a failed request. */
const TOKEN_RENEWAL_MARGIN = 120

let shakaModule: any = null
let shakaLoad: Promise<any> | null = null

/**
 * Load and initialise Shaka once per page, not once per video block.
 *
 * The bundle is ~400 KB, and most lessons have no video at all, so it stays out
 * of the main chunk behind a dynamic import.
 */
async function loadShaka() {
	if (shakaModule) return shakaModule
	if (!shakaLoad) {
		shakaLoad = import('shaka-player/dist/shaka-player.compiled.js').then(
			(mod) => {
				const shaka = (mod as any).default ?? mod
				shaka.polyfill.installAll()
				shakaModule = shaka
				return shaka
			}
		)
	}
	return shakaLoad
}

export function useShakaPlayer() {
	const status = ref<PlaybackStatus>('idle')
	const audioTracks = ref<AudioTrack[]>([])
	const duration = ref(0)
	const poster = ref<string | null>(null)
	const errorMessage = ref<string | null>(null)
	const usingDash = ref(false)
	const videoId = ref<string | null>(null)

	const player = shallowRef<any>(null)

	let token: string | null = null
	let tokenExpiresAt = 0
	let refreshing: Promise<void> | null = null
	/** Guards against a late async load writing over a newer one. */
	let generation = 0

	async function fetchPlaybackInfo(
		fileUrl: string | null,
		id: string | null
	): Promise<PlaybackInfo | null> {
		try {
			return await apiCall('lms.lms.video.api.get_playback_info', {
				video_id: id || undefined,
				file_url: id ? undefined : fileUrl || undefined,
			})
		} catch {
			// No LMS Video row for this file — an upload from before the feature
			// existed, or one the backfill hasn't reached. Progressive it is.
			return null
		}
	}

	async function ensureFreshToken() {
		if (!token || !videoId.value) return
		if (Date.now() / 1000 < tokenExpiresAt - TOKEN_RENEWAL_MARGIN) return

		// Several segment requests are in flight at once; they must share one
		// refresh rather than each triggering their own.
		if (!refreshing) {
			refreshing = apiCall('lms.lms.video.api.refresh_playback_token', {
				video_id: videoId.value,
			})
				.then((result: { token: string; token_expires_at: number }) => {
					token = result.token
					tokenExpiresAt = result.token_expires_at
				})
				.catch(() => {})
				.finally(() => {
					refreshing = null
				})
		}
		await refreshing
	}

	function withToken(uri: string) {
		if (!token) return uri
		return `${uri}${uri.includes('?') ? '&' : '?'}t=${encodeURIComponent(token)}`
	}

	async function playProgressive(
		videoEl: HTMLVideoElement,
		src: string | null,
		nextStatus: PlaybackStatus
	) {
		await teardownPlayer()
		if (src) videoEl.src = src
		usingDash.value = false
		audioTracks.value = []
		status.value = nextStatus
	}

	/**
	 * Point `videoEl` at a lesson video.
	 *
	 * `file` is the block's file url (already wrapped in the serve_resource
	 * endpoint by the time it reaches the browser); `id` short-circuits the
	 * lookup when the caller already knows the video.
	 */
	async function attach(
		videoEl: HTMLVideoElement,
		options: { file?: string | null; videoId?: string | null } = {}
	) {
		const mine = ++generation
		status.value = 'loading'
		errorMessage.value = null

		const sourceFileUrl = extractSourceFileUrl(options.file)
		const info = await fetchPlaybackInfo(sourceFileUrl, options.videoId ?? null)
		if (mine !== generation) return

		if (!info) {
			await playProgressive(videoEl, options.file ?? null, 'progressive')
			return
		}

		videoId.value = info.video_id
		duration.value = info.duration || 0
		poster.value = info.poster_url

		if (info.status === 'Failed') {
			errorMessage.value = info.error
			await playProgressive(videoEl, info.fallback_url, 'failed')
			return
		}

		if (info.status !== 'Ready') {
			// Still encoding. The original upload may be a container the browser
			// cannot decode (.mkv, .avi), so this is a genuine waiting state, not
			// something we can paper over.
			await playProgressive(videoEl, info.fallback_url, 'processing')
			return
		}

		try {
			await loadDash(videoEl, info)
			if (mine !== generation) return
			status.value = 'ready'
		} catch (error: any) {
			if (mine !== generation) return
			console.error('Shaka could not play the packaged video', error)
			errorMessage.value = error?.message ?? String(error)
			await playProgressive(videoEl, info.fallback_url, 'progressive')
		}
	}

	async function loadDash(videoEl: HTMLVideoElement, info: PlaybackInfo) {
		const shaka = await loadShaka()

		if (!shaka.Player.isBrowserSupported()) {
			throw new Error('This browser cannot play adaptive streams')
		}

		await teardownPlayer()

		token = info.token
		tokenExpiresAt = info.token_expires_at ?? 0

		const instance = new shaka.Player()
		await instance.attach(videoEl)
		player.value = instance

		// The token rides on each request rather than being baked into the
		// manifest, so renewing it never means re-fetching the manifest.
		instance
			.getNetworkingEngine()
			.registerRequestFilter(async (_type: unknown, request: any) => {
				await ensureFreshToken()
				request.uris = request.uris.map(withToken)
			})

		instance.addEventListener('error', (event: any) => {
			console.error('Shaka error', event?.detail)
		})

		// The manifest is served from an /api/method/ url with no .mpd extension,
		// so the type has to be stated explicitly for Shaka to pick the DASH parser.
		await instance.load(info.manifest_url, null, 'application/dash+xml')

		usingDash.value = true
		duration.value = videoEl.duration || info.duration || 0
		audioTracks.value = readAudioTracks(instance, info)
	}

	/**
	 * Build the audio menu from Shaka's variant tracks, decorated with the
	 * instructor's labels.
	 *
	 * Shaka's tracks are authoritative for *selection*; the backend rows only
	 * supply display names. Keeping it that way means a label that fails to match
	 * (a packager that normalised a language code differently than expected)
	 * costs a nice name, never the ability to switch tracks.
	 */
	function readAudioTracks(instance: any, info: PlaybackInfo): AudioTrack[] {
		const labels = new Map(
			(info.audio_tracks || []).map((track) => [
				String(track.manifest_lang).toLowerCase(),
				track.label,
			])
		)

		const seen = new Set<string>()
		const tracks: AudioTrack[] = []

		for (const variant of instance.getVariantTracks()) {
			const language = String(variant.language || '').toLowerCase()
			// One variant per audio track here (there is a single video rendition),
			// but dedupe defensively so a future bitrate ladder doesn't multiply
			// the menu entries.
			const key = `${language}:${variant.audioId ?? ''}`
			if (seen.has(key)) continue
			seen.add(key)

			tracks.push({
				id: variant.id,
				language: variant.language,
				label: labels.get(language) || variant.label || variant.language,
				active: !!variant.active,
			})
		}

		return tracks
	}

	function selectAudioTrack(trackId: number) {
		const instance = player.value
		if (!instance) return

		const variant = instance
			.getVariantTracks()
			.find((track: any) => track.id === trackId)
		if (!variant) return

		// clearBuffer switches what the learner hears immediately instead of after
		// the seconds already buffered in the old language have played out.
		instance.selectVariantTrack(variant, /* clearBuffer */ true)
		audioTracks.value = audioTracks.value.map((track) => ({
			...track,
			active: track.id === trackId,
		}))
	}

	/**
	 * Tear the player down without cancelling the load in progress.
	 *
	 * Kept separate from `destroy` because both `loadDash` and `playProgressive`
	 * call it *during* an attach — bumping the generation counter here would make
	 * every attach invalidate itself before it could report success.
	 */
	async function teardownPlayer() {
		const instance = player.value
		player.value = null
		if (instance) {
			try {
				await instance.destroy()
			} catch {
				// Already torn down.
			}
		}
	}

	/** Public teardown: also cancels any attach still in flight. */
	async function destroy() {
		generation++
		await teardownPlayer()
	}

	return {
		attach,
		destroy,
		selectAudioTrack,
		audioTracks: audioTracks as Ref<AudioTrack[]>,
		status,
		usingDash,
		duration,
		poster,
		errorMessage,
		videoId,
	}
}
