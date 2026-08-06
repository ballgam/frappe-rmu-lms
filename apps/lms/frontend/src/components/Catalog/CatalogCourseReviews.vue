<template>
	<section
		v-if="reviews.data?.length || membership"
		class="catalog-panel rounded-2xl border bg-surface-white p-6 sm:p-7"
	>
		<div class="flex flex-wrap items-start justify-between gap-4">
			<h2 class="text-xl font-semibold text-ink-gray-9">
				{{ __('Learner reviews') }}
			</h2>
			<Button v-if="membership && !hasReviewed.data" @click="openReviewModal()">
				{{ __('Write a review') }}
			</Button>
		</div>

		<!-- Only drawn once there is something to distribute. An all-zero
		     histogram reads as five one-star ratings rather than as no ratings. -->
		<div v-if="total" class="mt-6 flex flex-wrap items-center gap-x-8 gap-y-6">
			<div>
				<p class="text-4xl font-semibold text-ink-gray-9">
					{{ avg_rating ? formatRating(avg_rating) : '0' }}
				</p>
				<div class="mt-1 flex gap-0.5">
					<span
						v-for="i in 5"
						:key="i"
						class="lucide-star size-4"
						:style="{
							color:
								i <= Math.round(Number(avg_rating) || 0)
									? 'var(--catalog-accent)'
									: 'var(--outline-gray-2)',
						}"
						aria-hidden="true"
					/>
				</div>
				<p class="mt-1 text-xs text-ink-gray-5">
					{{ total }} {{ total === 1 ? __('rating') : __('ratings') }}
				</p>
			</div>

			<ul class="min-w-[15rem] flex-1 space-y-2">
				<li
					v-for="row in distribution"
					:key="row.stars"
					class="flex items-center gap-3 text-xs text-ink-gray-6"
				>
					<span class="w-10 shrink-0">
						{{ row.stars }} {{ row.stars === 1 ? __('star') : __('stars') }}
					</span>
					<span
						class="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-gray-2"
						role="img"
						:aria-label="`${row.stars} ${
							row.stars === 1 ? __('star') : __('stars')
						}: ${row.pct}%`"
					>
						<span
							class="block h-full rounded-full"
							:style="{
								width: `${row.pct}%`,
								background: 'var(--catalog-accent)',
							}"
						/>
					</span>
					<span class="w-9 shrink-0 text-end tabular-nums">{{ row.pct }}%</span>
				</li>
			</ul>
		</div>

		<template v-if="visibleReviews.length">
			<div class="my-7 h-px bg-outline-gray-2" />
			<ul class="space-y-7">
				<li
					v-for="review in visibleReviews"
					:key="review.name"
					class="flex gap-4"
				>
					<router-link
						:to="{
							name: 'Profile',
							params: { username: review.owner_details.username },
						}"
						class="shrink-0"
					>
						<UserAvatar :user="review.owner_details" size="2xl" />
					</router-link>
					<div class="min-w-0 flex-1">
						<div class="flex flex-wrap items-center gap-x-3">
							<router-link
								:to="{
									name: 'Profile',
									params: { username: review.owner_details.username },
								}"
								class="truncate font-semibold text-ink-gray-9 hover:underline"
							>
								{{ review.owner_details.full_name }}
							</router-link>
							<span class="text-xs text-ink-gray-5">
								{{ formatReviewDate(review.creation) }}
							</span>
						</div>
						<div class="mt-1 flex gap-0.5">
							<span
								v-for="i in 5"
								:key="i"
								class="lucide-star size-3.5"
								:style="{
									color:
										i <= Math.ceil(review.rating)
											? 'var(--catalog-accent)'
											: 'var(--outline-gray-2)',
								}"
								aria-hidden="true"
							/>
						</div>
						<p
							v-if="review.review"
							class="mt-2 text-p-sm leading-relaxed text-ink-gray-7"
							:class="{ 'line-clamp-5': !expanded[review.name] }"
						>
							{{ review.review }}
						</p>
						<button
							v-if="review.review && isClampable(review.review)"
							type="button"
							class="mt-1 rounded text-p-sm font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--catalog-primary)]"
							:style="{ color: 'var(--catalog-primary-ink)' }"
							@click="toggleExpand(review.name)"
						>
							{{ expanded[review.name] ? __('See less') : __('See more') }}
						</button>
					</div>
				</li>
			</ul>

			<Button
				v-if="canShowMore"
				class="mt-6 w-full"
				size="md"
				@click="showAll = true"
			>
				{{ __('View all reviews') }}
			</Button>
		</template>

		<p v-else-if="membership" class="mt-6 text-p-sm text-ink-gray-5">
			{{ __('No reviews yet. Be the first to review this course.') }}
		</p>
	</section>

	<ReviewModal
		v-model="showReviewModal"
		v-model:reloadReviews="reviews"
		v-model:hasReviewed="hasReviewed"
		:courseName="courseName"
	/>
</template>

<script setup lang="ts">
/**
 * The catalog's reviews block. Same three resources and the same ReviewModal
 * wiring as CourseReviews — the modal takes both resources as v-models and
 * reloads them after posting, so that binding has to stay intact — plus the
 * mock's rating histogram, which is derived here rather than fetched.
 */
import { computed, inject, reactive, ref, watch } from 'vue'
import { Button, createResource } from 'frappe-ui'
import UserAvatar from '@/components/UserAvatar.vue'
import ReviewModal from '@/components/Modals/ReviewModal.vue'
import { formatRating } from '@/utils'
import type dayjsType from 'dayjs'
import type {
	CourseReviewInfo,
	Membership,
	Resource,
	SessionUser,
} from '@/types'

const PREVIEW_LIMIT = 4
const CLAMP_THRESHOLD = 220

const props = defineProps<{
	courseName: string
	avg_rating?: string
	membership?: Membership | null
}>()

const user = inject<SessionUser>('$user')!
const dayjs = inject<typeof dayjsType>('$dayjs')!

const hasReviewed = createResource({
	url: 'frappe.client.get_count',
	cache: ['eligible_to_review', props.courseName, props.membership?.member],
	params: {
		doctype: 'LMS Course Review',
		filters: { course: props.courseName, owner: props.membership?.member },
	},
	auto: user.data?.name ? true : false,
}) as Resource<number | null>

const reviews = createResource({
	url: 'lms.lms.utils.get_reviews',
	cache: ['course_reviews', props.courseName],
	makeParams() {
		return { course: props.courseName }
	},
	auto: true,
}) as Resource<CourseReviewInfo[] | null>

watch(
	() => props.courseName,
	() => reviews.reload()
)

const showReviewModal = ref(false)
const showAll = ref(false)
const expanded = reactive<Record<string, boolean>>({})

// owner_details comes back null for guest-authored or deleted-user reviews,
// and the row below dereferences it for the avatar and the profile link.
const allReviews = computed<CourseReviewInfo[]>(() =>
	(reviews.data || []).filter((r) => r.owner_details)
)

const visibleReviews = computed<CourseReviewInfo[]>(() =>
	showAll.value ? allReviews.value : allReviews.value.slice(0, PREVIEW_LIMIT)
)

const canShowMore = computed<boolean>(
	() => !showAll.value && allReviews.value.length > PREVIEW_LIMIT
)

const total = computed<number>(() => reviews.data?.length || 0)

// get_reviews already scales the stored 0–1 fraction to 0–5, and returns every
// review, so the distribution is a count over what is already in hand.
// Math.ceil buckets it the same way the star rows fill.
const distribution = computed(() =>
	[5, 4, 3, 2, 1].map((stars) => {
		const count = (reviews.data || []).filter(
			(r) => Math.ceil(r.rating) === stars
		).length
		return {
			stars,
			count,
			pct: total.value ? Math.round((count / total.value) * 100) : 0,
		}
	})
)

function isClampable(text: string): boolean {
	return text.length > CLAMP_THRESHOLD
}

function toggleExpand(name: string): void {
	expanded[name] = !expanded[name]
}

function formatReviewDate(date: string): string {
	if (!date) return ''
	const d = dayjs(date)
	const months = dayjs().diff(d, 'month')
	if (months >= 1) {
		return `${months} ${months === 1 ? __('month ago') : __('months ago')}`
	}
	const days = dayjs().diff(d, 'day')
	if (days >= 1) {
		return `${days} ${days === 1 ? __('day ago') : __('days ago')}`
	}
	return __('Today')
}

function openReviewModal(): void {
	showReviewModal.value = true
}
</script>
