<template>
	<!-- The student-facing course page. Same data and the same guards as
	     CourseDetail, drawn as a full-width page with the app sidebar dropped;
	     /courses/:courseName keeps the tabbed admin shell untouched.

	     `lms-catalog` is what scopes the palette in styles/catalog.css; without
	     it every --catalog-* variable below resolves to nothing. -->
	<div class="lms-catalog min-h-full bg-surface-base pb-20">
		<CatalogCourseHero :course="course" :is-admin="isAdmin" />

		<div
			class="mx-auto grid w-full max-w-7xl gap-x-10 gap-y-8 px-5 pt-10 sm:px-8 lg:grid-cols-[minmax(0,1fr)_22rem] lg:pt-0"
		>
			<div class="order-2 min-w-0 space-y-8 lg:order-1 lg:mt-10">
				<SkeletonLoader v-if="!course.data" variant="lines" :lines="8" />

				<template v-else>
					<section>
						<div class="mb-4 flex flex-wrap items-end justify-between gap-3">
							<h2 class="text-xl font-semibold text-ink-gray-9">
								{{ __('Course content') }}
							</h2>
							<p v-if="outlineStats" class="text-p-sm text-ink-gray-5">
								{{ outlineStats }}
							</p>
						</div>
						<!-- Keyed on the course, here and below. Related courses now
						     navigate in place, so this page is reused course-to-course,
						     and each of these children captures its `cache` key once at
						     setup — the same hazard the course resource avoids by
						     carrying no cache key at all. Remounting is the cheap fix:
						     it also resets "see more" and "view all" state that would
						     otherwise carry over from the previous course. -->
						<CatalogCourseOutline
							ref="outlineRef"
							:key="course.data.name"
							:courseName="course.data.name"
							:getProgress="Boolean(course.data.membership)"
						/>
					</section>

					<section
						v-if="course.data.description || course.data.instructors?.length"
						class="catalog-panel rounded-2xl border bg-surface-white p-6 sm:p-7"
					>
						<template v-if="course.data.description">
							<h2 class="text-xl font-semibold text-ink-gray-9">
								{{ __('About this course') }}
							</h2>
							<div
								v-html="sanitizeRichHTML(course.data.description)"
								class="ProseMirror prose prose-sm mt-4 max-w-none !whitespace-normal prose-table:table-fixed prose-th:relative prose-th:border prose-th:border-outline-gray-2 prose-th:bg-surface-gray-2 prose-th:p-2 prose-td:relative prose-td:border prose-td:border-outline-gray-2 prose-td:p-2"
							/>
						</template>

						<template v-if="course.data.instructors?.length">
							<div
								v-if="course.data.description"
								class="my-7 h-px bg-outline-gray-2"
							/>
							<p
								class="text-xs font-semibold uppercase tracking-wider text-ink-gray-5"
							>
								{{ creatorLabel }}
							</p>
							<div class="mt-4 flex items-start gap-4">
								<router-link
									v-if="focusedInstructor?.username"
									:to="{
										name: 'Profile',
										params: { username: focusedInstructor.username },
									}"
									class="shrink-0"
								>
									<UserAvatar :user="focusedInstructor" size="2xl" />
								</router-link>
								<UserAvatar
									v-else
									:user="focusedInstructor"
									size="2xl"
									class="shrink-0"
								/>
								<div class="min-w-0">
									<p class="font-semibold text-ink-gray-9">
										{{ focusedInstructor?.full_name }}
									</p>
									<div
										v-if="focusedInstructor?.bio"
										v-html="sanitizeRichHTML(focusedInstructor.bio)"
										class="ProseMirror prose prose-sm mt-1 max-w-none text-ink-gray-6"
									/>
								</div>
							</div>

							<!-- More than one instructor: name the team and let the reader
							     switch which one the block above describes, rather than
							     stacking bios nobody scrolls past. -->
							<div v-if="peers.length" class="mt-5 flex flex-wrap gap-2">
								<button
									v-for="instructor in course.data.instructors"
									:key="instructor.username || instructor.name"
									type="button"
									class="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-p-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--catalog-primary)]"
									:class="
										instructorKey(instructor) === focusedKey
											? 'border-transparent text-white'
											: 'border-outline-gray-2 text-ink-gray-6 hover:text-ink-gray-9'
									"
									:style="
										instructorKey(instructor) === focusedKey
											? { background: 'var(--catalog-primary-ink)' }
											: {}
									"
									:aria-pressed="instructorKey(instructor) === focusedKey"
									@click="focusedKey = instructorKey(instructor)"
								>
									<UserAvatar :user="instructor" size="sm" />
									{{ instructor.full_name }}
								</button>
							</div>
						</template>
					</section>

					<CatalogCourseReviews
						:key="course.data.name"
						:courseName="course.data.name"
						:avg_rating="course.data.rating"
						:membership="course.data.membership || null"
					/>

					<CatalogRelatedCourses
						:key="course.data.name"
						:courseName="course.data.name"
					/>
				</template>
			</div>

			<!-- Pulled up over the hero on wide screens only. Below lg the card
			     stacks under the hero, where a negative margin would drag it into
			     the gradient. -->
			<aside class="order-1 lg:order-2 lg:-mt-28">
				<div class="sticky top-8 space-y-4">
					<CatalogEnrollCard :course="course" />

					<div
						v-if="course.data"
						class="rounded-2xl border bg-surface-gray-1 p-5"
					>
						<p class="text-p-sm font-semibold text-ink-gray-9">
							{{ __('Your progress') }}
						</p>
						<template v-if="progress !== null">
							<div
								class="mt-3 h-2 overflow-hidden rounded-full bg-surface-gray-3"
								role="progressbar"
								:aria-valuenow="progress"
								aria-valuemin="0"
								aria-valuemax="100"
								:aria-label="__('Course progress')"
							>
								<div
									class="h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none"
									:style="{
										width: `${progress}%`,
										background: 'var(--catalog-primary)',
									}"
								/>
							</div>
							<p class="mt-2 text-xs text-ink-gray-6">
								{{ progress }}% {{ __('complete') }}
							</p>
						</template>
						<p v-else class="mt-2 text-xs text-ink-gray-6">
							{{ __('Not started — enroll to track lesson completion.') }}
						</p>
					</div>
				</div>
			</aside>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { createResource, usePageMeta } from 'frappe-ui'
