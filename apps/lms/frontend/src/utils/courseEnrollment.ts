/**
 * The rules behind a course's enrolment card, shared by CourseCardOverlay (the
 * classic course page) and CatalogEnrollCard (the student catalog). They used
 * to be copied into both, which is how two cards can quietly disagree about
 * whether a learner is offered "Buy" or "Enroll".
 *
 * Pure functions only, so they can be tested without mounting anything; the
 * side effects (enrolling, fetching a certificate) are in
 * composables/useCourseEnrollment.
 */
import type { CourseDetails, CourseInstructorInfo } from '@/types'

type Course = Partial<CourseDetails> | null | undefined
type User = { name?: string; is_moderator?: boolean } | null | undefined

/** A moderator, or one of this course's instructors. */
export function isCourseAdmin(user: User, course: Course): boolean {
	if (!user) return false
	if (user.is_moderator) return true
	return ((course?.instructors as CourseInstructorInfo[]) || []).some(
		(instructor) => instructor.name === user.name
	)
}

export type CourseCta = 'continue' | 'billing' | 'contact_admin' | 'enroll' | 'none'

/**
 * Which call to action the card shows. The order is the behaviour: enrolled
 * beats paid, paid beats the self-learning block, and an admin who is not
 * enrolled falls past every branch to none at all.
 */
export function getCourseCta(course: Course, isAdmin: boolean): CourseCta {
	if (!course) return 'none'
	if (course.membership) return 'continue'
	if (isAdmin) return 'none'
	if (course.paid_course) return 'billing'
	if (course.disable_self_learning) return 'contact_admin'
	return 'enroll'
}

/** Where "Continue learning" goes. current_lesson is "<chapter>-<lesson>". */
export function getContinueRoute(course: Course) {
	const current = course?.current_lesson
	const [chapterNumber, lessonNumber] = current ? current.split('-') : []
	return {
		name: 'Lesson',
		params: {
			courseName: course?.name,
			chapterNumber: chapterNumber || 1,
			lessonNumber: lessonNumber || 1,
		},
	}
}

export function getBillingRoute(course: Course) {
	return {
		name: 'Billing',
		params: { type: 'course', name: course?.name },
	}
}

export function getPriceLabel(course: Course): string {
	if (course?.paid_course) return course?.price || ''
	return __('Free')
}

/**
 * Bucketed social proof: an exact count reads as precision the number does not
 * have once it is large.
 */
export function getEnrolledLabel(enrollments: number | null | undefined): string {
	const n = enrollments ?? 0
	if (!n) return ''
	if (n < 50) return String(n)
	const tier = n < 1000 ? 50 : 100
	return `${Math.floor(n / tier) * tier}+`
}

export function canGetCertificate(course: Course): boolean {
	return Boolean(
		course?.enable_certification &&
			((course?.membership as { progress?: number } | undefined)?.progress ??
				0) >= 100
	)
}

export function getCertificateUrl(certificate: {
	name: string
	template: string
}): string {
	return `/api/method/frappe.utils.print_format.download_pdf?doctype=LMS+Certificate&name=${
		certificate.name
	}&format=${encodeURIComponent(certificate.template)}`
}
