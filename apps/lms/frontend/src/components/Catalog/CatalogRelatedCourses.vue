<template>
	<section v-if="relatedCourses.data?.length">
		<h2 class="text-xl font-semibold text-ink-gray-9">
			{{ __('Related courses') }}
		</h2>
		<!-- Same resource RelatedCourses uses, drawn with the catalog's own card.
		     That card links to CatalogCourseDetail, so the reader stays inside
		     this flow — hence no target="_blank" here; a new tab per related
		     course is a papercut the old grid did not need either. -->
		<div class="mt-5 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
			<CatalogCourseCard
				v-for="course in relatedCourses.data"
				:key="course.name"
				:course="course"
			/>
		</div>
	</section>
</template>

<script setup lang="ts">
import { createResource } from 'frappe-ui'
import { watch } from 'vue'
import CatalogCourseCard from '@/components/Catalog/CatalogCourseCard.vue'
import type { Resource } from '@/types'

const props = defineProps<{ courseName: string }>()

const relatedCourses = createResource({
	url: 'lms.lms.utils.get_related_courses',
	cache: ['related_courses', props.courseName],
	makeParams() {
		return { course: props.courseName }
	},
	auto: true,
}) as Resource<Record<string, any>[] | null>

watch(
	() => props.courseName,
	() => relatedCourses.reload()
)
</script>