import { useRouter } from 'vue-router'
import { sessionStore } from '@/stores/session'
import { sanitizeRichHTML } from '@/utils/sanitizeRichHTML'
import SkeletonLoader from '@/components/SkeletonLoader.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import CatalogCourseHero from '@/components/Catalog/CatalogCourseHero.vue'
import CatalogCourseOutline from '@/components/Catalog/CatalogCourseOutline.vue'
import CatalogEnrollCard from '@/components/Catalog/CatalogEnrollCard.vue'
import CatalogCourseReviews from '@/components/Catalog/CatalogCourseReviews.vue'
import CatalogRelatedCourses from '@/components/Catalog/CatalogRelatedCourses.vue'
import type {
	CourseDetails,
	CourseInstructorInfo,
	OutlineChapter,
	Resource,
	SessionUser,
} from '@/types'

type Brand = { name?: string; logo?: string; favicon?: string }

const props = defineProps<{ courseName: string }>()

const router = useRouter()
const user = inject<SessionUser>('$user')!
const { brand } = sessionStore() as { brand: Brand }

// No `cache` key: it would be read once at setup, so the reload below — this
// component is reused when you jump straight from one course to another — would
// file the new course's data under the course you arrived on.
const course = createResource({
	url: 'lms.lms.utils.get_course_details',
	makeParams() {
		return { course: props.courseName }
	},
	auto: true,
}) as Resource<CourseDetails | null>

watch(
	() => props.courseName,
	() => course.reload()
)

const isAdmin = computed<boolean>(() => {
	if (user.data?.is_moderator) return true
	return (course.data?.instructors || []).some(
		(instructor: CourseInstructorInfo) => instructor.name === user.data?.name
	)
})

// get_course_details returns {} for a course the viewer may not see, so an
// unpublished course reaching a student here means the URL was guessed.
watch(course, () => {
	if (!isAdmin.value && !course.data?.published && !course.data?.upcoming) {
		router.push({ name: 'Courses' })
	}
})

// The outline is fetched once, by the outline component, and the summary line
// reads its chapters back. CourseOverview fetches it twice to do the same job.
const outlineRef = ref<{
	chapters: OutlineChapter[]
	lessonCount: number
} | null>(null)

const outlineStats = computed<string>(() => {
	const chapters = outlineRef.value?.chapters || []
	const lessonCount = outlineRef.value?.lessonCount || 0
	const parts: string[] = []
	if (chapters.length) {
		parts.push(
			`${chapters.length} ${
				chapters.length === 1 ? __('chapter') : __('chapters')
			}`
		)
	}
	if (lessonCount) {
		parts.push(
			`${lessonCount} ${lessonCount === 1 ? __('lesson') : __('lessons')}`
		)
	}
	return parts.join(' · ')
})

const instructors = computed<CourseInstructorInfo[]>(
	() => course.data?.instructors || []
)

const instructorKey = (instructor: CourseInstructorInfo): string =>
	instructor.username || instructor.name || instructor.full_name || ''

const focusedKey = ref<string>('')

watch(
	instructors,
	(list) => {
		if (!list.length) {
			focusedKey.value = ''
			return
		}
		if (!list.some((i) => instructorKey(i) === focusedKey.value)) {
			focusedKey.value = instructorKey(list[0])
		}
	},
	{ immediate: true }
)

const focusedInstructor = computed<CourseInstructorInfo | undefined>(
	() =>
		instructors.value.find((i) => instructorKey(i) === focusedKey.value) ||
		instructors.value[0]
)

const peers = computed<CourseInstructorInfo[]>(() =>
	instructors.value.filter((i) => instructorKey(i) !== focusedKey.value)
)

const creatorLabel = computed<string>(() => {
	const n = instructors.value.length
	if (n <= 1) return __('Course creator')
	if (n <= 4) return __('Taught by')
	return __('Taught by a team of {0}').format(String(n))
})

const progress = computed<number | null>(() => {
	const value = course.data?.membership?.progress
	if (value === undefined || value === null) return null
	const numeric = Number(value)
	if (!Number.isFinite(numeric)) return null
	return Math.min(100, Math.ceil(numeric))
})

usePageMeta(() => ({
	title: course.data?.title,
	icon: brand.favicon,
}))
</script>
