<template>
	<!-- "My learning" for the new student experience. `lms-catalog` brings the
	     catalog palette the course cards are drawn with. -->
	<div class="lms-catalog min-h-full bg-surface-base pb-16">
		<section class="catalog-hero relative overflow-hidden">
			<div
				class="relative mx-auto flex w-full max-w-7xl flex-wrap items-end justify-between gap-4 px-5 py-10 sm:px-8 sm:py-12"
			>
				<div class="min-w-0">
					<p
						class="text-[0.7rem] font-semibold uppercase tracking-[0.22em] text-[color:var(--catalog-hero-ink-muted)]"
					>
						{{ __('My learning') }}
					</p>
					<h1
						class="mt-3 text-3xl font-light tracking-tight text-[color:var(--catalog-hero-ink)] sm:text-4xl"
					>
						{{ __('Welcome back') }},
						<span class="font-medium">{{ firstName }}</span>
					</h1>
					<p class="mt-2 text-p-base text-[color:var(--catalog-hero-ink-muted)]">
						{{ subtitle }}
					</p>
				</div>
				<button
					type="button"
					class="inline-flex items-center gap-2 rounded-full border px-4 py-2 text-p-sm font-medium text-[color:var(--catalog-hero-ink)] transition-colors hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
					:style="{
						borderColor: 'var(--catalog-hero-border)',
						background: 'var(--catalog-hero-chip)',
					}"
					:aria-label="
						__('View learning streak: {0} days').format(
							streakInfo.data?.current_streak || 0
						)
					"
					@click="emit('open-streak')"
				>
					<span aria-hidden="true">🔥</span>
					{{ streakInfo.data?.current_streak || 0 }}
					{{ __('day streak') }}
				</button>
			</div>
		</section>

		<div class="mx-auto w-full max-w-7xl space-y-12 px-5 pt-8 sm:px-8">
			<!-- Continue learning: the most recently active unfinished course. -->
			<section
				v-if="resumeCourse"
				class="catalog-panel-float -mt-16 overflow-hidden rounded-2xl border bg-surface-white sm:-mt-20"
				:aria-label="__('Continue learning')"
			>
				<div class="flex flex-col sm:flex-row">
					<div class="aspect-video w-full shrink-0 sm:aspect-auto sm:w-72">
						<img
							v-if="resumeCourse.image"
							:src="resumeCourse.image"
							alt=""
							class="size-full object-cover"
						/>
						<div
							v-else
							class="flex size-full min-h-[8rem] items-center justify-center p-4 text-center text-lg font-bold text-white"
							:style="{ backgroundImage: gradientFor(resumeCourse) }"
						>
							{{ resumeCourse.title }}
						</div>
					</div>
					<div class="flex min-w-0 flex-1 flex-col justify-center gap-3 p-6">
						<p
							class="text-xs font-semibold uppercase tracking-wider text-[color:var(--catalog-primary-ink)]"
						>
							{{ __('Continue learning') }}
						</p>
						<h2 class="text-xl font-semibold text-ink-gray-9">
							{{ resumeCourse.title }}
						</h2>
						<div class="flex items-center gap-3">
							<div
								class="h-2 flex-1 overflow-hidden rounded-full bg-surface-gray-3"
								role="progressbar"
								:aria-valuenow="resumeProgress"
								aria-valuemin="0"
								aria-valuemax="100"
								:aria-label="__('Course progress')"
							>
								<div
									class="h-full rounded-full bg-[var(--catalog-primary)]"
									:style="{ width: `${resumeProgress}%` }"
								/>
							</div>
							<span class="shrink-0 text-p-sm font-medium text-ink-gray-7">
								{{ resumeProgress }}%
							</span>
						</div>
						<div>
							<router-link
								:to="getContinueRoute(resumeCourse)"
								class="sx-btn-primary sx-focus inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-p-sm font-semibold"
							>
								<span class="lucide-play size-4" aria-hidden="true" />
								{{ resumeProgress ? __('Resume') : __('Start course') }}
							</router-link>
						</div>
					</div>
				</div>
			</section>

			<UpcomingEvaluations :forHome="true" />
			<UpcomingLiveClasses :myLiveClasses="myLiveClasses" />

			<!-- Enrolled courses -->
			<section v-if="hasEnrollments" :aria-labelledby="'my-courses-heading'">
				<div class="flex flex-wrap items-center justify-between gap-3">
					<h2
						id="my-courses-heading"
						class="text-xl font-semibold text-ink-gray-9"
					>
						{{ __('My courses') }}
					</h2>
					<TabButtons v-model="tab" :buttons="tabButtons" />
				</div>
				<div
					v-if="visibleCourses.length"
					class="mt-5 grid gap-6 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4"
				>
					<CatalogCourseCard
						v-for="course in visibleCourses"
						:key="course.name"
						:course="course"
					/>
				</div>
				<p v-else class="mt-8 text-center text-p-base text-ink-gray-5">
					{{
						tab === 'completed'
							? __('No completed courses yet. Keep going!')
							: __('Nothing in progress right now.')
					}}
				</p>
			</section>

			<!-- Loading enrolled courses -->
			<div
				v-else-if="enrolled.loading && !enrolled.data"
				class="grid gap-6 sm:grid-cols-2 lg:grid-cols-3"
			>
				<div
					v-for="n in 3"
					:key="n"
					class="h-72 animate-pulse rounded-3xl bg-surface-gray-2"
				/>
			</div>

			<!-- Not enrolled in anything yet -->
			<section v-else class="space-y-6">
				<div
					class="catalog-panel rounded-2xl border bg-surface-white px-6 py-10 text-center"
				>
					<span
						class="lucide-book-open mx-auto block size-10 text-[color:var(--catalog-primary-ink)]"
						aria-hidden="true"
					/>
					<h2 class="mt-4 text-xl font-semibold text-ink-gray-9">
						{{ __('Start your first course') }}
					</h2>
					<p class="mt-2 text-p-base text-ink-gray-6">
						{{ __('Courses you enroll in will show up here with your progress.') }}
					</p>
					<router-link
						:to="{ name: 'Courses' }"
						class="sx-btn-primary sx-focus mt-6 inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-p-sm font-semibold"
					>
						{{ __('Browse courses') }}
					</router-link>
				</div>
				<div v-if="suggested.length">
					<h2 class="text-xl font-semibold text-ink-gray-9">
						{{ __('Popular courses') }}
					</h2>
					<div class="mt-5 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
						<CatalogCourseCard
							v-for="course in suggested"
							:key="course.name"
							:course="course"
						/>
					</div>
				</div>
			</section>

			<!-- Batches the learner belongs to. Not linked from the navbar, so this
			     is how a batch learner gets back to theirs. -->
			<section v-if="memberBatches.length">
				<h2 class="text-xl font-semibold text-ink-gray-9">
					{{ __('My batches') }}
				</h2>
				<div class="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
					<router-link
						v-for="batch in memberBatches"
						:key="batch.name"
						:to="{ name: 'BatchDetail', params: { batchName: batch.name } }"
					>
						<BatchCard :batch="batch" />
					</router-link>
				</div>
			</section>
		</div>
	</div>
