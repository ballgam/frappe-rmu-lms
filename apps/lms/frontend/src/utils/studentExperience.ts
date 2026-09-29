/**
 * Whether the current viewer gets the redesigned student experience: the top
 * navbar shell, the catalog on /courses, the new lesson player and so on.
 *
 * Gated by LMS Settings `enable_new_student_ui` so the whole redesign can be
 * switched off without a redeploy; off means every page behaves as before.
 *
 * Staff never get it, except when they opt into Student View to preview a
 * course. `get_user_info` marks anyone without an LMS staff role as a student,
 * which includes a System Manager who holds no LMS role, so that role is
 * excluded here explicitly rather than by changing the backend flag other
 * code relies on.
 *
 * Until the user has loaded this stays false: a staff member must never see
 * the student shell flash in, while a student briefly seeing the old shell
 * would be harmless (and the router waits for the user anyway).
 *
 * Kept free of store imports so it can be unit tested on its own; the reactive
 * wrapper is composables/useStudentExperience.
 */
type StudentExperienceInput = {
	flag: unknown
	isLoggedIn: boolean
	user: Record<string, unknown> | null | undefined
	studentView: boolean
}

export function isStudentExperience({
	flag,
	isLoggedIn,
	user,
	studentView,
}: StudentExperienceInput): boolean {
	if (!flag) return false
	if (studentView) return true
	if (!isLoggedIn) return true
	if (!user) return false
	return Boolean(user.is_student && !user.is_system_manager)
}
