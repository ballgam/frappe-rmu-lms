import { computed, inject, ref } from 'vue'
import { call, createResource, toast } from 'frappe-ui'
import { useRouter } from 'vue-router'
import { useTelemetry } from 'frappe-ui/frappe'
import {
	canGetCertificate,
	getBillingRoute,
	getContinueRoute,
	getCourseCta,
	getCertificateUrl,
	getEnrolledLabel,
	getPriceLabel,
	isCourseAdmin,
} from '@/utils/courseEnrollment'
import type { CourseDetails, Resource, SessionUser } from '@/types'

type Options = {
	/**
	 * Reload the course after enrolling, before opening lesson 1-1. The catalog
	 * card does, so a learner coming back is not offered "Enroll" again; the
	 * classic card never did, and waits a second so the toast is read.
	 */
	reloadAfterEnroll?: boolean
}

/**
 * Everything an enrolment card does, over the rules in utils/courseEnrollment.
 * Reads `$user` by inject, so Student View's student-shaped user applies.
 */
export function useCourseEnrollment(
	course: Resource<CourseDetails | null>,
	{ reloadAfterEnroll = false }: Options = {}
) {
	const router = useRouter()
	const user = inject<SessionUser>('$user')!
	const { capture } = useTelemetry()

	const data = computed(() => course.data)
	const isAdmin = computed(() => isCourseAdmin(user.data, data.value))
	const cta = computed(() => getCourseCta(data.value, isAdmin.value))
	const continueRoute = computed(() => getContinueRoute(data.value))
	const billingRoute = computed(() => getBillingRoute(data.value))
	const priceLabel = computed(() => getPriceLabel(data.value))
	const enrolledLabel = computed(() =>
		getEnrolledLabel(data.value?.enrollments)
	)
	const certificateAvailable = computed(() => canGetCertificate(data.value))

	const enrolling = ref(false)

	const openFirstLesson = (courseName: string) =>
		router.push({
			name: 'Lesson',
			params: { courseName, chapterNumber: 1, lessonNumber: 1 },
		})

	async function enroll(): Promise<void> {
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
			if (reloadAfterEnroll) {
				await course.reload()
				openFirstLesson(courseName)
			} else {
				setTimeout(() => openFirstLesson(courseName), 1000)
			}
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
			window.open(getCertificateUrl(certificateData), '_blank')
		},
	}) as Resource<{ name: string; template: string } | null>

	function fetchCertificate(): void {
		certificate.submit({ course: data.value?.name, member: user.data?.name })
	}

	return {
		isAdmin,
		cta,
		continueRoute,
		billingRoute,
		priceLabel,
		enrolledLabel,
		certificateAvailable,
		enrolling,
		enroll,
		fetchCertificate,
	}
}