</template>
<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { createResource, TabButtons } from 'frappe-ui'
import CatalogCourseCard from '@/components/Catalog/CatalogCourseCard.vue'
import BatchCard from '@/pages/Batches/components/BatchCard.vue'
import UpcomingEvaluations from '@/components/UpcomingEvaluations.vue'
import UpcomingLiveClasses from '@/components/UpcomingLiveClasses.vue'
import { getContinueRoute } from '@/utils/courseEnrollment'
import {
	defaultTab,
	groupByProgress,
	pickResumeCourse,
	type LearningTab,
} from '@/utils/myLearning'

defineProps<{
	myLiveClasses: any
	streakInfo: any
	subtitle: string
}>()

const emit = defineEmits<{ 'open-streak': [] }>()

const user = inject<any>('$user')

const firstName = computed(
	() => (user.data?.full_name || '').split(' ')[0] || __('learner')
)

// Most recently active enrolments first; featured or popular courses instead
// when there are none (used for the suggestions below).
const recent = createResource({
	url: 'lms.lms.api.get_my_courses',
	auto: true,
})

// Every enrolled course, with membership progress for the tabs.
const enrolled = createResource({
	url: 'lms.lms.utils.get_courses',
	params: { filters: { enrolled: 1 }, limit_page_length: 120 },
	auto: true,
})

const batches = createResource({
	url: 'lms.lms.api.get_my_batches',
	auto: true,
})

const groups = computed(() => groupByProgress(enrolled.data || []))
const hasEnrollments = computed(() => groups.value.all.length > 0)

const tab = ref<LearningTab>('in_progress')
watch(
	() => enrolled.data,
	(data) => {
		if (data) tab.value = defaultTab(groups.value)
	},
	{ immediate: true }
)

const tabButtons = computed(() => [
	{
		label: `${__('In progress')} (${groups.value.in_progress.length})`,
		value: 'in_progress',
	},
	{
		label: `${__('Completed')} (${groups.value.completed.length})`,
		value: 'completed',
	},
	{ label: `${__('All')} (${groups.value.all.length})`, value: 'all' },
])

const visibleCourses = computed(() => groups.value[tab.value])

const resumeCourse = computed(() => pickResumeCourse(recent.data))
const resumeProgress = computed(() =>
	Math.min(100, Math.round(Number(resumeCourse.value?.membership?.progress) || 0))
)

const suggested = computed(() =>
	(recent.data || []).filter((course: any) => !course.membership)
)

const memberBatches = computed(() =>
	(batches.data || []).filter((batch: any) =>
		batch.students?.includes(user.data?.name)
	)
)

const gradientFor = (course: any) => {
	const color = course.card_gradient?.toLowerCase() || 'blue'
	return `linear-gradient(to top right, black, var(--${color}-400))`
}
</script>
