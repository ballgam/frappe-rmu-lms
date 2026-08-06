<template>
	<iframe
		v-if="videoPreview.type === 'youtube'"
		:src="videoPreview.src"
		:title="__('Video preview')"
		class="min-h-56 w-full rounded-t-md"
		allowfullscreen
	/>
	<video
		v-else-if="videoPreview.type === 'file' && !videoError"
		ref="videoRef"
		:src="usingPackagedVideo ? undefined : videoPreview.src"
		controls
		class="min-h-56 w-full rounded-t-md bg-black object-contain"
		:data-video-source="canonicalVideoSource(videoPreview.src)"
		@error="onVideoError"
	/>
	<img
		v-else-if="videoPreview.type === 'file' && videoError && fallbackImage"
		:src="fallbackImage"
		:alt="__('Video preview')"
		class="min-h-56 w-full rounded-t-md object-cover"
	/>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { canonicalVideoSource, getVideoPreview } from '@/utils/video'

// Shared display for a course/batch preview video. A video_link can be a
// YouTube link (render an embed iframe — NOT a <video>, which is what made batch
// cards fail), an uploaded file path (<video>), or unplayable (fall back to the
// poster image). Used by CourseCardOverlay and BatchOverlay.
const props = defineProps<{
	videoLink?: string | null
	fallbackImage?: string | null
}>()

const videoPreview = computed(() => getVideoPreview(props.videoLink))

// Reset the in-browser playback error whenever the source changes.
const videoError = ref(false)
const videoRef = ref<HTMLVideoElement | null>(null)
const usingPackagedVideo = ref(false)
let player: { attach: Function; destroy: Function } | null = null

watch(
	() => props.videoLink,
	() => {
		videoError.value = false
		usingPackagedVideo.value = false
		player?.destroy()
		player = null
	}
)

/**
 * The browser couldn't decode this preview — try the packaged version before
 * giving up and showing the poster image.
 *
 * Deliberately reactive rather than eager. This component renders once per card
 * in the course catalog, so asking the server about every preview on mount would
 * add a request per card to a listing page. Failing to decode is rare (a .mov or
 * .mkv trailer), and it is exactly the case a package fixes.
 */
const onVideoError = async () => {
	if (usingPackagedVideo.value || !videoRef.value) {
		videoError.value = true
		return
	}

	usingPackagedVideo.value = true
	try {
		const { useShakaPlayer } = await import('@/composables/useShakaPlayer')
		player = useShakaPlayer()
		await player.attach(videoRef.value, { file: videoPreview.value.src })
	} catch {
		videoError.value = true
	}
}
</script>
