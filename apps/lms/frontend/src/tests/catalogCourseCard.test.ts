/**
 * CatalogCourseCard.vue — what the card says about a course.
 *
 * The mock it is drawn from carries fields LMS Course does not have (level,
 * duration) and omits several it does (featured, certification, more than one
 * instructor). These cover the substitutions.
 */
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('frappe-ui', () => ({
	Avatar: { props: ['label', 'image', 'size'], template: '<span />' },
	Tooltip: { template: '<div><slot /></div>' },
}))
vi.mock('@/utils', () => ({
	formatAmount: (n: number) => (n > 999 ? `${(n / 1000).toFixed(1)}k` : n),
	formatRating: (n: unknown) => String(n),
}))

vi.stubGlobal('__', (s: string) => s)

const BASE = {
	name: 'course-a',
	title: 'Interface Design Systems',
	short_introduction: 'Build a scalable design system.',
	category: 'Design',
	lessons: 19,
	enrollments: 6105,
	rating: 4.9,
	instructors: [{ name: 'lea', full_name: 'Léa Moreau', first_name: 'Léa' }],
}

async function mountCard(course: Record<string, any>) {
	const { default: CatalogCourseCard } = await import(
		'@/components/Catalog/CatalogCourseCard.vue'
	)
	return mount(CatalogCourseCard, {
		props: { course: { ...BASE, ...course } },
		global: {
			mocks: { __: (s: string) => s },
			stubs: { 'router-link': { template: '<a><slot /></a>' } },
		},
	})
}

describe('CatalogCourseCard', () => {
	it('shows the cover image when there is one', async () => {
		const wrapper = await mountCard({ image: '/files/cover.png' })
		expect(wrapper.find('img').attributes('src')).toBe('/files/cover.png')
	})

	it('falls back to the title on the course gradient with no image', async () => {
		const wrapper = await mountCard({ card_gradient: 'Green' })
		expect(wrapper.find('img').exists()).toBe(false)
		expect(wrapper.html()).toContain('var(--green-400)')
		// The title then appears twice — as the artwork and as the heading.
		expect(wrapper.text()).toContain('Interface Design Systems')
	})

	it('says Free unless the course is paid', async () => {
		expect((await mountCard({})).text()).toContain('Free')
		const paid = await mountCard({ paid_course: 1, price: '$45' })
		expect(paid.text()).toContain('$45')
		expect(paid.text()).not.toContain('Free')
	})

	it('renders the available lesson, enrolment, and rating metadata', async () => {
		const wrapper = await mountCard({})
		expect(wrapper.text()).toContain('19 lessons')
		expect(wrapper.text()).toContain('6.1k')
		expect(wrapper.text()).toContain('4.9')
	})

	it('shows progress only when the enrolled learner has started the course', async () => {
		expect((await mountCard({})).find('[role="progressbar"]').exists()).toBe(
			false
		)
		expect(
			(await mountCard({ membership: { progress: 0 } }))
				.find('[role="progressbar"]')
				.exists()
		).toBe(false)
		expect(
			(await mountCard({ membership: { progress: null } }))
				.find('[role="progressbar"]')
				.exists()
		).toBe(false)
		expect(
			(await mountCard({ membership: { progress: 'not a number' } }))
				.find('[role="progressbar"]')
				.exists()
		).toBe(false)

		const enrolled = await mountCard({ membership: { progress: 77.4 } })
		const bar = enrolled.find('[role="progressbar"]')
		expect(bar.attributes('aria-valuenow')).toBe('78')
		expect(bar.attributes('aria-valuemin')).toBe('0')
		expect(bar.attributes('aria-valuemax')).toBe('100')
		expect(enrolled.text()).toContain('78%')
		expect(bar.find('div').attributes('style')).toContain('width: 78%')
	})

	it('bounds displayed progress at 100%', async () => {
		const wrapper = await mountCard({ membership: { progress: 112.2 } })
		const bar = wrapper.find('[role="progressbar"]')
		expect(bar.attributes('aria-valuenow')).toBe('100')
		expect(wrapper.text()).toContain('100%')
		expect(bar.find('div').attributes('style')).toContain('width: 100%')
	})

	it('hides the rating until a course has one', async () => {
		expect((await mountCard({ rating: 0 })).text()).not.toContain('4.9')
		expect((await mountCard({})).text()).toContain('4.9')
	})

	it('names the first instructor and counts the rest', async () => {
		const one = await mountCard({})
		expect(one.text()).toContain('Léa Moreau')

		const three = await mountCard({
			instructors: [
				{ name: 'a', full_name: 'Léa Moreau', first_name: 'Léa' },
				{ name: 'b', full_name: 'Tom Berg', first_name: 'Tom' },
				{ name: 'c', full_name: 'Ana Duarte', first_name: 'Ana' },
			],
		})
		expect(three.text()).toContain('Léa and 2 others')
	})

	it('marks featured and certified courses', async () => {
		const plain = await mountCard({})
		expect(plain.text()).not.toContain('Featured')
		expect(plain.find('.lucide-graduation-cap').exists()).toBe(false)

		const flagged = await mountCard({
			featured: 1,
			enable_certification: 1,
		})
		expect(flagged.text()).toContain('Featured')
		expect(flagged.find('.lucide-graduation-cap').exists()).toBe(true)
	})

	it('links the whole card to the course, with no nested link inside it', async () => {
		const wrapper = await mountCard({})
		expect(wrapper.findAll('a')).toHaveLength(1)
	})
})
