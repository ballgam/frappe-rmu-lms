<template>
	<Dialog v-model="show" :options="{ title: __('Audio Tracks'), size: 'xl' }">
		<template #body-content>
			<div class="text-base text-ink-gray-7 mb-4">
				{{
					__(
						'Name each track so learners can tell them apart in the player. Renaming is instant — the video is not re-processed. You can also add a translated narration at any time; only the new track is processed, and the video keeps playing while it is.'
					)
				}}
			</div>

			<div v-if="tracks.length" class="space-y-3">
				<div
					class="grid grid-cols-[1fr,10rem,4rem,2rem] gap-x-3 text-sm text-ink-gray-5"
				>
					<div>{{ __('Name shown to learners') }}</div>
					<div>{{ __('Language') }}</div>
					<div class="text-center">{{ __('Default') }}</div>
					<div></div>
				</div>

				<div v-for="track in tracks" :key="track.manifest_lang">
					<div class="grid grid-cols-[1fr,10rem,4rem,2rem] gap-x-3 items-center">
						<FormControl
							v-model="track.label"
							type="text"
							:placeholder="track.manifest_lang"
						/>
						<Autocomplete
							v-model="track.languageOption"
							:options="languageOptions"
							:placeholder="__('Unknown')"
						/>
						<div class="flex justify-center">
							<input
								type="radio"
								name="default-audio-track"
								class="cursor-pointer"
								:aria-label="__('Make this the default track')"
								:disabled="track.status !== 'Ready'"
								:checked="track.is_default"
								@change="setDefault(track)"
							/>
						</div>
						<div class="flex justify-center">
							<!-- Not while the worker is mid-import on this row, and not
							     while a removal it already accepted is running. -->
							<button
								type="button"
								v-if="canRemove && track.status !== 'Processing' && track.status !== 'Removing'"
								:aria-label="__('Remove this track')"
								:title="__('Remove this track')"
								class="text-ink-gray-5 hover:text-ink-red-3"
								@click="remove(track)"
							>
								<span class="lucide-trash-2 size-4" />
							</button>
						</div>
					</div>

					<!-- A track that is not Ready is not in the manifest yet, so it is
					     invisible to learners. Say so rather than leaving a row that
					     looks finished but never shows up in the player. -->
					<div
						v-if="track.status !== 'Ready'"
						class="mt-1 flex items-center gap-x-2 text-sm"
						:class="
							track.status === 'Failed' ? 'text-ink-red-3' : 'text-ink-gray-5'
						"
					>
						<span
							v-if="track.status === 'Processing' || track.status === 'Pending'"
							class="lucide-loader-circle size-3.5 animate-spin"
						/>
						<span>{{ statusLabel(track) }}</span>
						<Button
							v-if="track.status === 'Failed'"
							variant="subtle"
							size="sm"
							@click="retry(track)"
						>
							{{ __('Retry') }}
						</Button>
					</div>
					<div
						v-if="track.status === 'Failed' && track.error"
						class="mt-1 whitespace-pre-wrap font-mono text-xs text-ink-gray-6 max-h-24 overflow-y-auto"
					>
						{{ track.error }}
					</div>
				</div>
			</div>

			<div v-else-if="!loading" class="text-base text-ink-gray-5">
				{{ __('This video has no separate audio tracks yet.') }}
			</div>

			<!-- ADD A TRACK -->
			<div class="mt-6 border-t border-outline-gray-2 pt-4">
				<div class="font-medium text-ink-gray-8 mb-1">
					{{ __('Add an audio track') }}
				</div>
				<div class="text-sm text-ink-gray-5 mb-3">
					{{
						__(
							'Upload a translated narration as an audio file, or a re-dubbed video to take the audio from. It must run about the same length as this video.'
						)
					}}
				</div>

				<div class="grid grid-cols-[1fr,10rem] gap-x-3 mb-3">
					<FormControl
						v-model="newTrack.label"
						type="text"
						:label="__('Name shown to learners')"
						:placeholder="__('e.g. Somali')"
					/>
					<div>
						<div class="text-xs text-ink-gray-5 mb-1">{{ __('Language') }}</div>
						<Autocomplete
							v-model="newTrack.languageOption"
							:options="languageOptions"
							:placeholder="__('Unknown')"
						/>
					</div>
				</div>

				<FileUploader
					:fileTypes="['audio/*', 'video/*']"
					:uploadArgs="uploadArgs"
					:validateFile="validateFile"
					@success="onUploaded"
					@failure="onUploadFailed"
				>
					<template v-slot="{ progress, uploading, openFileSelector }">
						<Button
							:loading="uploading || adding"
							:disabled="!canAdd"
							@click="openFileSelector"
						>
							{{
								uploading
									? __('Uploading {0}%').format(progress)
									: adding
										? __('Checking the file')
										: __('Upload audio file')
							}}
						</Button>
					</template>
				</FileUploader>

				<div v-if="addError" class="mt-2 text-base text-ink-red-3">
					{{ addError }}
				</div>
			</div>

			<div v-if="error" class="mt-3 text-base text-ink-red-3">
				{{ error }}
			</div>
		</template>
		<template #actions>
			<Button variant="solid" :loading="saving" @click="save">
				{{ __('Save') }}
			</Button>
		</template>
	</Dialog>
