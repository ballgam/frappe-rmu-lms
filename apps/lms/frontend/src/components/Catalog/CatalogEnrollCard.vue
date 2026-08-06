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
					v-else-if="data?.paid_course && !isAdmin"
					:to="{
						name: 'Billing',
						params: { type: 'course', name: data.name },
					}"
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
					v-else-if="data?.disable_self_learning && !isAdmin"
					theme="blue"
					size="lg"
				>
					{{ __('Contact the Administrator to enroll for this course') }}
				</Badge>

				<Button
					v-else-if="!isAdmin"
					variant="solid"
					size="lg"
					class="w-full"
					:loading="enrolling"
					@click="enrollStudent()"
				>
					<template #prefix>
						<span class="lucide-book-text size-4" />
					</template>
					{{ __('Enroll now') }}
				</Button>

				<Button
					v-if="canGetCertificate"
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
 * CourseCardOverlay, restyled for the catalog. Two additions the mock has and
 * that card does not: a progress bar (CourseCardOverlay only reads
 * membership.progress to gate the certificate button) and a share control.
 */
import { computed, inject, ref } from 'vue'
import { Badge, Button, call, createResource, toast } from 'frappe-ui'
import { useRouter } from 'vue-router'
import { useTelemetry } from 'frappe-ui/frappe'
import CertificationLinks from '@/components/CertificationLinks.vue'
import VideoPreview from '@/components/VideoPreview.vue'
import type {
	CourseDetails,
	CourseInstructorInfo,
	Resource,
	SessionUser,
} from '@/types'

const props = defineProps<{
	/** The resource, not its data: every branch below reads course.data
	 *  reactively, and enrolment reloads it in place. */
	course: Resource<CourseDetails | null>
}>()

const router = useRouter()
const user = inject<SessionUser>('$user')!
const readOnlyMode = (window as Window & { read_only_mode?: boolean })
	.read_only_mode
const { capture } = useTelemetry()

const enrolling = ref(false)

const data = computed(() => props.course.data)

const isAdmin = computed<boolean>(() => {
	if (user.data?.is_moderator) return true
	return (data.value?.instructors || []).some(
		(instructor: CourseInstructorInfo) => instructor.name === user.data?.name
	)
})

// current_lesson is a "<chapter>-<lesson>" index, not a docname.
const continueRoute = computed(() => {
	const [chapterNumber, lessonNumber] = (
		data.value?.current_lesson || ''
	).split('-')
	return {
		name: 'Lesson',
		params: {
			courseName: data.value?.name,
			chapterNumber: chapterNumber || 1,
			lessonNumber: lessonNumber || 1,
		},
	}
})

const priceLabel = computed<string>(() => {
	if (data.value?.paid_course) return data.value?.price || ''
	return __('Free')
})

// Bucketed social proof: an exact count reads as precision the number does not
// have once it is large.
const enrolledLabel = computed<string>(() => {
	const n = data.value?.enrollments ?? 0
	if (!n) return ''
	if (n < 50) return String(n)
	const tier = n < 1000 ? 50 : 100
	return `${Math.floor(n / tier) * tier}+`
})

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

const canGetCertificate = computed<boolean>(() =>
	Boolean(
		data.value?.enable_certification &&
			(data.value?.membership?.progress ?? 0) >= 100
	)
)

async function enrollStudent(): Promise<void> {
	if (!user.data) {
		toast.warning(__('You need to login first to enroll for this course'))
		setTimeout(() => {
			window.location.href = `/login?redirect-to=${window.location.pathname}`
		}, 500)
		return
	}
	const courseName = data.value?.name
	if (!courseName) return

	enrolling.value = true
	try {
		await call('frappe.client.insert', {
			doc: {
				doctype: 'LMS Enrollment',
				course: courseName,
				member: user.data.name,
			},
		})
		capture('enrolled_in_course', { course: courseName })
		toast.success(__('You have been enrolled in this course'))
		// CourseCardOverlay never reloads, because it always navigates away —
		// which leaves this card reading "Enroll now" for anyone who comes back.
		await props.course.reload()
		router.push({
			name: 'Lesson',
			params: { courseName, chapterNumber: 1, lessonNumber: 1 },
		})
	} catch (err) {
		const error = err as { messages?: string[] } | string
		const msg =
			typeof error === 'string' ? error : error.messages?.[0] ?? 'Error'
		toast.warning(__(msg))
		console.error(err)
	} finally {
		enrolling.value = false
	}
}

const certificate = createResource({
	url: 'lms.lms.doctype.lms_certificate.lms_certificate.create_certificate',
	makeParams(values: { course?: string }) {
		return { course: values.course }
	},
	onSuccess(certificateData: { name: string; template: string }) {
		window.open(
			`/api/method/frappe.utils.print_format.download_pdf?doctype=LMS+Certificate&name=${
				certificateData.name
			}&format=${encodeURIComponent(certificateData.template)}`,
			'_blank'
		)
	},
}) as Resource<{ name: string; template: string } | null>

function fetchCertificate(): void {
	certificate.submit({ course: data.value?.name, member: user.data?.name })
}

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
