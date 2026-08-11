import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'

/**
 * The audio track manager: naming tracks, adding a translation to a video that
 * is already packaged, and removing one.
 *
 * Adding is the reason this is not just a rename form. A translated narration
 * arrives months after the lecture is published, so the modal has to show tracks
 * that are still importing — which the player-facing endpoint deliberately hides
 * — and must not let an author remove the last one.
 */

const calls: { method: string; args: any }[] = []
let responses: Record<string, any> = {}

vi.mock('frappe-ui', () => ({
	call: (method: string, args: any) => {
		calls.push({ method, args })
		const response = responses[method]
		if (response instanceof Error) return Promise.reject(response)
		return Promise.resolve(response ?? {})
	},
	Dialog: {
		props: ['options', 'modelValue'],
		template: '<div><slot name="body-content" /><slot name="actions" /></div>',
	},
	Button: {
		props: ['loading', 'disabled', 'variant', 'size', 'label'],
		emits: ['click'],
		template: `<button :disabled="disabled" @click="$emit('click')"><slot /></button>`,
	},
	FormControl: {
		props: ['modelValue', 'type', 'label', 'placeholder'],
		emits: ['update:modelValue'],
		template: `<input :type="type || 'text'" :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />`,
	},
	Autocomplete: {
		props: ['modelValue', 'options', 'placeholder'],
		emits: ['update:modelValue'],
		template: '<div class="autocomplete" />',
	},
	FileUploader: {
		emits: ['success'],
		template: `<div><slot :progress="0" :uploading="false" :openFileSelector="() => {}" /></div>`,
	},
}))

const socketHandlers: Record<string, Function[]> = {}
vi.mock('@/socket', () => ({
	initSocket: () => ({
		on: (event: string, handler: Function) => {
			;(socketHandlers[event] ||= []).push(handler)
		},
		off: (event: string, handler: Function) => {
			socketHandlers[event] = (socketHandlers[event] || []).filter(
				(h) => h !== handler
			)
		},
	}),
}))

import VideoAudioTracks from '@/components/Modals/VideoAudioTracks.vue'

type TrackRow = {
	manifest_lang: string
	label: string
	language: string
	is_default: boolean
	status: string
	origin: string
	error: string | null
}

const READY_TRACKS: TrackRow[] = [
	{
		manifest_lang: 'qaa',
		label: 'English',
		language: 'eng',
		is_default: true,
		status: 'Ready',
		origin: 'Source File',
		error: null,
	},
	{
		manifest_lang: 'qab',
		label: 'Somali',
		language: 'som',
		is_default: false,
		status: 'Ready',
		origin: 'Added',
		error: null,
	},
]

/** Mirrors the app's global `__`, including the `.format` helper components use. */
function withFormat(s: string) {
	const out = new String(s) as any
	out.format = (...args: any[]) =>
		s.replace(/\{(\d+)\}/g, (_m, i) => String(args[Number(i)]))
	return out
}

vi.stubGlobal('__', withFormat)

async function open(tracks: TrackRow[] = READY_TRACKS) {
	responses['lms.lms.video.api.list_audio_tracks'] = { audio_tracks: tracks }
	const wrapper = mount(VideoAudioTracks, {
		props: { videoId: 'a1b2c3d4e5f60718', modelValue: false },
		// The template resolves `__` on the instance; `<script setup>` resolves it
		// on globalThis. Both are the app's real global, so both are stubbed.
		global: { mocks: { __: withFormat } },
	})
	// The modal loads when `show` becomes true, which the initial value does not
	// trigger — flip it the way opening the dialog does.
	await wrapper.setProps({ modelValue: true })
	await flushPromises()
	return wrapper
}

beforeEach(() => {
	calls.length = 0
	responses = {}
	for (const key of Object.keys(socketHandlers)) delete socketHandlers[key]
})

