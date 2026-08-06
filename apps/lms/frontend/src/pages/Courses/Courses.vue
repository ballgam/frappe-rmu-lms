<template>
	<ListPage
		:breadcrumbs="breadcrumbs"
		:title="__('All Courses')"
		:rows="courses.data || []"
		:loading="loading"
		:total-count="courseCount"
		:has-next-page="courses.hasNextPage"
		v-model:page-length="pageLength"
		empty-name="Courses"
		empty-icon="lucide-book-open"
		@load-more="loadMore()"
	>
		<template #actions>
			<Dropdown
				placement="right"
				side="bottom"
				v-if="canCreateCourse()"
				:options="courseMenu"
			>
				<template v-slot="{ open }">
					<Button variant="solid">
						<template #prefix>
							<span class="lucide-plus size-4" />
						</template>
						{{ __('Create') }}
						<template #suffix>
							<span
								:class="[
									'lucide-chevron-down ms-1 size-4 transform transition-transform',
									open ? 'rotate-180' : '',
								]"
							/>
						</template>
					</Button>
				</template>
			</Dropdown>
		</template>

		<template #filters>
			<TabButtons
				:options="courseTabs"
				v-model="currentTab"
				class="!w-fit shrink-0"
			/>
			<FormControl
				v-model="title"
				:placeholder="__('Search')"
				:aria-label="__('Search')"
				type="text"
				@input="updateCourses()"
			>
				<template #prefix>
					<span class="lucide-search size-4 text-ink-gray-5" />
				</template>
			</FormControl>
			<ClearableCombobox
				v-if="categories.data?.length"
				v-model="currentCategory"
				:options="categories.data.filter((c) => c.value)"
				:placeholder="__('Category')"
				@update:modelValue="updateCourses()"
			/>
			<ToggleFilter
				:modelValue="certification"
				:label="__('Certification')"
				:mobileLabel="__('Certification available')"
				:tooltip="__('Only show courses that offer a certificate')"
				@update:modelValue="setCertification"
			/>
		</template>

		<template #card="{ row }">
			<router-link
				:to="{ name: 'CourseDetail', params: { courseName: row.name } }"
			>
				<CourseCard :course="row" />
			</router-link>
		</template>
	</ListPage>

	<NewCourseModal
		v-if="showCourseModal"
		v-model="showCourseModal"
		:courses="courses"
	/>

	<CourseImportModal
		v-if="showCourseImportModal"
		v-model="showCourseImportModal"
	/>
</template>
<script setup>
import { Button, Dropdown, FormControl, TabButtons, usePageMeta } from 'frappe-ui'
import ClearableCombobox from '@/components/Controls/ClearableCombobox.vue'
import ToggleFilter from '@/components/Controls/ToggleFilter.vue'
import ListPage from '@/components/Layouts/ListPage.vue'
import { computed, onMounted, ref } from 'vue'
import { sessionStore } from '@/stores/session'
import { canCreateCourse } from '@/utils'
import CourseCard from '@/components/CourseCard.vue'
import { useRouter } from 'vue-router'
import NewCourseModal from '@/pages/Courses/NewCourseModal.vue'
import CourseImportModal from '@/pages/Courses/CourseImportModal.vue'
import { useCourseCatalog } from '@/composables/useCourseCatalog'

// The filters, the list and the count are the catalog's, not this page's —
// CourseCatalog.vue draws the same state with a different set of controls.
const {
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
	init,
	updateCourses,
	setCertification,
	loadMore,
} = useCourseCatalog()

const { brand } = sessionStore()
const router = useRouter()
const showCourseModal = ref(false)
const showCourseImportModal = ref(false)

onMounted(() => {
	init()
	// Not a filter, so it is not the catalog's to read: this page is the one
	// that owns the create modal the link is asking to open.
	if (new URLSearchParams(location.search).get('newCourse') == '1') {
		showCourseModal.value = true
	}
})

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

const breadcrumbs = computed(() => [
	{
		label: __('Courses'),
		route: { name: 'Courses' },
	},
])

usePageMeta(() => {
	return {
		title: __('Courses'),
		icon: brand.favicon,
	}
})
</script>
