/**
 * CatalogEnrollCard.vue — the call-to-action chain.
 *
 * The chain is an ordered v-if/v-else-if: enrolled beats paid, paid beats the
 * self-learning block, and an admin falls past every branch. Reordering it is
 * silent in review and obvious to a learner, so each state is pinned here —
 * along with the enrolment call, which now reloads the course resource so a
 * learner returning to the page is not offered "Enroll now" again.
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
	title: 'Sustainable Development Essentials',
	lessons: 9,
	enrollments: 120,
	instructors: [{ name: 'lea@x.io', full_name: 'Léa Moreau' }],
}

const reload = vi.fn().mockResolvedValue(undefined)

async function mountCard(
	course: Record<string, unknown> = {},
	user: unknown = { data: { name: 'a@b.c' } }
) {
	const { default: CatalogEnrollCard } = await import(
		'@/components/Catalog/CatalogEnrollCard.vue'
	)
	return mount(CatalogEnrollCard, {
		props: { course: { data: { ...BASE, ...course }, reload } },
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

const routes = (wrapper: { findAll: (s: string) => { attributes: (a: string) => string | undefined }[] }) =>
	wrapper
		.findAll('a[data-to]')
		.map((a) => JSON.parse(a.attributes('data-to') as string))

beforeEach(() => {
	push.mockClear()
	apiCall.mockReset().mockResolvedValue({})
	capture.mockClear()
	toastSuccess.mockClear()
	toastWarning.mockClear()
	certificateSubmit.mockClear()
	reload.mockClear()
	vi.unstubAllGlobals()
	vi.stubGlobal('__', (s: string) => s)
})

describe('CatalogEnrollCard call-to-action chain', () => {
	it('shows nothing to act on until the course lands', async () => {
		const { default: CatalogEnrollCard } = await import(
			'@/components/Catalog/CatalogEnrollCard.vue'
		)
		const wrapper = mount(CatalogEnrollCard, {
			props: { course: { data: null, reload } },
			global: {
				provide: { $user: { data: { name: 'a@b.c' } } },
				mocks: { __: (s: string) => s },
				stubs: { 'router-link': true },
			},
		})
		// Against no data the chain would default to Free / Enroll now, then
		// swap to "Buy this course" once a paid course answered.
		expect(wrapper.text()).not.toContain('Enroll now')
		expect(wrapper.text()).not.toContain('Free')
		expect(wrapper.find('.animate-pulse').exists()).toBe(true)
	})

	it('offers enrolment to a signed-in learner who is not a member', async () => {
		const wrapper = await mountCard()
		expect(wrapper.text()).toContain('Enroll now')
		expect(wrapper.text()).not.toContain('Continue learning')
		expect(wrapper.text()).not.toContain('Buy this course')
	})

	it('resumes an enrolled learner at their current lesson', async () => {
		const wrapper = await mountCard({
			membership: { progress: 40 },
			current_lesson: '2-3',
		})
		expect(wrapper.text()).toContain('Continue learning')
		expect(wrapper.text()).not.toContain('Enroll now')
		expect(routes(wrapper)[0]).toEqual({
			name: 'Lesson',
			params: {
				courseName: 'COURSE-1',
				chapterNumber: '2',
				lessonNumber: '3',
			},
		})
		expect(wrapper.find('.certification-links').exists()).toBe(true)
	})

	it('starts an enrolled learner at lesson one when there is no current lesson', async () => {
		const wrapper = await mountCard({ membership: { progress: 0 } })
		expect(routes(wrapper)[0].params).toEqual({
			courseName: 'COURSE-1',
			chapterNumber: 1,
			lessonNumber: 1,
		})
	})

	it('sends a non-member of a paid course to billing', async () => {
		const wrapper = await mountCard({ paid_course: 1, price: '$45' })
		expect(wrapper.text()).toContain('Buy this course')
		expect(wrapper.text()).toContain('$45')
		expect(wrapper.text()).not.toContain('Free')
		expect(routes(wrapper)[0]).toEqual({
			name: 'Billing',
			params: { type: 'course', name: 'COURSE-1' },
		})
	})

	it('keeps membership ahead of payment, so an enrolled learner is never asked to buy', async () => {
		const wrapper = await mountCard({
			paid_course: 1,
			price: '$45',
			membership: { progress: 10 },
		})
		expect(wrapper.text()).toContain('Continue learning')
		expect(wrapper.text()).not.toContain('Buy this course')
	})

	it('explains a course that cannot be self-enrolled instead of offering a button', async () => {
		const wrapper = await mountCard({ disable_self_learning: 1 })
		expect(wrapper.text()).toContain(
			'Contact the Administrator to enroll for this course'
		)
		expect(wrapper.text()).not.toContain('Enroll now')
	})

	it('offers an instructor no call to action on their own course', async () => {
		const wrapper = await mountCard({ paid_course: 1, disable_self_learning: 1 }, {
			data: { name: 'lea@x.io' },
		})
		expect(wrapper.text()).not.toContain('Enroll now')
		expect(wrapper.text()).not.toContain('Buy this course')
		expect(wrapper.text()).not.toContain('Contact the Administrator')
	})

	it('offers a moderator no call to action either', async () => {
		const wrapper = await mountCard({}, {
			data: { name: 'mod@x.io', is_moderator: 1 },
		})
		expect(wrapper.text()).not.toContain('Enroll now')
	})
})

describe('CatalogEnrollCard enrolment', () => {
	it('inserts an enrolment, refreshes the course, then opens lesson one', async () => {
		const wrapper = await mountCard()
		await wrapper.findAll('button')[0].trigger('click')
		await flushPromises()

		expect(apiCall).toHaveBeenCalledWith('frappe.client.insert', {
			doc: {
				doctype: 'LMS Enrollment',
				course: 'COURSE-1',
				member: 'a@b.c',
			},
		})
		expect(capture).toHaveBeenCalledWith('enrolled_in_course', {
			course: 'COURSE-1',
		})
		// The reload is the fix: without it the card still reads "Enroll now"
		// for a learner who navigates back to the page.
		expect(reload).toHaveBeenCalled()
		expect(push).toHaveBeenCalledWith({
			name: 'Lesson',
			params: { courseName: 'COURSE-1', chapterNumber: 1, lessonNumber: 1 },
		})
	})

	it('sends a guest to log in rather than calling the API', async () => {
		vi.useFakeTimers()
		// Only window.location is swapped: replacing the whole window object
		// takes jsdom's event constructors with it, and trigger() then fails.
		const realLocation = window.location
		const location = { pathname: '/catalog/courses/COURSE-1', href: '' }
		Object.defineProperty(window, 'location', {
			value: location,
			writable: true,
			configurable: true,
		})

		try {
			const wrapper = await mountCard({}, { data: null })
			await wrapper.findAll('button')[0].trigger('click')
			await Promise.resolve()

			expect(apiCall).not.toHaveBeenCalled()
			expect(toastWarning).toHaveBeenCalledWith(
				'You need to login first to enroll for this course'
			)
			vi.runAllTimers()
			expect(location.href).toBe('/login?redirect-to=/catalog/courses/COURSE-1')
		} finally {
			Object.defineProperty(window, 'location', {
				value: realLocation,
				writable: true,
				configurable: true,
			})
			vi.useRealTimers()
		}
	})

	it('warns and stays put when the insert fails', async () => {
		apiCall.mockRejectedValue({ messages: ['Already enrolled'] })
		const wrapper = await mountCard()
		await wrapper.findAll('button')[0].trigger('click')
		await flushPromises()

		expect(toastWarning).toHaveBeenCalledWith('Already enrolled')
		expect(push).not.toHaveBeenCalled()
	})
})

describe('CatalogEnrollCard certificate and includes', () => {
	it('offers the certificate only once the course is both certified and finished', async () => {
		expect((await mountCard({ enable_certification: 1 })).text()).not.toContain(
			'Get certificate'
		)
		expect(
			(
				await mountCard({
					enable_certification: 1,
					membership: { progress: 60 },
				})
			).text()
		).not.toContain('Get certificate')
		expect(
			(
				await mountCard({
					enable_certification: 1,
					membership: { progress: 100 },
				})
			).text()
		).toContain('Get certificate')
	})

	it('buckets the enrolment count rather than quoting it exactly', async () => {
		expect((await mountCard({ enrollments: 12 })).text()).toContain('12 enrolled')
		expect((await mountCard({ enrollments: 187 })).text()).toContain(
			'150+ enrolled'
		)
		expect((await mountCard({ enrollments: 12480 })).text()).toContain(
			'12400+ enrolled'
		)
	})

	it('lists only the things the course actually has', async () => {
		const bare = await mountCard({
			lessons: 0,
			enrollments: 0,
			quiz_count: 0,
		})
		expect(bare.text()).not.toContain('This course includes')

		const full = await mountCard({
			video_link: 'https://youtu.be/x',
			lessons: 1,
			quiz_count: 2,
			enable_certification: 1,
		})
		expect(full.text()).toContain('This course includes')
		expect(full.text()).toContain('On demand course video')
		expect(full.text()).toContain('1 lesson')
		expect(full.text()).toContain('2 quiz topics')
		expect(full.text()).toContain('Certificate of completion')
	})

	it('falls back to the cover art when there is no preview video', async () => {
		expect((await mountCard({ image: '/files/cover.png' })).find('img').exists()).toBe(
			true
		)
		// VideoPreview owns the media once there is a video to play.
		expect(
			(await mountCard({ image: '/files/cover.png', video_link: 'https://youtu.be/x' }))
				.find('img')
				.exists()
		).toBe(false)
	})
})
