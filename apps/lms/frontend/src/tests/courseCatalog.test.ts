/**
 * CourseCatalog.vue — the full-width student catalog.
 *
 * It draws the same filter state as Courses.vue through a different set of
 * controls, so what is worth proving here is that the new controls reach
 * `useCourseCatalog` correctly: the chips set a category, the sheet's toggle
 * sets certification, and the hero's search waits for a pause instead of
 * firing a request per keystroke.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent, nextTick, reactive } from 'vue'
import { mount } from '@vue/test-utils'

type Rows = { name: string }[]

interface FakeRequest {
	filters: Record<string, unknown>
	aborted: boolean
	respond: (rows: Rows) => void
}

/** Same hand-settled stand-in the Courses.vue filter test uses. */
function makeCoursesResource() {
	const requests: FakeRequest[] = []
	let inFlight: FakeRequest | null = null

	const resource = reactive({
		data: null as Rows | null,
		hasNextPage: false,
		pageLength: 24,
		filters: {} as Record<string, unknown>,
		list: {
			loading: false,
			abort: () => {
				if (inFlight) inFlight.aborted = true
			},
		},
		update({ filters }: { filters: Record<string, unknown> }) {
			resource.filters = JSON.parse(JSON.stringify(filters))
		},
		reload() {
			const request: FakeRequest = {
				filters: JSON.parse(JSON.stringify(resource.filters)),
				aborted: false,
				respond(rows: Rows) {
					if (!request.aborted) resource.data = rows
				},
			}
			inFlight = request
			requests.push(request)
		},
		next: vi.fn(),
	})

	return { resource, requests }
}

const { coursesResource, requests, mobile, loggedIn } = vi.hoisted(() => ({
	coursesResource: { current: null as any },
	requests: { current: [] as any[] },
	mobile: { value: false },
	loggedIn: { value: true },
}))

const CATEGORIES = [
	{ label: '', value: null },
	{ label: 'Design', value: 'Design' },
	{ label: 'Engineering', value: 'Engineering' },
]

vi.mock('frappe-ui', () => ({
	usePageMeta: vi.fn(),
	createResource: () => reactive({ data: 12, abort: vi.fn(), submit: vi.fn() }),
	createListResource: (options: { url: string }) => {
		if (options.url.includes('get_course_categories')) {
			return reactive({ data: CATEGORIES, list: { loading: false } })
		}
		return coursesResource.current
	},
	Button: {
		props: ['label'],
		template: '<button :data-testid="label">{{ label }}<slot /></button>',
	},
	Dropdown: { template: '<div><slot :open="false" /></div>' },
	Tooltip: { template: '<div><slot /></div>' },
	// frappe-ui's Checkbox reports one click twice (Checkbox.vue:76-77); the
	// real ToggleFilter is kept below precisely to prove it swallows the echo.
	Checkbox: defineComponent({
		props: { modelValue: Boolean, label: String },
		emits: ['update:modelValue'],
		methods: {
			onChange() {
				this.$emit('update:modelValue', !this.modelValue)
				this.$emit('update:modelValue', !this.modelValue)
			},
		},
		template: `<input type="checkbox" data-testid="certification" @change="onChange" />`,
	}),
	TabButtons: {
		props: ['options', 'modelValue'],
		emits: ['update:modelValue'],
		template: `<div>
			<button
				v-for="option in options"
				:key="option.value"
				:data-testid="'tab-' + option.value"
				:data-state="option.value === modelValue ? 'checked' : 'unchecked'"
				@click="$emit('update:modelValue', option.value)"
			>{{ option.label }}</button>
		</div>`,
	},
}))

vi.mock('@/utils/composables', async () => {
	const { computed } = await import('vue')
	return { useScreenSize: () => ({ isMobile: computed(() => mobile.value) }) }
})
vi.mock('@/stores/session', () => ({
	sessionStore: () => ({ brand: {}, isLoggedIn: loggedIn.value }),
}))
vi.mock('@/utils', () => ({ canCreateCourse: () => true }))
vi.mock('vue-router', () => ({
	useRouter: () => ({ push: vi.fn() }),
	useRoute: () => ({ query: {} }),
}))

const stub = (template: string) => ({ default: { template } })
vi.mock('@/components/Catalog/CatalogCourseCard.vue', () =>
	stub('<article />')
)
vi.mock('@/pages/Courses/NewCourseModal.vue', () => stub('<div />'))
vi.mock('@/pages/Courses/CourseImportModal.vue', () => stub('<div />'))

vi.stubGlobal('__', (s: string) => s)

const STUDENT = { name: 'learner@test.com', is_student: true }
const COURSES = [{ name: 'course-a' }, { name: 'course-b' }]

