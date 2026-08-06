<template>
	<Dialog v-model="show" :options="{ title: __('Audio Tracks'), size: 'xl' }">
		<template #body-content>
			<div class="text-base text-ink-gray-7 mb-4">
				{{
					__(
						'These are the audio tracks found in the uploaded file. Name each one so learners can tell them apart in the player. Renaming is instant — the video is not re-processed.'
					)
				}}
			</div>

			<div v-if="tracks.length" class="space-y-3">
				<div
					class="grid grid-cols-[1fr,10rem,4rem] gap-x-3 text-sm text-ink-gray-5"
				>
					<div>{{ __('Name shown to learners') }}</div>
					<div>{{ __('Language') }}</div>
					<div class="text-center">{{ __('Default') }}</div>
				</div>

				<div
					v-for="track in tracks"
					:key="track.manifest_lang"
					class="grid grid-cols-[1fr,10rem,4rem] gap-x-3 items-center"
				>
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
							:checked="track.is_default"
							@change="setDefault(track)"
						/>
					</div>
				</div>
			</div>

			<div v-else class="text-base text-ink-gray-5">
				{{ __('This video has no separate audio tracks.') }}
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
import { ref, computed, watch } from 'vue'
import { Autocomplete, Button, Dialog, FormControl, call } from 'frappe-ui'
import { AUDIO_LANGUAGES } from '@/utils/languages'

/**
 * Lets an instructor name the audio tracks a video carries.
 *
 * This exists because MP4 and MOV exports almost never carry per-track language
 * tags, so a two-language lecture arrives as "Audio 1" and "Audio 2" and only
 * the person who made it knows which is which.
 *
 * Everything edited here is display metadata, joined to the manifest by a
 * language code that was fixed at packaging time — so saving is a database
 * write, not a re-encode.
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
const error = ref(null)

const languageOptions = computed(() =>
	AUDIO_LANGUAGES.map((language) => ({
		label: `${language.label} (${language.value})`,
		value: language.value,
	}))
)

watch(show, (open) => {
	if (open) load()
})

const load = async () => {
	error.value = null
	try {
		const info = await call('lms.lms.video.api.get_playback_info', {
			video_id: props.videoId,
		})
		tracks.value = (info.audio_tracks || []).map((track) => ({
			manifest_lang: track.manifest_lang,
			label: track.label,
			is_default: track.is_default,
			languageOption: track.language
				? languageOptions.value.find(
						(option) => option.value === track.language
					) || { label: track.language, value: track.language }
				: null,
		}))
	} catch (e) {
		error.value = e.message || String(e)
	}
}

const setDefault = (selected) => {
	tracks.value = tracks.value.map((track) => ({
		...track,
		is_default: track.manifest_lang === selected.manifest_lang,
	}))
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
		emit('updated', result.audio_tracks)
		show.value = false
	} catch (e) {
		error.value = e.message || String(e)
	} finally {
		saving.value = false
	}
}
</script>
