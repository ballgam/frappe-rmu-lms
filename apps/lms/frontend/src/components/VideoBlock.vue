<template>
	<div>
		<div v-if="quizzes.length && !showQuiz && readOnly" class="leading-6">
			{{
				__('This video contains {0} {1}:').format(
					quizzes.length,
					quizzes.length == 1 ? 'quiz' : 'quizzes'
				)
			}}

			<div
				v-for="(quiz, index) in quizzes"
				:key="`${quiz.quiz}-${index}`"
				class="ps-3 mt-1"
			>
				<span>
					{{ index + 1 }}. <span class="font-semibold"> {{ quiz.quiz }} </span>
				</span>
				{{ __('at {0} minutes').format(formatTimestamp(quiz.time)) }}
			</div>
		</div>

		<!-- Packaging still running. The original upload can be a container the
		     browser cannot decode, so this is a real wait, not a cosmetic one. -->
		<div
			v-if="isProcessing"
			class="rounded-md border border-outline-gray-2 bg-surface-gray-1 p-4 mb-2 text-base"
		>
			<div class="flex items-center gap-x-2 font-medium text-ink-gray-8">
				<span class="lucide-loader-circle size-4 animate-spin" />
				{{ __('Preparing this video for playback') }}
				<span v-if="processingProgress">{{ processingProgress }}%</span>
			</div>
			<div class="mt-1 text-ink-gray-6">
				{{
					__(
						'Audio track selection will be available once processing finishes. You can keep editing in the meantime.'
					)
				}}
			</div>
		</div>

		<!-- Packaging failed. Students silently fall back to the original file;
		     only an author sees why, and only an author can retry. -->
		<div
			v-else-if="hasFailed && !readOnly"
			class="rounded-md border border-outline-red-2 bg-surface-red-1 p-4 mb-2 text-base"
		>
			<div class="font-medium text-ink-red-3">
				{{ __('This video could not be prepared for audio track selection') }}
			</div>
			<div class="mt-1 text-ink-gray-7">
				{{
					__(
						'It is still playing as a normal video, but learners cannot switch audio tracks.'
					)
				}}
			</div>
			<div
				v-if="errorMessage"
				class="mt-2 whitespace-pre-wrap font-mono text-xs text-ink-gray-6 max-h-32 overflow-y-auto"
			>
				{{ errorMessage }}
			</div>
			<Button class="mt-3" :loading="retrying" @click="retryPackaging">
				{{ __('Retry') }}
			</Button>
		</div>

		<div
			v-if="!showQuiz"
			ref="videoContainer"
			class="video-block relative group"
		>
			<video
				@ended="videoEnded"
				@click="togglePlay"
				oncontextmenu="return false"
				class="rounded-md border border-outline-gray-1 cursor-pointer"
				ref="videoRef"
				:poster="poster || undefined"
				:data-video-source="canonicalSource"
			></video>
			<button
				type="button"
				v-if="!playing"
				:aria-label="__('Play video')"
				class="absolute inset-0 flex items-center justify-center cursor-pointer"
				@click="playVideo"
			>
				<div
					class="rounded-full p-4 ps-4.5"
					style="
						background: radial-gradient(
							circle,
							rgba(0, 0, 0, 0.3) 0%,
							rgba(0, 0, 0, 0.4) 50%
						);
					"
				>
					<Play />
				</div>
			</button>
			<div
				class="flex items-center gap-x-2 py-2 px-1 text-ink-base bg-gradient-to-b from-transparent to-black/75 absolute bottom-0 start-0 end-0 mx-auto rounded-md"
				:class="{
					'invisible group-hover:visible': playing,
				}"
			>
				<Button
					variant="ghost"
					class="hover:bg-transparent"
					:label="playing ? __('Pause') : __('Play')"
					@click="togglePlay"
				>
					<template #icon>
						<Play v-if="!playing" class="size-4 text-ink-gray-9" />
						<span v-else class="lucide-pause size-5 text-ink-base" />
					</template>
				</Button>

				<div class="relative flex items-center w-full flex-1">
					<input
						type="range"
						min="0"
						:max="duration"
						step="0.1"
						v-model="currentTime"
						@input="changeCurrentTime"
						:aria-label="__('Seek')"
						class="duration-slider h-1"
					/>
					<!-- QUIZ MARKERS -->
					<div class="absolute top-0 start-0 w-full h-full pointer-events-none">
						<div
							v-for="(quiz, index) in quizzes"
							:key="index"
							:style="getQuizMarkerStyle(quiz.time)"
							class="absolute top-0 h-full w-2 bg-surface-amber-3"
						></div>
					</div>
				</div>

				<span class="text-sm-medium">
					{{ formatSeconds(currentTime) }} / {{ formatSeconds(duration) }}
				</span>

				<!-- The point of the whole packaging pipeline: pick a language. -->
				<Dropdown v-if="audioTracks.length > 1" :options="audioTrackOptions">
					<Button :label="__('Audio track')">
						<template #prefix>
							<span class="lucide-languages size-4 text-ink-base" />
						</template>
						{{ activeAudioLabel }}
					</Button>
				</Dropdown>

				<Dropdown :options="dropdownOptions">
					<Button>{{ playbackSpeedLabel }}</Button>
				</Dropdown>

				<Button
					variant="ghost"
					@click="toggleMute"
					:label="muted ? __('Unmute') : __('Mute')"
					class="hover:bg-transparent"
				>
					<template #icon>
						<span class="lucide-volume-2 size-5 text-ink-base" v-if="!muted" />
						<span class="lucide-volume-x size-5 text-ink-base" v-else />
					</template>
				</Button>
				<Button
					variant="ghost"
					@click="toggleFullscreen"
					:label="__('Toggle fullscreen')"
					class="hover:bg-transparent"
				>
					<template #icon>
						<span class="lucide-maximize size-5 text-ink-base" />
					</template>
				</Button>
			</div>
		</div>
		<Quiz
			v-if="showQuiz"
			:quizName="currentQuiz"
			:inVideo="true"
			:backToVideo="resumeVideo"
		/>
		<div v-if="!readOnly" class="flex items-center gap-x-2">
			<Button @click="showQuizModal = true">
				{{ __('Add Quiz to Video') }}
			</Button>
			<!-- Shown whenever the video is packaged, not only when it already has
			     tracks: a silent recording has none, and adding one is exactly what
			     this opens. -->
			<Button v-if="canManageAudio" @click="showAudioTrackModal = true">
				{{ __('Audio Tracks ({0})').format(audioTracks.length) }}
			</Button>
		</div>
	</div>
	<QuizInVideo
		v-model="showQuizModal"
		:quizzes="quizzes"
		:saveQuizzes="saveQuizzes"
		:duration="duration"
	/>
	<VideoAudioTracks
		v-if="videoId"
		v-model="showAudioTrackModal"
		:videoId="videoId"
		@updated="onTracksUpdated"
	/>
	<Dialog v-model:open="showQuizLoader" size="sm" bare>
		<template #default>
			<div class="flex flex-col space-y-2 p-5 text-base leading-5">
				<span class="font-semibold">
					{{ __('Time for a Quiz') }}
				</span>
				<span>
					{{
						__(
							'Complete the upcoming quiz to continue watching the video. The quiz will open in {0} {1}.'
						).format(quizLoadTimer, quizLoadTimer === 1 ? 'second' : 'seconds')
					}}
				</span>
			</div>
		</template>
	</Dialog>