</template>
<script setup>
import { ref, computed, watch, onBeforeUnmount, reactive } from 'vue'
import {
	Autocomplete,
	Button,
	Dialog,
	FileUploader,
	FormControl,
	call,
} from 'frappe-ui'
import { AUDIO_LANGUAGES } from '@/utils/languages'
import { initSocket } from '@/socket'

/**
 * Lets an instructor name and manage the audio tracks a video carries.
 *
 * Naming exists because MP4 and MOV exports almost never carry per-track
 * language tags, so a two-language lecture arrives as "Audio 1" and "Audio 2"
 * and only the person who made it knows which is which. Names are display
 * metadata joined to the manifest by a language code fixed at packaging time,
 * so saving them is a database write, not a re-encode.
 *
 * Adding a track is not: it packages the new narration and merges one
 * AdaptationSet into the live manifest. The video itself is never touched, so
 * the row appears here as Processing while learners keep watching uninterrupted.
 */

const show = defineModel()
const emit = defineEmits(['updated'])

const props = defineProps({
	videoId: {
		type: String,
		required: true,
	},
})

const tracks = ref([])
const saving = ref(false)
const loading = ref(false)
const adding = ref(false)
const error = ref(null)
const addError = ref(null)

const newTrack = reactive({ label: '', languageOption: null })

const socket = initSocket()

const languageOptions = computed(() =>
	AUDIO_LANGUAGES.map((language) => ({
		label: `${language.label} (${language.value})`,
		value: language.value,
	}))
)

/**
 * Uploaded through the LMS's own endpoint rather than `/api/method/upload_file`.
 *
 * Frappe's generic uploader refuses every `audio/*` mimetype for users without
 * desk access, which is what course creators in this app are — so a lecture
 * uploads fine and its translated narration comes back 417. `upload_audio_source`
 * gates on "may this user edit this video's tracks" instead, which is the
 * narrower question anyway.
 *
 * `doctype`/`docname` are how that endpoint learns which video this is: the
 * uploader forwards those two fields and nothing else custom.
 */
const uploadArgs = computed(() => ({
	private: true,
	upload_endpoint: '/api/method/lms.lms.video.audio_tracks.upload_audio_source',
	doctype: 'LMS Video',
	docname: props.videoId,
}))

/** Removing the only track would leave the package with no audio at all. */
const canRemove = computed(
	() => tracks.value.filter((track) => track.status !== 'Failed').length > 1
)

const canAdd = computed(
	() => !adding.value && !tracks.value.some((track) => isBusy(track))
)

const isBusy = (track) =>
	track.status === 'Pending' || track.status === 'Processing'

const statusLabel = (track) => {
	if (track.status === 'Failed') return __('Could not be added')
	if (track.status === 'Removing') return __('Removing…')
	if (track.status === 'Processing')
		return track.progress
			? __('Processing {0}%').format(track.progress)
			: __('Processing…')
	return __('Waiting to be processed…')
}

watch(show, (open) => {
	if (open) {
		load()
		socket.on('lms_video_track_status', onTrackStatus)
	} else {
		socket.off('lms_video_track_status', onTrackStatus)
	}
})

onBeforeUnmount(() => {
	socket.off('lms_video_track_status', onTrackStatus)
})

const toRow = (track) => ({
	manifest_lang: track.manifest_lang,
	label: track.label,
	is_default: track.is_default,
	status: track.status,
	origin: track.origin,
	error: track.error,
	progress: 0,
	languageOption: track.language
		? languageOptions.value.find((option) => option.value === track.language) || {
				label: track.language,
				value: track.language,
			}
		: null,
})

const load = async () => {
	error.value = null
	loading.value = true
	try {
		const info = await call('lms.lms.video.api.list_audio_tracks', {
			video_id: props.videoId,
		})
		tracks.value = (info.audio_tracks || []).map(toRow)
	} catch (e) {
		error.value = e.message || String(e)
	} finally {
		loading.value = false
	}
}