describe('VideoAudioTracks', () => {
	it('loads the authoring list, not the player list', async () => {
		// get_playback_info hides tracks that are not Ready; the editor needs
		// exactly what it hides.
		await open()
		expect(calls.map((c) => c.method)).toContain(
			'lms.lms.video.api.list_audio_tracks'
		)
		expect(calls.map((c) => c.method)).not.toContain(
			'lms.lms.video.api.get_playback_info'
		)
	})

	it('uploads through the LMS endpoint, not Frappe generic uploader', async () => {
		// Regression: /api/method/upload_file refuses every audio/* mimetype for
		// users without desk access, which is what course creators here are — so
		// uploading a dub returned 417 before any of our code ran.
		const wrapper = await open()
		expect(wrapper.vm.uploadArgs).toMatchObject({
			upload_endpoint:
				'/api/method/lms.lms.video.audio_tracks.upload_audio_source',
			doctype: 'LMS Video',
			docname: 'a1b2c3d4e5f60718',
			private: true,
		})
	})

	it('shows why an upload failed instead of failing silently', async () => {
		const wrapper = await open()
		wrapper.vm.onUploadFailed({ message: 'File size exceeded the maximum' })
		await nextTick()
		expect(wrapper.text()).toContain('File size exceeded the maximum')
	})

	it('sends the uploaded file to add_audio_track with its label and language', async () => {
		const wrapper = await open()
		responses['lms.lms.video.audio_tracks.add_audio_track'] = {
			audio_tracks: [
				...READY_TRACKS,
				{
					manifest_lang: 'qac',
					label: 'French',
					language: 'fra',
					status: 'Pending',
					origin: 'Added',
					is_default: false,
					error: null,
				},
			],
		}

		wrapper.vm.newTrack.label = 'French'
		wrapper.vm.newTrack.languageOption = { label: 'French (fra)', value: 'fra' }
		await wrapper.vm.onUploaded({ file_url: '/private/files/french.m4a' })
		await flushPromises()

		const add = calls.find(
			(c) => c.method === 'lms.lms.video.audio_tracks.add_audio_track'
		)
		expect(add?.args).toMatchObject({
			video_id: 'a1b2c3d4e5f60718',
			file_url: '/private/files/french.m4a',
			label: 'French',
			language: 'fra',
		})
	})

	it('shows a track that is still importing, with its status', async () => {
		const wrapper = await open([
			READY_TRACKS[0],
			{ ...READY_TRACKS[1], status: 'Processing', label: 'Somali' },
		])
		// Its name is editable while it imports, so it lives in an input.
		const names = wrapper
			.findAll('input[type="text"]')
			.map((i) => (i.element as HTMLInputElement).value)
		expect(names).toContain('Somali')
		expect(wrapper.text()).toContain('Processing')
	})

	it('surfaces the error and a retry when an import failed', async () => {
		const wrapper = await open([
			READY_TRACKS[0],
			{
				...READY_TRACKS[1],
				status: 'Failed',
				error: 'the uploaded audio is 2400.0s long but the video is 5400.0s',
			},
		])
		expect(wrapper.text()).toContain('Could not be added')
		expect(wrapper.text()).toContain('2400.0s')
		expect(wrapper.text()).toContain('Retry')
	})

	it('offers no delete when only one track would be left', async () => {
		// A package with no audio AdaptationSet plays silently, with no way back
		// short of a full repackage.
		const wrapper = await open([READY_TRACKS[0]])
		expect(wrapper.vm.canRemove).toBe(false)

		const twoTracks = await open(READY_TRACKS)
		expect(twoTracks.vm.canRemove).toBe(true)
	})

	it('removing a track tells the player its manifest changed', async () => {
		const wrapper = await open()
		vi.stubGlobal('confirm', () => true)
		responses['lms.lms.video.audio_tracks.remove_audio_track'] = {
			audio_tracks: [READY_TRACKS[0]],
		}

		await wrapper.vm.remove(READY_TRACKS[1])
		await flushPromises()

		expect(
			calls.find(
				(c) => c.method === 'lms.lms.video.audio_tracks.remove_audio_track'
			)?.args
		).toMatchObject({ manifest_lang: 'qab' })
		expect(wrapper.emitted('updated')?.[0][0]).toMatchObject({
			listChanged: true,
		})
	})

	it('renaming emits listChanged false so the player patches in place', async () => {
		// The manifest is keyed on manifest_lang, which a rename never touches, so
		// re-fetching it would only interrupt playback for nothing.
		const wrapper = await open()
		responses['lms.lms.video.api.update_audio_tracks'] = {
			audio_tracks: READY_TRACKS,
		}

		await wrapper.vm.save()
		await flushPromises()

		expect(wrapper.emitted('updated')?.[0][0]).toMatchObject({
			listChanged: false,
		})
	})

	it('a progress event updates one row without re-fetching the list', async () => {
		const wrapper = await open([
			READY_TRACKS[0],
			{ ...READY_TRACKS[1], status: 'Processing' },
		])
		const before = calls.length

		for (const handler of socketHandlers['lms_video_track_status'] || []) {
			handler({
				video_id: 'a1b2c3d4e5f60718',
				manifest_lang: 'qab',
				status: 'Processing',
				progress: 42,
			})
		}
		await nextTick()

		expect(calls.length).toBe(before)
		expect(wrapper.text()).toContain('42')
	})

	it('ignores events for a different video', async () => {
		const wrapper = await open()
		const before = calls.length

		for (const handler of socketHandlers['lms_video_track_status'] || []) {
			handler({ video_id: 'ffffffffffffffff', status: 'Ready' })
		}
		await flushPromises()

		expect(calls.length).toBe(before)
		expect(wrapper.emitted('updated')).toBeUndefined()
	})
})