</template>
<script setup>
import { ref, onMounted, computed, watch, onBeforeUnmount } from 'vue'
import { Button, Dialog, Dropdown, call } from 'frappe-ui'
import { formatSeconds, formatTimestamp } from '@/utils/format'
import { canonicalVideoSource } from '@/utils/video'
import { useSettings } from '@/stores/settings'
import { useShakaPlayer } from '@/composables/useShakaPlayer'
import { initSocket } from '@/socket'
import Play from '@/components/Icons/Play.vue'
// The template has always rendered <Quiz> for the in-video quiz gate but never
// imported it, so the component failed to resolve and the gate rendered nothing.
import Quiz from '@/components/Quiz.vue'
import QuizInVideo from '@/components/Modals/QuizInVideo.vue'
import VideoAudioTracks from '@/components/Modals/VideoAudioTracks.vue'

const videoRef = ref(null)
const videoContainer = ref(null)
let playing = ref(false)
let currentTime = ref(0)
let duration = ref(0)
let muted = ref(false)
const showQuizModal = ref(false)
const showAudioTrackModal = ref(false)
const showQuiz = ref(false)
const showQuizLoader = ref(false)
const quizLoadTimer = ref(0)
const currentQuiz = ref(null)
const nextQuiz = ref({})
const retrying = ref(false)
const processingProgress = ref(0)
const { settings } = useSettings()

// Speed control states
const playbackSpeed = ref(1)
const playbackSpeedLabel = ref('1x')
const playbackSpeeds = [
	{ label: '0.5x', value: 0.5 },
	{ label: '1x', value: 1 },
	{ label: '1.5x', value: 1.5 },
	{ label: '2x', value: 2 },
]

