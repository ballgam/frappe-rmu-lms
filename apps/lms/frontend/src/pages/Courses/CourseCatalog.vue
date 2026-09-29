<template>
	<!-- The student-facing catalog. Same filters, same list resource and same
	     create actions as Courses.vue — all of that lives in useCourseCatalog —
	     drawn as a full-width page with the app sidebar dropped.

	     `lms-catalog` is what scopes the palette in styles/catalog.css; without
	     it every --catalog-* variable below resolves to nothing. -->
	<div class="lms-catalog min-h-full bg-surface-base">
		<CatalogHero
			:search="title"
			:filters-open="filtersOpen"
			:active-filter-count="activeFilterCount"
			@update:search="onSearch"
			@toggle-filters="filtersOpen = !filtersOpen"
		>
			<template #actions>
				<Dropdown
					v-if="canCreateCourse()"
					placement="right"
					side="bottom"
					:options="courseMenu"
				>
					<template v-slot="{ open }">
						<button
							type="button"
							class="inline-flex items-center gap-1.5 rounded-full bg-surface-white px-4 py-2 text-p-sm font-semibold text-ink-gray-9 shadow-sm transition-colors hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
						>
							<span class="lucide-plus size-4" />
							{{ __('Create') }}
							<span
								:class="[
									'lucide-chevron-down size-4 transition-transform',
									open ? 'rotate-180' : '',
								]"
							/>
						</button>
					</template>
				</Dropdown>
			</template>
		</CatalogHero>

		<section class="mx-auto w-full max-w-7xl px-5 py-10 sm:px-8 sm:py-12">
			<div class="flex flex-col gap-4">
				<CatalogFilterBar
					:tabs="courseTabs"
					:tab="currentTab"
					:categories="categories.data || []"
					:category="currentCategory"
					:count="courseCount"
					@update:tab="currentTab = $event"
					@update:category="onCategory"
				/>
				<CatalogFilterPanel
					v-model="filtersOpen"
					:certification="certification"
					:can-clear="activeFilterCount > 0"
					@update:certification="setCertification"
					@clear="clearFilters"
				/>
			</div>

			<div v-if="loading && !rows.length" class="mt-8">
				<div class="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
					<div
						v-for="n in 8"
						:key="n"
						class="h-[22rem] animate-pulse rounded-3xl bg-surface-gray-2"
					/>
				</div>
			</div>

			<div
				v-else-if="rows.length"
				class="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4"
			>
				<CatalogCourseCard
					v-for="course in rows"
					:key="course.name"
					:course="course"
				/>
			</div>

			<!-- Guests get an empty list from get_courses when guest access is off,
			     which is not the same thing as "nothing matched". Say which. -->
			<div v-else class="mx-auto mt-16 max-w-md text-center">
				<span
					class="lucide-book-open mx-auto block size-8 text-ink-gray-4"
					aria-hidden="true"
				/>
				<p class="mt-4 text-p-base text-ink-gray-6">
					{{
						isLoggedIn
							? __('No courses match that search yet.')
							: __('Sign in to browse the course catalog.')
					}}
				</p>
				<Button
					v-if="isLoggedIn && activeFilterCount"
					class="mt-4"
					:label="__('Clear filters')"
					@click="clearFilters"
				/>
				<Button
					v-else-if="!isLoggedIn"
					class="mt-4"
					variant="solid"
					:label="__('Sign in')"
					@click="goToLogin"
				/>
			</div>

			<div
				v-if="rows.length"
				class="mt-10 flex flex-col items-center gap-3 text-p-sm text-ink-gray-5"
			>
				<!-- `hasNextPage` is true before the first response lands, so asking
				     for page two mid-fetch would append onto data that does not
				     exist yet. Same guard ListPage's footer uses. -->
				<Button
					v-if="!loading && courses.hasNextPage"
					:label="__('Load More')"
					@click="loadMore()"
				/>
				<p>
					{{ __('Showing') }} {{ rows.length }}
					<template v-if="courseCount !== null">
						{{ __('of') }} {{ courseCount }}
					</template>
				</p>
			</div>
		</section>

		<NewCourseModal
			v-if="showCourseModal"
			v-model="showCourseModal"
			:courses="courses"
		/>
		<CourseImportModal
			v-if="showCourseImportModal"
			v-model="showCourseImportModal"
		/>
	</div>
</template>

<script setup>
import { Button, Dropdown, usePageMeta } from 'frappe-ui'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { sessionStore } from '@/stores/session'
import { canCreateCourse } from '@/utils'
import { useCourseCatalog } from '@/composables/useCourseCatalog'
import CatalogHero from '@/components/Catalog/CatalogHero.vue'
import CatalogFilterBar from '@/components/Catalog/CatalogFilterBar.vue'
import CatalogFilterPanel from '@/components/Catalog/CatalogFilterPanel.vue'
import CatalogCourseCard from '@/components/Catalog/CatalogCourseCard.vue'
import NewCourseModal from '@/pages/Courses/NewCourseModal.vue'
import CourseImportModal from '@/pages/Courses/CourseImportModal.vue'

const {
	courses,
	categories,
	courseCount,
	loading,
	title,
	currentCategory,
	certification,
	currentTab,
	courseTabs,
	init,
	updateCourses,
	setCertification,
	loadMore,
} = useCourseCatalog()

const { brand, isLoggedIn } = sessionStore()
const router = useRouter()
const route = useRoute()
const showCourseModal = ref(false)
const showCourseImportModal = ref(false)
const filtersOpen = ref(false)

const rows = computed(() => courses.data || [])

const activeFilterCount = computed(
	() => (currentCategory.value ? 1 : 0) + (certification.value ? 1 : 0)
)

onMounted(() => {
	init()
})

// A keystroke used to cost a request each, aborting the last. The list page
// keeps that behaviour; here the search waits for a pause instead, so a typed
// word is one fetch rather than one per letter.
let searchTimer = null

const onSearch = (value) => {
	title.value = value
	clearTimeout(searchTimer)
	searchTimer = setTimeout(updateCourses, 300)
}

onUnmounted(() => {
	clearTimeout(searchTimer)
})

// The student navbar's search pushes ?title= onto this same route, which does
// not remount the page, so pick the new term up here.
watch(
	() => route.query.title,
	(value) => {
		const next = typeof value === 'string' ? value : ''
		if (next === title.value) return
		title.value = next
		clearTimeout(searchTimer)
		updateCourses()
	}
)

const onCategory = (value) => {
	currentCategory.value = value
	updateCourses()
}

const clearFilters = () => {
	currentCategory.value = null
	certification.value = false
	title.value = ''
	clearTimeout(searchTimer)
	updateCourses()
}

const goToLogin = () => {
	window.location.href = '/login'
}

const courseMenu = computed(() => {
	return [
		{
			label: __('New Course'),
			icon: 'lucide-book-open',
			onClick() {
				showCourseModal.value = true
			},
		},
		{
			label: __('Import via Data Import Tool'),
			icon: 'lucide-upload',
			onClick() {
				router.push({
					name: 'NewDataImport',
					params: { doctype: 'LMS Course' },
				})
			},
		},
		{
			label: __('Import via ZIP'),
			icon: 'lucide-folder-plus',
			onClick() {
				showCourseImportModal.value = true
			},
		},
	]
})

usePageMeta(() => {
	return {
		title: __('Courses'),
		icon: brand.favicon,
	}
})
</script>
