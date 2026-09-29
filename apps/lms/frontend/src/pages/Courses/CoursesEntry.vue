<template>
	<CourseCatalog v-if="studentUI" />
	<Courses v-else />
</template>
<script setup>
/**
 * /courses: the catalog for the new student experience, the classic list for
 * everyone else. Decided at render time rather than by redirect, so the URL
 * stays the same and switching the setting off takes effect on the next load.
 */
import { defineAsyncComponent, inject } from 'vue'
import { useRoute } from 'vue-router'
import { useStudentExperience } from '@/composables/useStudentExperience'
import { provideStudentView } from '@/composables/useStudentView'

const CourseCatalog = defineAsyncComponent(() =>
	import('@/pages/Courses/CourseCatalog.vue')
)
const Courses = defineAsyncComponent(() => import('@/pages/Courses/Courses.vue'))

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
