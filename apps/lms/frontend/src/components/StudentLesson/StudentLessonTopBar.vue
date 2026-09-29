<template>
	<!-- The lesson player's top bar for the new student experience: back to the
	     course, where you are, your progress, and prev / next. Presentational
	     only; Lesson.vue owns every action it emits. -->
	<div
		class="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-outline-gray-2 bg-surface-white px-3 sm:px-5"
	>
		<router-link
			:to="{ name: 'CourseDetail', params: { courseName }, query: previewQuery }"
			class="sx-focus grid size-9 shrink-0 place-items-center rounded-full text-ink-gray-7 hover:bg-surface-gray-2"
			:aria-label="__('Back to course')"
		>
			<span class="lucide-arrow-left size-5 rtl:rotate-180" aria-hidden="true" />
		</router-link>

		<div class="min-w-0 flex-1">
			<p class="truncate text-p-xs text-ink-gray-5">{{ courseTitle }}</p>
			<p class="truncate text-p-sm font-semibold text-ink-gray-9">
				{{ lessonTitle }}
			</p>
		</div>

		<!-- Progress ring -->
		<div
			class="hidden shrink-0 items-center gap-2 sm:flex"
			role="progressbar"
			:aria-valuenow="percent"
			aria-valuemin="0"
			aria-valuemax="100"
			:aria-label="__('Course progress')"
		>
			<svg viewBox="0 0 36 36" class="size-8 -rotate-90" aria-hidden="true">
				<circle
					cx="18"
					cy="18"
					r="15.5"
					fill="none"
					stroke-width="3.5"
					class="stroke-[var(--sx-primary-soft)]"
				/>
				<circle
					cx="18"
					cy="18"
					r="15.5"
					fill="none"
					stroke-width="3.5"
					stroke-linecap="round"
					class="stroke-[var(--sx-primary)] transition-[stroke-dashoffset] duration-500"
					:stroke-dasharray="circumference"
					:stroke-dashoffset="circumference * (1 - percent / 100)"
				/>
			</svg>
			<span class="text-p-xs font-medium tabular-nums text-ink-gray-7">
				{{ percent }}%
			</span>
		</div>

		<slot name="actions" />

		<div class="flex shrink-0 items-center gap-1">
			<button
				type="button"
				class="sx-focus grid size-9 place-items-center rounded-full text-ink-gray-7 hover:bg-surface-gray-2 disabled:opacity-40 disabled:hover:bg-transparent"
				:disabled="!hasPrev"
				:aria-label="__('Previous lesson')"
				@click="emit('prev')"
			>
				<span class="lucide-chevron-left size-5 rtl:rotate-180" aria-hidden="true" />
			</button>
			<button
				type="button"
				class="sx-focus grid size-9 place-items-center rounded-full text-ink-gray-7 hover:bg-surface-gray-2 disabled:opacity-40 disabled:hover:bg-transparent"
				:disabled="!hasNext"
				:aria-label="__('Next lesson')"
				@click="emit('next')"
			>
				<span class="lucide-chevron-right size-5 rtl:rotate-180" aria-hidden="true" />
			</button>
			<button
				v-if="canZen"
				type="button"
				class="sx-focus hidden size-9 place-items-center rounded-full text-ink-gray-7 hover:bg-surface-gray-2 md:grid"
				:aria-label="__('Zen Mode')"
				@click="emit('zen')"
			>
				<span class="lucide-focus size-5" aria-hidden="true" />
			</button>
			<button
				type="button"
				class="sx-focus inline-flex h-9 items-center gap-2 rounded-full px-3 text-p-sm font-medium text-ink-gray-8 hover:bg-surface-gray-2"
				:aria-expanded="curriculumOpen"
				:aria-label="__('Course content')"
				@click="emit('toggle-curriculum')"
			>
				<span class="lucide-list size-5" aria-hidden="true" />
				<span class="hidden lg:inline">{{ __('Course content') }}</span>
			</button>
		</div>
	</div>
</template>
<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
	courseName: string
	courseTitle?: string
	lessonTitle?: string
	progress?: number | string | null
	hasPrev: boolean
	hasNext: boolean
	curriculumOpen: boolean
	canZen?: boolean
	/** Carries ?studentView back to the course page for staff previewing. */
	previewQuery?: Record<string, unknown>
}>()

const emit = defineEmits<{
	prev: []
	next: []
	zen: []
	'toggle-curriculum': []
}>()

const circumference = 2 * Math.PI * 15.5

const percent = computed(() =>
	Math.max(0, Math.min(100, Math.round(Number(props.progress) || 0)))
)
</script>
