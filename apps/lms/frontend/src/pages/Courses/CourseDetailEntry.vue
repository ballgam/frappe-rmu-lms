<template>
	<CatalogCourseDetail v-if="studentUI" :courseName="courseName" />
	<CourseDetail v-else :courseName="courseName" />
</template>
<script setup>
/**
 * /courses/:courseName: the catalog's course page for the new student
 * experience (including staff previewing in Student View), the tabbed course
 * page with its editor, dashboard and settings for everyone else.
 */
import { defineAsyncComponent, inject } from 'vue'
import { useRoute } from 'vue-router'
import { useStudentExperience } from '@/composables/useStudentExperience'
import { provideStudentView } from '@/composables/useStudentView'

defineProps({
	courseName: { type: String, required: true },
})

const CatalogCourseDetail = defineAsyncComponent(() =>
	import('@/pages/Courses/CatalogCourseDetail.vue')
)
const CourseDetail = defineAsyncComponent(() =>
	import('@/pages/Courses/CourseDetail.vue')
)

const { enabled: studentUI } = useStudentExperience()

// Staff previewing with ?studentView=1 see the page as a learner would: no
// admin shortcuts on the enrolment card. Only with the new experience on, so
// the classic pages behave exactly as before when it is off.
const route = useRoute()
provideStudentView(
	inject('$user'),
	() => studentUI.value && route.query.studentView === '1'
)
</script>
