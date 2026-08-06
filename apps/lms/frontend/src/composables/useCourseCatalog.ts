import { computed, inject, ref, watch, type ComputedRef, type Ref } from 'vue'
import { createListResource, createResource } from 'frappe-ui'

/**
 * The course catalog's filter state: one list resource, one count resource, and
 * the tab / search / category / certification controls that drive both.
 *
 * Lifted out of Courses.vue so a second presentation of the same catalog can
 * reuse it rather than copy it. Nothing here is incidental — the aborts, the
 * separate `reloading` flag and the page-length rewind are each a fixed bug,
 * and a forked copy would reintroduce every one of them. Which controls draw
 * these filters, and how they are laid out, stays with the page.
 */

type Filters = Record<string, any>

type UserResource = {
	data?: Record<string, any> | null
}

type Tab = { label: string; value: string }

export type CourseCatalog = {
	courses: any
	categories: any
	courseCount: ComputedRef<number | null>
	loading: ComputedRef<boolean>
	pageLength: Ref<number>
	title: Ref<string>
	currentCategory: Ref<string | null>
	certification: Ref<boolean>
	currentTab: Ref<string>
	courseTabs: ComputedRef<Tab[]>
	filters: Ref<Filters>
	init: () => void
	updateCourses: () => void
	setCertification: (value: boolean) => void
	loadMore: () => void
}