async function mountCatalog(user = { data: { ...STUDENT } }) {
	const { default: CourseCatalog } = await import(
		'@/pages/Courses/CourseCatalog.vue'
	)
	const wrapper = mount(CourseCatalog, {
		global: {
			provide: {
				$user: user,
				$dayjs: () => ({ add: () => ({ format: () => '' }) }),
			},
			mocks: { __: (s: string) => s },
			stubs: { 'router-link': { template: '<a><slot /></a>' } },
		},
	})
	await nextTick()
	return wrapper
}

const cards = (wrapper: any) => wrapper.findAll('article').length
const chip = (wrapper: any, label: string) =>
	wrapper.findAll('[role="group"] button').find((b: any) => b.text() === label)
const search = (wrapper: any) => wrapper.find('input[type="search"]')
const lastFilters = () =>
	requests.current[requests.current.length - 1].filters

beforeEach(() => {
	mobile.value = false
	loggedIn.value = true
	window.history.replaceState({}, '', '/lms/catalog')
	const fake = makeCoursesResource()
	coursesResource.current = fake.resource
	requests.current = fake.requests
	vi.resetModules()
})

afterEach(() => {
	vi.useRealTimers()
})

describe('CourseCatalog', () => {
	it('fetches the published tab on mount and renders a card per course', async () => {
		const wrapper = await mountCatalog()

		expect(requests.current).toHaveLength(1)
		expect(requests.current[0].filters).toMatchObject({ published: 1, live: 1 })

		requests.current[0].respond(COURSES)
		await nextTick()
		expect(cards(wrapper)).toBe(2)
	})

	it('filters by category from the chip row', async () => {
		const wrapper = await mountCatalog()

		await chip(wrapper, 'Design')!.trigger('click')
		await nextTick()

		expect(requests.current).toHaveLength(2)
		expect(lastFilters()).toMatchObject({ category: 'Design' })
		expect(chip(wrapper, 'Design')!.attributes('aria-pressed')).toBe('true')
	})

	it('leaves the "All" chip meaning no category filter', async () => {
		const wrapper = await mountCatalog()

		await chip(wrapper, 'Design')!.trigger('click')
		await nextTick()
		await chip(wrapper, 'All')!.trigger('click')
		await nextTick()

		expect(lastFilters()).not.toHaveProperty('category')
	})

	it('sends one request for a typed word, not one per keystroke', async () => {
		vi.useFakeTimers()
		const wrapper = await mountCatalog()
		const requestsAfterMount = requests.current.length

		const input = search(wrapper)
		for (const value of ['v', 'vu', 'vue']) {
			await input.setValue(value)
		}
		expect(requests.current).toHaveLength(requestsAfterMount)

		vi.advanceTimersByTime(300)
		await nextTick()

		expect(requests.current).toHaveLength(requestsAfterMount + 1)
		expect(lastFilters()).toMatchObject({ title: ['like', '%vue%'] })
	})

	it('sends one request from the certification toggle', async () => {
		const wrapper = await mountCatalog()

		// The hero's Filters button; `aria-expanded` is what names it as the
		// control for the panel below.
		await wrapper.find('button[aria-expanded]').trigger('click')
		await wrapper.find('[data-testid="certification"]').trigger('change')
		await nextTick()

		expect(requests.current).toHaveLength(2)
		expect(lastFilters()).toMatchObject({ certification: 1 })
	})

	it('drops a slow response from the tab the user has already left', async () => {
		const wrapper = await mountCatalog({
			data: { name: 'admin@test.com', is_moderator: true },
		} as any)

		await wrapper.find('[data-testid="tab-upcoming"]').trigger('click')
		await nextTick()
		expect(requests.current).toHaveLength(2)

		requests.current[1].respond([])
		await nextTick()
		expect(cards(wrapper)).toBe(0)

		// The published tab's fetch finally lands. It must not repaint the grid.
		requests.current[0].respond(COURSES)
		await nextTick()
		expect(cards(wrapper)).toBe(0)
	})

	it('clears every filter at once from the empty state', async () => {
		const wrapper = await mountCatalog()
		requests.current[0].respond([])
		await nextTick()

		await chip(wrapper, 'Design')!.trigger('click')
		await nextTick()
		requests.current[1].respond([])
		await nextTick()

		await wrapper.find('[data-testid="Clear filters"]').trigger('click')
		await nextTick()

		expect(lastFilters()).not.toHaveProperty('category')
		expect(lastFilters()).not.toHaveProperty('certification')
	})

	it('asks a guest to sign in rather than reporting no matches', async () => {
		loggedIn.value = false
		const wrapper = await mountCatalog({ data: null } as any)
		requests.current[0].respond([])
		await nextTick()

		expect(wrapper.text()).toContain('Sign in to browse the course catalog.')
	})
})
