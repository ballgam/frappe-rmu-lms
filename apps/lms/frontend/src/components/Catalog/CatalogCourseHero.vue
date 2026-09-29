<template>
	<!-- The course page's masthead. Shares .catalog-hero with CatalogHero, so
	     both pages carry the same gradient band and corner light. It sits under
	     the student navbar, which carries the brand and account menu. -->
	<section class="catalog-hero relative overflow-hidden">
		<!-- The cover art as a wash rather than a picture. soft-light keeps the
		     gradient's contrast, so the title below stays legible whatever the
		     image happens to be. -->
		<div
			v-if="data?.image"
			aria-hidden="true"
			class="absolute inset-0 bg-cover bg-center opacity-25 [mix-blend-mode:soft-light]"
			:style="{ backgroundImage: `url(${data.image})` }"
		/>

		<div
			class="relative mx-auto w-full max-w-7xl px-5 pb-24 pt-5 sm:px-8 lg:pb-32"
		>
			<div class="flex items-center justify-between gap-4">
				<router-link
					:to="{ name: 'Courses' }"
					class="-ms-3 inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-p-sm font-medium text-[color:var(--catalog-hero-ink-muted)] transition-colors hover:bg-white/10 hover:text-[color:var(--catalog-hero-ink)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
				>
					<span class="lucide-arrow-left size-4 rtl:rotate-180" />
					{{ __('All courses') }}
				</router-link>
				<!-- Staff previewing in Student View: the way back to the editor,
				     dashboard and settings. Without ?studentView the same URL
				     renders the tabbed admin page. -->
				<router-link
					v-if="isAdmin && data"
					:to="{ name: 'CourseDetail', params: { courseName: data.name } }"
					class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-p-sm font-medium text-[color:var(--catalog-hero-ink)] transition-colors hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
					:style="{
						borderColor: 'var(--catalog-hero-border)',
						background: 'var(--catalog-hero-chip)',
					}"
				>
					<span class="lucide-settings-2 size-4" />
					{{ __('Manage course') }}
				</router-link>
			</div>

			<!-- Held at the hero's own height while the course loads, so the title
			     landing does not shove the page down. -->
			<div v-if="!data" class="mt-6 animate-pulse sm:mt-10">
				<div class="h-6 w-40 rounded-full bg-white/15" />
				<div class="mt-5 h-11 w-full max-w-2xl rounded bg-white/15" />
				<div class="mt-3 h-11 w-2/3 max-w-xl rounded bg-white/15" />
				<div class="mt-6 h-5 w-full max-w-xl rounded bg-white/10" />
				<div class="mt-8 h-5 w-72 rounded bg-white/10" />
			</div>

			<div v-else class="mt-6 sm:mt-10">
				<nav :aria-label="__('Breadcrumb')">
					<ol
						class="flex flex-wrap items-center gap-x-2 gap-y-1 text-p-sm text-[color:var(--catalog-hero-ink-muted)]"
					>
						<li>
							<router-link
								:to="{ name: 'Courses' }"
								class="rounded transition-colors hover:text-[color:var(--catalog-hero-ink)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
							>
								{{ __('Catalog') }}
							</router-link>
						</li>
						<li v-if="data.category" class="flex items-center gap-2">
							<span aria-hidden="true">/</span>
							<router-link
								:to="{
									name: 'Courses',
									query: { category: data.category },
								}"
								class="rounded transition-colors hover:text-[color:var(--catalog-hero-ink)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
							>
								{{ data.category }}
							</router-link>
						</li>
						<li class="flex min-w-0 items-center gap-2">
							<span aria-hidden="true">/</span>
							<span
								class="truncate text-[color:var(--catalog-hero-ink)]"
								aria-current="page"
							>
								{{ data.title }}
							</span>
						</li>
					</ol>
				</nav>

				<div v-if="chips.length" class="mt-5 flex flex-wrap gap-2">
					<span
						v-for="chip in chips"
						:key="chip"
						class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wider text-[color:var(--catalog-hero-ink)]"
						:style="{
							borderColor: 'var(--catalog-hero-border)',
							background: 'var(--catalog-hero-chip)',
						}"
					>
						{{ chip }}
					</span>
				</div>

				<h1
					class="mt-5 max-w-3xl text-4xl font-semibold leading-[1.08] text-[color:var(--catalog-hero-ink)] sm:text-5xl"
				>
					{{ data.title }}
				</h1>
				<p
					v-if="data.short_introduction"
					class="mt-5 max-w-2xl text-p-lg leading-relaxed text-[color:var(--catalog-hero-ink-muted)]"
				>
					{{ data.short_introduction }}
				</p>

				<!-- Every stat is gated on having a value: the mock's row is always
				     full, a real course's is not, and an empty star reads as a
				     zero rating rather than as "not rated yet". -->
				<div
					class="mt-8 flex flex-wrap items-center gap-x-7 gap-y-3 text-p-sm text-[color:var(--catalog-hero-ink-muted)]"
				>
					<span v-if="hasRating" class="flex items-center gap-2">
						<span
							class="lucide-star size-4"
							:style="{ color: 'var(--catalog-accent)' }"
						/>
						<span class="font-semibold text-[color:var(--catalog-hero-ink)]">
							{{ formatRating(data.rating) }}
						</span>
						<span v-if="data.rating_count">
							({{ formatAmount(data.rating_count) }}
							{{ data.rating_count === 1 ? __('rating') : __('ratings') }})
						</span>
					</span>
					<span v-if="data.enrollments" class="flex items-center gap-2">
						<span class="lucide-users size-4" />
						{{ formatAmount(data.enrollments) }}
						{{ data.enrollments === 1 ? __('learner') : __('learners') }}
					</span>
					<span v-if="data.lessons" class="flex items-center gap-2">
						<span class="lucide-book-open size-4" />
						{{ data.lessons }}
						{{ data.lessons === 1 ? __('lesson') : __('lessons') }}
					</span>
					<span v-if="(data.quiz_count || 0) > 0" class="flex items-center gap-2">
						<span class="lucide-help-circle size-4" />
						{{ data.quiz_count }}
						{{ data.quiz_count === 1 ? __('quiz') : __('quizzes') }}
					</span>
					<span class="flex items-center gap-2">
						<span class="lucide-clock size-4" />
						{{ __('Self-paced') }}
					</span>
				</div>

				<div
					v-if="data.instructors?.length"
					class="mt-6 flex items-center gap-3"
				>
					<div class="flex shrink-0 items-center">
						<UserAvatar
							v-for="instructor in data.instructors.slice(0, 3)"
							:key="instructor.username || instructor.name"
							:user="instructor"
							size="md"
							class="-me-2 ring-2 ring-white/40 last:me-0"
						/>
					</div>
					<span
						class="min-w-0 truncate text-p-sm text-[color:var(--catalog-hero-ink-muted)]"
					>
						{{ __('Created by') }}
						<span class="font-medium text-[color:var(--catalog-hero-ink)]">
							{{ instructorLabel }}
						</span>
					</span>
				</div>
			</div>
		</div>
	</section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatAmount, formatRating } from '@/utils'
