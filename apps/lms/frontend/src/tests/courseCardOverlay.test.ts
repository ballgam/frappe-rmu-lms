/**
 * CourseCardOverlay.vue — the enrolment card on the classic course page.
 *
 * Staff and (with the new student experience off) learners both see it, so its
 * call-to-action chain, enrolment call and certificate flow are pinned here
 * before the logic is shared with the catalog's enrolment card.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const push = vi.fn()
const apiCall = vi.fn()
const capture = vi.fn()
const toastSuccess = vi.fn()
const toastWarning = vi.fn()
const certificateSubmit = vi.fn()

vi.mock('frappe-ui', () => ({
	Badge: { template: '<span class="badge"><slot /></span>' },
	Button: {
		props: ['loading'],
		template: '<button><slot name="prefix" /><slot /></button>',
	},
	call: (...args: unknown[]) => apiCall(...args),
	createResource: () => ({ data: null, submit: certificateSubmit }),
	toast: {
		success: (...a: unknown[]) => toastSuccess(...a),
		warning: (...a: unknown[]) => toastWarning(...a),
	},
}))
vi.mock('frappe-ui/frappe', () => ({ useTelemetry: () => ({ capture }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
vi.mock('@/components/VideoPreview.vue', () => ({
	default: { template: '<div class="video-preview" />' },
}))
vi.mock('@/components/CertificationLinks.vue', () => ({
	default: { template: '<div class="certification-links" />' },
}))

vi.stubGlobal('__', (s: string) => s)

const BASE = {
	name: 'COURSE-1',
	title: 'Course',
	lessons: 3,
	enrollments: 7,
	instructors: [{ name: 'lea@x.io' }],
}

async function mountOverlay(
	course: Record<string, unknown> = {},
	user: unknown = { data: { name: 'a@b.c' } }
) {
	const { default: CourseCardOverlay } = await import(
		'@/components/CourseCardOverlay.vue'
	)
	return mount(CourseCardOverlay, {
		props: { course: { data: { ...BASE, ...course } } as any },
		global: {
			provide: { $user: user },
			mocks: { __: (s: string) => s },
			stubs: {
				'router-link': {
					props: ['to'],
					template: '<a :data-to="JSON.stringify(to)"><slot /></a>',
				},
			},
		},
	})
}

const routes = (wrapper: any) =>
	wrapper
		.findAll('a[data-to]')
		.map((a: any) => JSON.parse(a.attributes('data-to')))

beforeEach(() => {
	vi.useRealTimers()
	push.mockClear()
	apiCall.mockReset().mockResolvedValue({})
	capture.mockClear()
	toastSuccess.mockClear()
	toastWarning.mockClear()
	certificateSubmit.mockClear()
})

describe('CourseCardOverlay call-to-action chain', () => {
	it('offers enrolment to a learner who is not a member', async () => {
		const wrapper = await mountOverlay()
		expect(wrapper.text()).toContain('Enroll Now')
		expect(wrapper.text()).toContain('Free')
	})

	it('resumes a member at their current lesson', async () => {
		const wrapper = await mountOverlay({
			membership: { progress: 40 },
			current_lesson: '2-3',
			paid_course: 1,
		})
		expect(wrapper.text()).toContain('Continue Learning')
		expect(wrapper.text()).not.toContain('Buy this course')
		expect(routes(wrapper)[0]).toMatchObject({
			name: 'Lesson',
			params: { courseName: 'COURSE-1', chapterNumber: '2', lessonNumber: '3' },
		})
	})

	it('starts a member with no current lesson at 1-1', async () => {
		const wrapper = await mountOverlay({ membership: { progress: 0 } })
		expect(routes(wrapper)[0].params).toMatchObject({
			chapterNumber: 1,
			lessonNumber: 1,
		})
	})

	it('sends a non-member to billing for a paid course', async () => {
		const wrapper = await mountOverlay({ paid_course: 1, price: '$10' })
		expect(wrapper.text()).toContain('Buy this course')
		expect(wrapper.text()).toContain('$10')
		expect(routes(wrapper)[0]).toMatchObject({
			name: 'Billing',
			params: { type: 'course', name: 'COURSE-1' },
		})
	})

	it('puts paid ahead of the self-learning block', async () => {
		const wrapper = await mountOverlay({
			paid_course: 1,
			disable_self_learning: 1,
		})
		expect(wrapper.text()).toContain('Buy this course')
		expect(wrapper.text()).not.toContain('Contact the Administrator')
	})

	it('asks the learner to contact an admin when self-learning is off', async () => {
		const wrapper = await mountOverlay({ disable_self_learning: 1 })
		expect(wrapper.text()).toContain('Contact the Administrator')
		expect(wrapper.text()).not.toContain('Enroll Now')
	})

	it('offers a course instructor no call to action', async () => {
		const wrapper = await mountOverlay(
			{ paid_course: 1, disable_self_learning: 1 },
			{ data: { name: 'lea@x.io' } }
		)
		expect(wrapper.text()).not.toContain('Enroll Now')
		expect(wrapper.text()).not.toContain('Buy this course')
		expect(wrapper.text()).not.toContain('Contact the Administrator')
	})

	it('offers a moderator no call to action', async () => {
		const wrapper = await mountOverlay(
			{},
			{ data: { name: 'm@x.io', is_moderator: true } }
		)
		expect(wrapper.text()).not.toContain('Enroll Now')
	})

	it('offers the certificate once progress reaches 100', async () => {
		const wrapper = await mountOverlay({
			enable_certification: 1,
			membership: { progress: 100 },
		})
		const button = wrapper
			.findAll('button')
			.find((b) => b.text().includes('Get Certificate'))
		expect(button).toBeTruthy()
		await button!.trigger('click')
		expect(certificateSubmit).toHaveBeenCalledWith({
			course: 'COURSE-1',
			member: 'a@b.c',
		})
	})

	it('withholds the certificate below 100', async () => {
		const wrapper = await mountOverlay({
			enable_certification: 1,
			membership: { progress: 99 },
		})
		expect(wrapper.text()).not.toContain('Get Certificate')
	})
})

describe('CourseCardOverlay enrolment', () => {
	it('inserts an enrolment, then opens lesson 1-1', async () => {
		vi.useFakeTimers()
		const wrapper = await mountOverlay()
		await wrapper
			.findAll('button')
			.find((b) => b.text().includes('Enroll Now'))!
			.trigger('click')
		await flushPromises()

		expect(apiCall).toHaveBeenCalledWith('frappe.client.insert', {
			doc: { doctype: 'LMS Enrollment', course: 'COURSE-1', member: 'a@b.c' },
		})
		expect(capture).toHaveBeenCalledWith('enrolled_in_course', {
			course: 'COURSE-1',
		})
		expect(toastSuccess).toHaveBeenCalled()

		vi.advanceTimersByTime(1000)
		expect(push).toHaveBeenCalledWith({
			name: 'Lesson',
			params: { courseName: 'COURSE-1', chapterNumber: 1, lessonNumber: 1 },
		})
	})

	it('warns with the server message when enrolment fails', async () => {
		apiCall.mockRejectedValue({ messages: ['Already enrolled'] })
		const error = vi.spyOn(console, 'error').mockImplementation(() => {})
		const wrapper = await mountOverlay()
		await wrapper
			.findAll('button')
			.find((b) => b.text().includes('Enroll Now'))!
			.trigger('click')
		await flushPromises()
		expect(toastWarning).toHaveBeenCalledWith('Already enrolled')
		expect(push).not.toHaveBeenCalled()
		error.mockRestore()
	})

	it('sends a guest to log in instead of enrolling', async () => {
		vi.useFakeTimers()
		const location = { href: '', pathname: '/lms/courses/COURSE-1' }
		vi.stubGlobal('location', location)
		const wrapper = await mountOverlay({}, { data: null })
		await wrapper
			.findAll('button')
			.find((b) => b.text().includes('Enroll Now'))!
			.trigger('click')
		expect(apiCall).not.toHaveBeenCalled()
		expect(toastWarning).toHaveBeenCalled()
		vi.advanceTimersByTime(500)
		expect(location.href).toBe('/login?redirect-to=/lms/courses/COURSE-1')
		vi.unstubAllGlobals()
		vi.stubGlobal('__', (s: string) => s)
	})
})
