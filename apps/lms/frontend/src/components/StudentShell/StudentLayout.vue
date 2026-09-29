<template>
	<!-- The student shell: a top navbar instead of the app sidebar, and on a
	     phone a bottom tab bar. h-dvh for the same reason as MobileLayout: 100vh
	     is the URL-bar-retracted viewport, which would push the tab bar off
	     screen. -->
	<div class="relative flex h-dvh flex-col bg-surface-base">
		<a
			href="#scrollContainer"
			@click.prevent="skipToContent('scrollContainer')"
			class="sr-only focus:not-sr-only focus:absolute focus:start-4 focus:top-4 focus:z-50 focus:rounded focus:bg-surface-base focus:px-4 focus:py-2 focus:text-ink-gray-9 focus:shadow-md focus:outline-none focus:ring-2 focus:ring-outline-gray-3"
		>
			{{ __('Skip to main content') }}
		</a>

		<StudentNavbar class="shrink-0" />

		<!-- #scrollContainer is the id the other layouts give their scroll area;
		     pages and the skip link rely on it. -->
		<main
			id="scrollContainer"
			tabindex="-1"
			class="flex min-h-0 flex-1 flex-col overflow-y-auto focus:outline-none"
		>
			<slot />
		</main>

		<StudentBottomTabs v-if="isMobile && !isPlayer" class="shrink-0" />
	</div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { skipToContent } from '@/utils/a11y'
import { useScreenSize } from '@/utils/composables'
import StudentNavbar from '@/components/StudentShell/StudentNavbar.vue'
import StudentBottomTabs from '@/components/StudentShell/StudentBottomTabs.vue'

const route = useRoute()
const { isMobile } = useScreenSize()

// The lesson player needs the whole height on a phone; it has its own
// prev/next and curriculum controls, so the tab bar would only crowd it.
const isPlayer = computed(() =>
	['Lesson', 'SCORMChapter'].includes(String(route.name))
)
</script>