export function useCourseCatalog(): CourseCatalog {
	const user = inject<UserResource>('$user')
	const dayjs = inject<any>('$dayjs')

	const start = ref(0)
	const currentCategory = ref<string | null>(null)
	const title = ref('')
	const certification = ref(false)
	const filters = ref<Filters>({})
	const currentTab = ref('live')

	const courses = createListResource({
		doctype: 'LMS Course',
		url: 'lms.lms.utils.get_courses',
		cache: ['courses', user?.data?.name],
		pageLength: 24,
		start: start.value,
	})

	// The tabs filter on `enrolled`, `created` and `live`, which are not fields,
	// so `frappe.client.get_count` cannot answer this — only the endpoint that
	// resolves them can. Without it the footer can say how many rows it has but
	// not how many there are.
	const courseCountResource = createResource({
		url: 'lms.lms.utils.get_course_count',
		makeParams: () => ({ filters: filters.value }),
		onError: (error: unknown) => {
			console.error(error)
		},
	})

	const courseCount = computed<number | null>(
		() => courseCountResource.data ?? null
	)

	const getCourseCount = () => {
		// Same sequencing hazard as the list: nothing orders the responses, so a
		// slow count for filters the user has left would overwrite the current one.
		courseCountResource.abort()
		courseCountResource.submit()
	}

	// `list.loading` goes false mid-request: the aborted fetch's tail resolves
	// after the new reload() has started and clears the flag for it, so the empty
	// state flashes until the reload lands.
	const reloading = ref(false)

	const reloadCourses = async () => {
		reloading.value = true
		try {
			await courses.reload()
		} finally {
			reloading.value = false
		}
	}

	const loading = computed<boolean>(
		() => courses.list.loading || reloading.value
	)

	const pageLength = computed({
		get: () => courses.pageLength,
		set: (value: number) => {
			// reload() refetches only the rows already loaded when start > 0, so
			// without rewinding to the first page a bigger page size changes nothing.
			courses.update({ pageLength: value, start: 0 })
			reloadCourses()
		},
	})

	const categories = createListResource({
		doctype: 'LMS Category',
		url: 'lms.lms.utils.get_course_categories',
		cache: ['course_categories'],
		auto: true,
	})

	const updateCourses = () => {
		updateFilters()
		// createResource keeps no request sequence: every response assigns
		// `data`, so a slow fetch for filters the user has already left repaints
		// the list with the wrong courses seconds later. Cancel it first — an
		// aborted fetch is swallowed and never reaches the list.
		courses.list.abort()
		courses.update({
			filters: filters.value,
		})
		reloadCourses()
		getCourseCount()
	}

	const updateFilters = () => {
		updateCategoryFilter()
		updateTitleFilter()
		updateCertificationFilter()
		updateTabFilter()
		updateStudentFilter()
		setQueryParams()
	}

	const updateCategoryFilter = () => {
		if (currentCategory.value) {
			filters.value['category'] = currentCategory.value
		} else {
			delete filters.value['category']
		}
	}

	const updateTitleFilter = () => {
		if (title.value) {
			filters.value['title'] = ['like', `%${title.value}%`]
		} else {
			delete filters.value['title']
		}
	}

	const updateCertificationFilter = () => {
		if (certification.value) {
			filters.value['certification'] = 1
		} else {
			delete filters.value['certification']
		}
	}

	const updateTabFilter = () => {
		delete filters.value['live']
		delete filters.value['created']
		delete filters.value['published_on']
		delete filters.value['upcoming']

		if (currentTab.value == 'enrolled' && user?.data?.is_student) {
			filters.value['enrolled'] = 1
			delete filters.value['published']
		} else {
			delete filters.value['published']
			delete filters.value['enrolled']

			if (currentTab.value == 'live') {
				filters.value['published'] = 1
				filters.value['upcoming'] = 0
				filters.value['live'] = 1
			} else if (currentTab.value == 'upcoming') {
				filters.value['upcoming'] = 1
			} else if (currentTab.value == 'new') {
				filters.value['published'] = 1
				filters.value['published_on'] = [
					'>=',
					dayjs().add(-3, 'month').format('YYYY-MM-DD'),
				]
			} else if (currentTab.value == 'created') {
				filters.value['created'] = 1
			} else if (currentTab.value == 'unpublished') {
				filters.value['published'] = 0
			}
		}
	}

	const updateStudentFilter = () => {
		if (
			!user?.data ||
			(user?.data?.is_student && currentTab.value != 'enrolled')
		) {
			filters.value['published'] = 1
		}
	}

	const setQueryParams = () => {
		let queries = new URLSearchParams(location.search)
		let filterKeys: Record<string, unknown> = {
			title: title.value,
			category: currentCategory.value,
			certification: certification.value,
		}

		Object.keys(filterKeys).forEach((key) => {
			if (filterKeys[key]) {
				queries.set(key, String(filterKeys[key]))
			} else {
				queries.delete(key)
			}
		})

		let queryString = ''
		if (queries.toString()) {
			queryString = `?${queries.toString()}`
		}

		history.replaceState({}, '', `${location.pathname}${queryString}`)
	}

	const setFiltersFromQuery = () => {
		let queries = new URLSearchParams(location.search)
		title.value = queries.get('title') || ''
		currentCategory.value = queries.get('category') || null
		// `|| false` would keep the raw string, so ?certification=false read as on.
		certification.value = queries.get('certification') === 'true'
		const tab = queries.get('tab')
		if (tab) currentTab.value = tab
	}

	/** Read the deep link, then fetch. What a page runs on mount. */
	const init = () => {
		setFiltersFromQuery()
		updateCourses()
	}

	const setCertification = (value: boolean) => {
		certification.value = value
		updateCourses()
	}

	const loadMore = () => {
		courses.next()
	}

	watch(currentTab, () => {
		updateCourses()
	})

	const courseTabs = computed<Tab[]>(() => {
		let tabs = [
			{
				label: __('Published'),
				value: 'live',
			},
			{
				label: __('Upcoming'),
				value: 'upcoming',
			},
		]
		if (
			user?.data?.is_moderator ||
			user?.data?.is_instructor ||
			user?.data?.is_evaluator
		) {
			tabs.push({ label: __('Created'), value: 'created' })
			tabs.push({ label: __('Unpublished'), value: 'unpublished' })
		} else if (user?.data) {
			tabs.push({ label: __('Enrolled'), value: 'enrolled' })
		}
		return tabs
	})

	return {
		courses,
		categories,
		courseCount,
		loading,
		pageLength,
		title,
		currentCategory,
		certification,
		currentTab,
		courseTabs,
		filters,
		init,
		updateCourses,
		setCertification,
		loadMore,
	}
}