/**
 * Keep the list live while the worker runs.
 *
 * A percentage arrives every few seconds and only needs to touch one row; a
 * completed or removed track changes the list itself, so reload and tell the
 * player it has a new manifest to fetch.
 */
const onTrackStatus = async (data) => {
	if (!data || data.video_id !== props.videoId) return

	if (data.status === 'Processing' && data.progress != null) {
		const row = tracks.value.find(
			(track) => track.manifest_lang === data.manifest_lang
		)
		if (row) {
			row.status = 'Processing'
			row.progress = data.progress
		}
		return
	}

	await load()
	if (data.removed || data.status === 'Ready') {
		emit('updated', { tracks: tracks.value, listChanged: true })
	}
}

const setDefault = (selected) => {
	tracks.value = tracks.value.map((track) => ({
		...track,
		is_default: track.manifest_lang === selected.manifest_lang,
	}))
}

const validateFile = (file) => {
	const extension = file.name.split('.').pop().toLowerCase()
	if (!ALLOWED_EXTENSIONS.includes(extension)) {
		return __('Upload an audio file, or a video to take the audio from.')
	}
}

// Mirrors paths.AUDIO_EXTENSIONS + paths.VIDEO_EXTENSIONS on the server, which
// is what actually decides. Checking here only saves an upload that would be
// rejected on arrival — so it must not be narrower than the server's, or it
// blocks files the pipeline would happily have taken.
const ALLOWED_EXTENSIONS = [
	// paths.AUDIO_EXTENSIONS
	'mp3',
	'm4a',
	'aac',
	'wav',
	'flac',
	'ogg',
	'oga',
	'opus',
	'wma',
	'mka',
	// paths.VIDEO_EXTENSIONS
	'mp4',
	'mov',
	'mkv',
	'avi',
	'webm',
	'm4v',
	'mpeg',
	'mpg',
	'wmv',
	'flv',
	'3gp',
]

/**
 * Show why an upload never reached us.
 *
 * Without this the uploader fails silently into its own internal banner and the
 * author is left clicking a button that appears to do nothing — which is exactly
 * how the audio mimetype rejection presented before it was diagnosed.
 */
const onUploadFailed = (uploadError) => {
	adding.value = false
	addError.value =
		uploadError?.message ||
		(typeof uploadError === 'string' ? uploadError : null) ||
		__('The file could not be uploaded.')
}

const onUploaded = async (file) => {
	addError.value = null
	adding.value = true
	try {
		const result = await call('lms.lms.video.audio_tracks.add_audio_track', {
			video_id: props.videoId,
			file_url: file.file_url,
			label: newTrack.label,
			language: newTrack.languageOption?.value || '',
		})
		tracks.value = (result.audio_tracks || []).map(toRow)
		newTrack.label = ''
		newTrack.languageOption = null
	} catch (e) {
		addError.value = e.message || String(e)
	} finally {
		adding.value = false
	}
}

const remove = async (track) => {
	if (
		!window.confirm(
			__('Remove "{0}"? Learners will no longer be able to select it.').format(
				track.label || track.manifest_lang
			)
		)
	)
		return

	error.value = null
	try {
		const result = await call('lms.lms.video.audio_tracks.remove_audio_track', {
			video_id: props.videoId,
			manifest_lang: track.manifest_lang,
		})
		tracks.value = (result.audio_tracks || []).map(toRow)
		emit('updated', { tracks: tracks.value, listChanged: true })
	} catch (e) {
		error.value = e.message || String(e)
	}
}

const retry = async (track) => {
	error.value = null
	try {
		const result = await call('lms.lms.video.audio_tracks.retry_audio_track', {
			video_id: props.videoId,
			manifest_lang: track.manifest_lang,
		})
		tracks.value = (result.audio_tracks || []).map(toRow)
	} catch (e) {
		error.value = e.message || String(e)
	}
}

const save = async () => {
	saving.value = true
	error.value = null
	try {
		const result = await call('lms.lms.video.api.update_audio_tracks', {
			video_id: props.videoId,
			tracks: tracks.value.map((track) => ({
				manifest_lang: track.manifest_lang,
				label: track.label,
				language: track.languageOption?.value || '',
				is_default: track.is_default ? 1 : 0,
			})),
		})
		// Labels only: the track list is unchanged, so the player can patch its
		// menu in place instead of re-fetching the manifest.
		emit('updated', { tracks: result.audio_tracks, listChanged: false })
		show.value = false
	} catch (e) {
		error.value = e.message || String(e)
	} finally {
		saving.value = false
	}
}
</script>
