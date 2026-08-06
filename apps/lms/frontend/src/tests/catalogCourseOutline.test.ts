/**
 * CatalogCourseOutline.vue — the catalog's read-only outline.
 *
 * It is a separate component from CourseOutline rather than a restyle, so the
 * behaviour that had to be carried across — lesson routing, the lesson icon
 * map, SCORM chapters and completion — is what these tests pin down. What was
 * deliberately left behind (drag, rename, delete, ChapterModal) is asserted
 * absent, since re-adding it by accident is the failure mode.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const push = vi.fn()
const toastSuccess = vi.fn()

type Lesson = {
	name: string
	title: string
	number: string
	icon?: string
	is_complete?: boolean
	include_in_preview?: 0 | 1
}
type Chapter = {
	name: string
	title: string
	idx: number
	is_scorm_package?: 0 | 1
	lessons?: Lesson[]
}

// Mutable so each test swaps in its own fixture before mounting; the resource
// exposes `data` through a getter so the component reads the current value.
let currentOutline: Chapter[] | null = []
let outlineLoading = false

vi.mock('frappe-ui', () => ({
	createResource: () => ({
		get data() {
			return currentOutline
		},
		get loading() {
			return outlineLoading
		},
		reload: vi.fn(),
		fetch: vi.fn(),
	}),
	toast: {
		success: (...args: unknown[]) => toastSuccess(...args),
		warning: vi.fn(),
	},
}))

vi.mock('vue-router', () => ({
	useRouter: () => ({ push }),
	useRoute: () => ({ params: {}, query: {} }),
}))

vi.mock('@/components/SkeletonLoader.vue', () => ({
	default: { template: '<div class="skeleton" />' },
}))

vi.stubGlobal('__', (s: string) => s)

const CHAPTERS: Chapter[] = [
	{
		name: 'CH-1',
		title: 'Introduction',
		idx: 1,
		lessons: [
			{ name: 'L-A', title: 'What is the 2030 Agenda?', number: '1-1', icon: 'icon-youtube' },
			{ name: 'L-B', title: 'The 17 SDGs', number: '1-2', icon: 'icon-list', is_complete: true },
		],
	},
	{
		name: 'CH-2',
		title: 'Measuring impact',
		idx: 2,
		lessons: [
			{ name: 'L-C', title: 'Indicators', number: '2-1', icon: 'icon-quiz' },
		],
	},
]

async function mountOutline(
	props: Record<string, unknown> = {},
	user: unknown = { data: { name: 'a@b.c' } }
) {
	const { default: CatalogCourseOutline } = await import(
		'@/components/Catalog/CatalogCourseOutline.vue'
	)
	const wrapper = mount(CatalogCourseOutline, {
		props: { courseName: 'COURSE-1', ...props },
		global: {
			provide: { $user: user },
			mocks: { __: (s: string) => s },
			stubs: {
				// Rendered as a plain <a> carrying the resolved route as JSON, so
				// the assertions below can read what each lesson links to.
				'router-link': {
					props: ['to'],
					template: '<a :data-to="JSON.stringify(to)"><slot /></a>',
				},
			},
		},
	})
	await flushPromises()
	return wrapper
}

beforeEach(() => {
	currentOutline = CHAPTERS
	outlineLoading = false
	push.mockClear()
	toastSuccess.mockClear()
})

describe('CatalogCourseOutline', () => {
	it('links each lesson to the student Lesson route, splitting the positional number', async () => {
		const wrapper = await mountOutline()
		const routes = wrapper
			.findAll('a[data-to]')
			.map((a) => JSON.parse(a.attributes('data-to') as string))

		expect(routes[0]).toEqual({
			name: 'Lesson',
			params: {
				courseName: 'COURSE-1',
				chapterNumber: '1',
				lessonNumber: '1',
			},
		})
		expect(routes[1].params).toEqual({
			courseName: 'COURSE-1',
			chapterNumber: '1',
			lessonNumber: '2',
		})
	})

	it('never deep-links into the course editor', async () => {
		const wrapper = await mountOutline()
		expect(wrapper.html()).not.toContain('CourseDetail')
		expect(wrapper.html()).not.toContain('editLesson')
	})

	it('maps every lesson icon the backend can return', async () => {
		currentOutline = [
			{
				name: 'CH-1',
				title: 'All types',
				idx: 1,
				lessons: [
					{ name: 'a', title: 'video', number: '1-1', icon: 'icon-youtube' },
					{ name: 'b', title: 'quiz', number: '1-2', icon: 'icon-quiz' },
					{ name: 'c', title: 'task', number: '1-3', icon: 'icon-assignment' },
					{ name: 'd', title: 'code', number: '1-4', icon: 'icon-code' },
					{ name: 'e', title: 'text', number: '1-5', icon: 'icon-list' },
				],
			},
		]
		const wrapper = await mountOutline()
		const html = wrapper.html()
		expect(html).toContain('lucide-monitor-play')
		expect(html).toContain('lucide-help-circle')
		expect(html).toContain('lucide-notebook-pen')
		expect(html).toContain('lucide-square-code')
		expect(html).toContain('lucide-file-text')
	})

	it('falls back to the text icon for an unknown or missing icon', async () => {
		currentOutline = [
			{
				name: 'CH-1',
				title: 'Odd',
				idx: 1,
				lessons: [
					{ name: 'a', title: 'no icon', number: '1-1' },
					{ name: 'b', title: 'new icon', number: '1-2', icon: 'icon-hologram' },
				],
			},
		]
		const wrapper = await mountOutline()
		expect(wrapper.findAll('.lucide-file-text')).toHaveLength(2)
	})

	it('marks completed lessons', async () => {
		const wrapper = await mountOutline()
		// L-B is the only complete lesson in the fixture.
		expect(wrapper.findAll('.lucide-check')).toHaveLength(1)
	})

	it('flags preview lessons', async () => {
		expect((await mountOutline()).text()).not.toContain('Preview')
		currentOutline = [
			{
				name: 'CH-1',
				title: 'Introduction',
				idx: 1,
				lessons: [
					{ name: 'a', title: 'Free sample', number: '1-1', include_in_preview: 1 },
				],
			},
		]
		expect((await mountOutline()).text()).toContain('Preview')
	})

	it('opens a SCORM chapter in the player instead of expanding it', async () => {
		currentOutline = [
			{
				name: 'CH-S',
				title: 'Packaged module',
				idx: 1,
				is_scorm_package: 1,
				lessons: [{ name: 'a', title: 'scorm', number: '1-1' }],
			},
		]
		const wrapper = await mountOutline()
		await wrapper.find('button').trigger('click')

		expect(push).toHaveBeenCalledWith({
			name: 'SCORMChapter',
			params: { courseName: 'COURSE-1', chapterName: 'CH-S' },
		})
	})

	it('asks a guest to enroll rather than opening the SCORM player', async () => {
		currentOutline = [
			{
				name: 'CH-S',
				title: 'Packaged module',
				idx: 1,
				is_scorm_package: 1,
				lessons: [{ name: 'a', title: 'scorm', number: '1-1' }],
			},
		]
		const wrapper = await mountOutline({}, { data: null })
		await wrapper.find('button').trigger('click')

		expect(push).not.toHaveBeenCalled()
		expect(toastSuccess).toHaveBeenCalledWith(
			'Please enroll for this course to view this lesson'
		)
	})

	it('checks a SCORM chapter only once every lesson in it is complete', async () => {
		currentOutline = [
			{
				name: 'CH-S',
				title: 'Packaged module',
				idx: 1,
				is_scorm_package: 1,
				lessons: [
					{ name: 'a', title: 'one', number: '1-1', is_complete: true },
					{ name: 'b', title: 'two', number: '1-2' },
				],
			},
		]
		expect((await mountOutline()).find('.lucide-check').exists()).toBe(false)

		currentOutline[0].lessons![1].is_complete = true
		expect((await mountOutline()).find('.lucide-check').exists()).toBe(true)
	})

	it('says content is coming rather than showing an empty shell', async () => {
		currentOutline = []
		expect((await mountOutline()).text()).toContain(
			'Course Content coming soon!'
		)

		// A chapter with no lessons is still nothing to read.
		currentOutline = [{ name: 'CH-1', title: 'Empty', idx: 1, lessons: [] }]
		expect((await mountOutline()).text()).toContain(
			'Course Content coming soon!'
		)
	})

	it('shows the skeleton only before the first response', async () => {
		currentOutline = null
		outlineLoading = true
		expect((await mountOutline()).find('.skeleton').exists()).toBe(true)

		currentOutline = CHAPTERS
		outlineLoading = true
		expect((await mountOutline()).find('.skeleton').exists()).toBe(false)
	})

	it('exposes its chapters so the page does not fetch the outline a second time', async () => {
		const wrapper = await mountOutline()
		expect(
			(wrapper.vm as unknown as { chapters: Chapter[] }).chapters
		).toHaveLength(2)
		expect((wrapper.vm as unknown as { lessonCount: number }).lessonCount).toBe(
			3
		)
	})

	it('carries no editing affordances', async () => {
		const html = (await mountOutline()).html()
		expect(html).not.toContain('lucide-trash-2')
		expect(html).not.toContain('Add Lesson')
		expect(html).not.toContain('lucide-file-pen-line')
	})
})