import UserAvatar from '@/components/UserAvatar.vue'
import type { CourseDetails, Resource } from '@/types'

const props = defineProps<{
	course: Resource<CourseDetails | null>
	/** Adds the way across to the tabbed admin shell on /courses/:courseName. */
	isAdmin?: boolean
}>()

const data = computed(() => props.course.data)

const hasRating = computed(() => Number(data.value?.rating) > 0)

// The mock's badges are level / category / certificate. LMS Course has no level
// field, so the row is category, the course's own tags, and the certificate.
const chips = computed<string[]>(() => {
	const course = data.value
	if (!course) return []
	const values: string[] = []
	if (course.category) values.push(course.category)
	if (course.tags) {
		values.push(...course.tags.split(', ').filter((tag) => tag.trim()))
	}
	if (course.enable_certification) values.push(__('Certificate'))
	return values
})

// Same substitution CatalogCourseCard makes: name the first instructor and
// count the rest, rather than truncating a list nobody can read at this size.
const instructorLabel = computed<string>(() => {
	const instructors = data.value?.instructors ?? []
	if (!instructors.length) return ''
	const [first, ...rest] = instructors
	if (!rest.length) return first.full_name || ''
	if (rest.length === 1) {
		return `${first.first_name} ${__('and')} ${rest[0].first_name}`
	}
	return `${first.first_name} ${__('and')} ${rest.length} ${__('others')}`
})
</script>
