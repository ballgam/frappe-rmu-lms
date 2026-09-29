import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useSettings } from '@/stores/settings'
import { usersStore } from '@/stores/user'
import { sessionStore } from '@/stores/session'
import { isStudentExperience } from '@/utils/studentExperience'

export { isStudentExperience }

/** Reactive form of isStudentExperience for the current route and user. */
export function useStudentExperience() {
	const route = useRoute()
	const { settings } = useSettings()
	// The store's resource, not inject('$user'): Lesson.vue shadows `$user` with
	// a student-shaped proxy in Student View, and the layout decision has to be
	// made from the real account.
	const { userResource } = usersStore()
	const session = sessionStore()

	const enabled = computed(() =>
		isStudentExperience({
			flag: settings.data?.enable_new_student_ui,
			isLoggedIn: session.isLoggedIn,
			user: userResource.data,
			studentView: route?.query?.studentView === '1',
		})
	)

	return { enabled }
}