const props = defineProps({
	file: {
		type: String,
		required: true,
	},
	videoId: {
		type: String,
		default: null,
	},
	type: {
		type: String,
		default: 'video/mp4',
	},
	readOnly: {
		type: Boolean,
		default: true,
	},
	quizzes: {
		type: Array,
		default: () => [],
	},
	saveQuizzes: {
		type: Function,
		default: () => {},
	},
})

const {
	attach,
	destroy,
	selectAudioTrack,
	audioTracks,
	status,
	duration: packagedDuration,
	poster,
	errorMessage,
	videoId,
} = useShakaPlayer()

const socket = initSocket()

const isProcessing = computed(() => status.value === 'processing')
const hasFailed = computed(() => status.value === 'failed')

// Tracks can only be managed against a live package: adding one merges into the
// manifest Shaka has just loaded, so there has to be one.
const canManageAudio = computed(() => !!videoId.value && status.value === 'ready')

/**
 * The key every watch-duration record and resume position is stored under.
 *
 * Deliberately derived from the file url rather than read off `<video>.src`:
 * once Shaka attaches, that property is a `blob:` MediaSource url which differs
 * on every load. Computing it this way reproduces exactly what the old
 * progressive player reported, so existing records keep matching.
 */
const canonicalSource = computed(() => canonicalVideoSource(props.file))

const activeAudioLabel = computed(() => {
	const active = audioTracks.value.find((track) => track.active)
	return active?.label ?? __('Audio')
})

const audioTrackOptions = computed(() =>
	audioTracks.value.map((track) => ({
		label: track.label,
		active: track.active,
		onClick: () => selectAudioTrack(track.id),
	}))
)

onMounted(async () => {
	updateCurrentTime()
	updateNextQuiz()
	if (videoRef.value) {
		videoRef.value.playbackRate = 1
	}
	await attach(videoRef.value, { file: props.file, videoId: props.videoId })
	socket.on('lms_video_status', onVideoStatus)
	socket.on('lms_video_track_status', onTrackStatus)
})

onBeforeUnmount(() => {
	socket.off('lms_video_status', onVideoStatus)
	socket.off('lms_video_track_status', onTrackStatus)
	destroy()
})

/**
 * React to the packaging job's progress without a page reload — an instructor
 * who uploads a lecture and keeps editing should see the audio menu appear on
 * its own when the encode finishes.
 */
const onVideoStatus = (data) => {
	if (!data || data.video_id !== videoId.value) return

	if (data.status === 'Packaging' && data.progress) {
		processingProgress.value = data.progress
		return
	}

	if (data.status === 'Ready' || data.status === 'Failed') {
		processingProgress.value = 0
		reload()
	}
}

/**
 * Pick up a track that finished importing after the modal was closed.
 *
 * Authors only. The manifest changed under a learner too, but interrupting a
 * lecture to add a language they did not ask for is worse than letting them
 * find it on their next load.
 */
const onTrackStatus = (data) => {
	if (props.readOnly || showAudioTrackModal.value) return
	if (!data || data.video_id !== videoId.value) return
	if (data.removed || data.status === 'Ready') reload()
}

const reload = async () => {
	const resumeAt = videoRef.value?.currentTime ?? 0
	await attach(videoRef.value, { file: props.file, videoId: videoId.value })
	updateCurrentTime()
	if (videoRef.value && resumeAt) {
		videoRef.value.currentTime = resumeAt
	}
}

const retryPackaging = async () => {
	retrying.value = true
	try {
		await call('lms.lms.video.uploads.retry_packaging', {
			video_id: videoId.value,
		})
		processingProgress.value = 0
		status.value = 'processing'
	} finally {
		retrying.value = false
	}
}

const onTracksUpdated = ({ tracks, listChanged }) => {
	// A track was added or removed, so the manifest itself changed and Shaka has
	// to re-parse it before the new language can be selected.
	if (listChanged) {
		reload()
		return
	}

	// Labels are display-only, so a rename lands without touching the manifest
	// or the currently playing buffer.
	audioTracks.value = audioTracks.value.map((track) => {
		const updated = tracks.find(
			(row) =>
				String(row.manifest_lang).toLowerCase() ===
				String(track.language).toLowerCase()
		)
		return updated ? { ...track, label: updated.label } : track
	})
}

// Shaka reports the real duration only once the manifest is parsed; the
// element's own loadedmetadata can fire before that with NaN, which would put
// every quiz marker at the wrong position.
watch(packagedDuration, (value) => {
	if (value && !duration.value) duration.value = value
})

