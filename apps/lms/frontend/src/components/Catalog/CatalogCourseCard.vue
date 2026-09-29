<template>
	<router-link
		:to="{ name: 'CourseDetail', params: { courseName: course.name } }"
		class="catalog-course-card-link group block h-full rounded-3xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--catalog-primary)] focus-visible:ring-offset-2"
	>
		<article
			class="catalog-course-card flex h-full flex-col overflow-hidden rounded-3xl border bg-surface-white"
		>
			<div class="relative aspect-[16/9] overflow-hidden">
				<img
					v-if="course.image"
					:src="course.image"
					alt=""
					loading="lazy"
					class="size-full object-cover transition-transform duration-500 motion-safe:group-hover:scale-105"
				/>
				<!-- No cover image: the title becomes the artwork, on the course's
				     own gradient. Carrying the title here rather than leaving a
				     blank rectangle is the behaviour the current card already has. -->
				<div
					v-else
					class="flex size-full items-center justify-center px-5 text-center font-extrabold leading-tight text-white"
					:class="titleArtSize"
					:style="{ backgroundImage: gradient }"
				>
					{{ course.title }}
				</div>

				<span
					v-if="course.category"
					class="absolute start-4 top-4 rounded-full bg-surface-white/90 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-ink-gray-8 backdrop-blur"
				>
					{{ course.category }}
				</span>
				<span
					class="absolute end-4 top-4 rounded-full px-3 py-1 text-xs font-semibold backdrop-blur"
					:class="
						course.paid_course
							? 'bg-[color:var(--catalog-accent)] text-[#1a1200]'
							: 'bg-black/70 text-white'
					"
				>
					{{ priceLabel }}
				</span>
				<span
					v-if="course.featured"
					class="absolute bottom-4 start-4 inline-flex items-center gap-1 rounded-full bg-black/70 px-2.5 py-1 text-xs font-semibold text-white backdrop-blur"
				>
					<span class="lucide-award size-3.5" />
					{{ __('Featured') }}
				</span>
			</div>

			<div class="flex flex-1 flex-col gap-4 p-5">
				<div
					class="flex items-center gap-4 text-xs font-medium text-ink-gray-6"
				>
					<span v-if="course.lessons" class="inline-flex items-center gap-1.5">
						<span class="lucide-book-open size-3.5 shrink-0" />
						{{ course.lessons }} {{ __('lessons') }}
					</span>
					<span
						v-if="course.enrollments"
						class="inline-flex items-center gap-1.5"
					>
						<span class="lucide-users size-3.5 shrink-0" />
						{{ formatAmount(course.enrollments) }}
					</span>
					<span
						v-if="Number(course.rating) > 0"
						class="ms-auto inline-flex items-center gap-1.5 font-semibold text-ink-gray-9"
					>
						<span
							class="lucide-star size-3.5 shrink-0"
							:style="{ color: 'var(--catalog-accent)' }"
						/>
						{{ formatRating(course.rating) }}
					</span>
				</div>

				<div class="min-w-0 space-y-1.5">
					<h3 class="text-lg font-semibold leading-snug text-ink-gray-9">
						{{ course.title }}
					</h3>
					<p
						v-if="course.short_introduction"
						class="line-clamp-2 text-p-sm leading-relaxed text-ink-gray-6"
					>
						{{ course.short_introduction }}
					</p>
				</div>

				<div v-if="progress !== null" class="space-y-1.5">
					<div
						class="flex items-center justify-between text-xs font-medium text-ink-gray-6"
					>
						<span>{{ __('In progress') }}</span>
						<span>{{ progress }}%</span>
					</div>
					<div
						class="h-1.5 overflow-hidden rounded-full bg-surface-gray-2"
						role="progressbar"
						:aria-valuenow="progress"
						aria-valuemin="0"
						aria-valuemax="100"
						:aria-label="__('Course progress')"
					>
						<div
							class="h-full rounded-full transition-[width] duration-500"
							:style="{
								width: `${progress}%`,
								background: 'var(--catalog-primary)',
							}"
						/>
					</div>
				</div>

				<div class="mt-auto flex items-center gap-3 border-t pt-4">
					<!-- Plain avatars and plain text: the whole card is already a
					     link, and an <a> inside an <a> is invalid markup that the
					     browser silently unnests. The instructor's profile is one
					     click further in, from the course page. -->
					<div class="flex shrink-0 items-center">
						<UserAvatar
							v-for="instructor in course.instructors?.slice(0, 3)"
							:key="instructor.username || instructor.name"
							:user="instructor"
							size="sm"
							class="-me-2 ring-2 ring-surface-white last:me-0"
						/>
					</div>
					<span class="min-w-0 truncate text-p-sm font-medium text-ink-gray-7">
						{{ instructorLabel }}
					</span>
					<span
						v-if="course.paid_certificate || course.enable_certification"
						class="lucide-graduation-cap ms-auto size-4 shrink-0 text-ink-gray-6"
						:title="__('Certificate available')"
					/>
				</div>
			</div>
		</article>
	</router-link>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { formatAmount, formatRating } from '@/utils'

const props = defineProps<{ course: Record<string, any> }>()

const priceLabel = computed<string>(() =>
	props.course.paid_course ? props.course.price : __('Free')
)

// `membership` is scoped to the session user by get_courses. A 0% enrollment
// is intentionally kept quiet until the learner has started the course.
const progress = computed<number | null>(() => {
	const value = props.course.membership?.progress
	if (value === undefined || value === null) return null

	const numericValue = Number(value)
	if (!Number.isFinite(numericValue) || numericValue <= 0) return null

	return Math.min(100, Math.ceil(numericValue))
})

const gradient = computed<string>(() => {
	const color = props.course.card_gradient?.toLowerCase() || 'blue'
	return `linear-gradient(to top right, black, var(--${color}-400))`
})

const titleArtSize = computed<string>(() => {
	const length = props.course.title?.length ?? 0
	if (length > 32) return 'text-lg'
	if (length > 20) return 'text-2xl'
	return 'text-3xl'
})

// The mock has one instructor; a course can have several. Name the first and
// count the rest, rather than truncating a list nobody can read at this size.
const instructorLabel = computed<string>(() => {
	const instructors = props.course.instructors ?? []
	if (!instructors.length) return ''
	const [first, ...rest] = instructors
	if (!rest.length) return first.full_name
	if (rest.length === 1) return `${first.first_name} ${__('and')} ${rest[0].first_name}`
	return `${first.first_name} ${__('and')} ${rest.length} ${__('others')}`
})
</script>
