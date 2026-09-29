<template>
	<!-- Held blank until the course lands. Rendering the chain against no data
	     defaults to "Free" and "Enroll now", which then swaps to "Buy this
	     course" the moment a paid course answers. -->
	<div
		v-if="!data"
		class="catalog-panel-float overflow-hidden rounded-2xl border bg-surface-white"
	>
		<div class="aspect-video w-full animate-pulse bg-surface-gray-2" />
		<div class="animate-pulse space-y-4 p-6">
			<div class="h-8 w-24 rounded bg-surface-gray-2" />
			<div class="h-11 w-full rounded bg-surface-gray-2" />
			<div class="h-4 w-3/4 rounded bg-surface-gray-2" />
			<div class="h-4 w-2/3 rounded bg-surface-gray-2" />
		</div>
	</div>

	<div
		v-else
		class="catalog-panel-float overflow-hidden rounded-2xl border bg-surface-white"
	>
		<div class="relative">
			<VideoPreview
				:video-link="data?.video_link"
				:fallback-image="data?.image"
			/>
			<!-- VideoPreview renders nothing at all when there is no video and no
			     playback error, which would leave this card headless. The mock
			     always has media here, so fall back to the cover art. -->
			<img
				v-if="!data?.video_link && data?.image"
				:src="data.image"
				:alt="__('Course cover')"
				class="aspect-video w-full object-cover"
			/>
		</div>

		<div class="p-6">
			<div class="flex items-baseline gap-2">
				<p class="text-3xl font-semibold text-ink-gray-9">{{ priceLabel }}</p>
			</div>
			<p v-if="!data?.paid_course" class="mt-1 text-xs text-ink-gray-5">
				{{ __('Open learning · no payment required') }}
			</p>

			<div v-if="!readOnlyMode" class="mt-5">
				<!-- The order of this chain is the behaviour: enrolled beats paid,
				     paid beats the self-learning block, and an admin falls past
				     every branch to no call to action at all. -->
				<div v-if="data?.membership" class="space-y-2">
					<router-link :to="continueRoute" class="block">
						<Button variant="solid" size="lg" class="w-full">
							<template #prefix>
								<span class="lucide-book-text size-4" />
							</template>
							{{ __('Continue learning') }}
						</Button>
					</router-link>
					<CertificationLinks :courseName="data.name" class="w-full" />
				</div>

				<router-link
					v-else-if="cta === 'billing'"
					:to="billingRoute"
					class="block"
				>
					<Button variant="solid" size="lg" class="w-full">
						<template #prefix>
							<span class="lucide-credit-card size-4" />
						</template>
						{{ __('Buy this course') }}
					</Button>
				</router-link>

				<Badge
					v-else-if="cta === 'contact_admin'"
					theme="blue"
					size="lg"
				>
					{{ __('Contact the Administrator to enroll for this course') }}
				</Badge>

				<Button
					v-else-if="cta === 'enroll'"
					variant="solid"
					size="lg"
					class="w-full"
					:loading="enrolling"
					@click="enroll()"
				>
					<template #prefix>
						<span class="lucide-book-text size-4" />
					</template>
					{{ __('Enroll now') }}
				</Button>

				<Button
					v-if="certificateAvailable"
					variant="subtle"
					size="lg"
					class="mt-2 w-full"
					@click="fetchCertificate()"
				>
					<template #prefix>
						<span class="lucide-graduation-cap size-4" />
					</template>
					{{ __('Get certificate') }}
				</Button>

				<Button
					variant="outline"
					size="lg"
					class="mt-2 w-full"
					@click="shareCourse()"
				>
					<template #prefix>
						<span class="lucide-share-2 size-4" />
					</template>
					{{ __('Share course') }}
				</Button>
			</div>

			<template v-if="hasCourseStats">
				<div class="my-6 h-px bg-outline-gray-2" />
				<p
					class="text-xs font-semibold uppercase tracking-wider text-ink-gray-5"
				>
					{{ __('This course includes') }}
				</p>
				<ul class="mt-4 space-y-3 text-p-sm">
					<li
						v-for="item in includes"
						:key="item.label"
						class="flex items-center gap-3"
					>
						<span
							class="size-4 shrink-0"
							:class="item.icon"
							:style="{ color: 'var(--catalog-primary-ink)' }"
							aria-hidden="true"
						/>
						<span class="text-ink-gray-7">{{ item.label }}</span>
					</li>
				</ul>
			</template>
		</div>
	</div>
</template>

<script setup lang="ts">
/**
 * The catalog's enrolment card.
 *
 * Same call-to-action chain, enrolment call and certificate flow as
 * CourseCardOverlay (both come from useCourseEnrollment), restyled for the
 * catalog, plus a share control.
 */
import { computed } from 'vue'
import { Badge, Button, toast } from 'frappe-ui'
import CertificationLinks from '@/components/CertificationLinks.vue'
import VideoPreview from '@/components/VideoPreview.vue'
import { useCourseEnrollment } from '@/composables/useCourseEnrollment'
import type { CourseDetails, Resource } from '@/types'

const props = defineProps<{
	/** The resource, not its data: every branch below reads course.data
	 *  reactively, and enrolment reloads it in place. */
	course: Resource<CourseDetails | null>
}>()

const readOnlyMode = (window as Window & { read_only_mode?: boolean })
	.read_only_mode

const data = computed(() => props.course.data)

const {
	cta,
	continueRoute,
	billingRoute,
	priceLabel,
	enrolledLabel,
	certificateAvailable,
	enrolling,
	enroll,
	fetchCertificate,
} = useCourseEnrollment(props.course, { reloadAfterEnroll: true })

const includes = computed<{ icon: string; label: string }[]>(() => {
	const course = data.value
	if (!course) return []
	const rows: { icon: string; label: string }[] = []
	if (enrolledLabel.value) {
		rows.push({
			icon: 'lucide-users',
			label: `${enrolledLabel.value} ${__('enrolled')}`,
		})
	}
	if (course.video_link) {
		rows.push({
			icon: 'lucide-monitor-play',
			label: __('On demand course video'),
		})
	}
	if (course.lessons) {
		rows.push({
			icon: 'lucide-book-open',
			label: `${course.lessons} ${
				course.lessons === 1 ? __('lesson') : __('lessons')
			}`,
		})
	}
	if ((course.quiz_count || 0) > 0) {
		rows.push({
			icon: 'lucide-help-circle',
			label: `${course.quiz_count} ${
				course.quiz_count === 1 ? __('quiz topic') : __('quiz topics')
			}`,
		})
	}
	if (course.enable_certification) {
		rows.push({ icon: 'lucide-award', label: __('Certificate of completion') })
	}
	return rows
})

const hasCourseStats = computed<boolean>(() => includes.value.length > 0)

// navigator.share is absent on desktop browsers and navigator.clipboard is
// absent outside a secure context, so neither can be assumed. A dismissed
// share sheet rejects with AbortError — that is the user declining, not a
// failure worth a toast.
async function shareCourse(): Promise<void> {
	const url = window.location.href
	try {
		if (navigator.share) {
			await navigator.share({ title: data.value?.title, url })
			return
		}
		if (navigator.clipboard) {
			await navigator.clipboard.writeText(url)
			toast.success(__('Link copied'))
			return
		}
		toast.warning(__('Copy the address bar to share this course'))
	} catch (err) {
		if ((err as Error)?.name === 'AbortError') return
		toast.warning(__('Could not share this course'))
	}
}
</script>