const updateCurrentTime = () => {
	setTimeout(() => {
		if (!videoRef.value) return
		videoRef.value.onloadedmetadata = () => {
			const value = videoRef.value.duration
			if (Number.isFinite(value)) duration.value = value
		}
		videoRef.value.ontimeupdate = () => {
			currentTime.value = videoRef.value?.currentTime || currentTime.value
			if (currentTime.value >= nextQuiz.value.time) {
				videoRef.value.pause()
				playing.value = false
				videoRef.value.onTimeupdate = null
				currentQuiz.value = nextQuiz.value.quiz
				quizLoadTimer.value = 7
			}
		}
	}, 0)
}

watch(quizLoadTimer, () => {
	if (quizLoadTimer.value > 0) {
		showQuizLoader.value = true
		setTimeout(() => {
			quizLoadTimer.value -= 1
		}, 1000)
	} else {
		showQuizLoader.value = false
		showQuiz.value = true
	}
})

const resumeVideo = (restart = false) => {
	showQuiz.value = false
	currentQuiz.value = null
	updateCurrentTime()
	setTimeout(() => {
		videoRef.value.currentTime = restart ? 0 : currentTime.value
		videoRef.value.play()
		playing.value = true
		updateNextQuiz()
	}, 0)
}

const updateNextQuiz = () => {
	if (!props.quizzes.length) return

	props.quizzes.forEach((quiz) => {
		if (typeof quiz.time == 'string' && quiz.time.includes(':')) {
			let time = quiz.time.split(':')
			let timeInSeconds = parseInt(time[0]) * 60 + parseInt(time[1])
			quiz.time = timeInSeconds
		}
	})

	props.quizzes.sort((a, b) => a.time - b.time)

	const nextQuizIndex = props.quizzes.findIndex(
		(quiz) => quiz.time > currentTime.value
	)
	if (nextQuizIndex !== -1) {
		nextQuiz.value = props.quizzes[nextQuizIndex]
	} else {
		nextQuiz.value = {}
	}
}

const playVideo = () => {
	videoRef.value.play()
	playing.value = true
}

const pauseVideo = () => {
	videoRef.value.pause()
	playing.value = false
}

const togglePlay = () => {
	if (playing.value) {
		pauseVideo()
	} else {
		playVideo()
	}
}

const videoEnded = () => {
	playing.value = false
}

const toggleMute = () => {
	videoRef.value.muted = !videoRef.value.muted
	muted.value = videoRef.value.muted
}

const changeCurrentTime = () => {
	if (
		settings.data?.prevent_skipping_videos &&
		currentTime.value > videoRef.value.currentTime
	)
		return
	videoRef.value.currentTime = currentTime.value
	updateNextQuiz()
}

const toggleFullscreen = () => {
	if (document.fullscreenElement) {
		document.exitFullscreen()
	} else {
		videoContainer.value.requestFullscreen()
	}
}

const getQuizMarkerStyle = (time) => {
	const percentage = ((time - 5) / Math.ceil(duration.value)) * 100
	return {
		insetInlineStart: `${percentage}%`,
	}
}

const setPlaybackSpeed = (speed, label) => {
	playbackSpeed.value = speed
	playbackSpeedLabel.value = label
	if (videoRef.value) {
		videoRef.value.playbackRate = speed
	}
}

const dropdownOptions = computed(() =>
	playbackSpeeds.map((speed) => ({
		label: speed.label,
		active: playbackSpeed.value === speed.value,
		onClick: () => setPlaybackSpeed(speed.value, speed.label),
	}))
)
</script>

<style scoped>
.video-block {
	width: 100%;
	margin: 0 auto;
}

.video-block video {
	width: 100%;
	height: auto;
}

iframe {
	width: 100%;
	min-height: 500px;
}

.duration-slider {
	-webkit-appearance: none;
	appearance: none;
	border-radius: 10px;
	background-color: theme('colors.gray.600');
	cursor: pointer;
}

.duration-slider::-webkit-slider-thumb {
	width: 2px;
	border-radius: 50%;
	-webkit-appearance: none;
	background-color: theme('colors.white');
}

@media screen and (-webkit-min-device-pixel-ratio: 0) {
	input[type='range'] {
		overflow: hidden;
		width: 100%;
		-webkit-appearance: none;
	}

	input[type='range']::-webkit-slider-thumb {
		-webkit-appearance: none;
		cursor: pointer;
		box-shadow: -500px 0 0 500px theme('colors.white');
	}
}
</style>
