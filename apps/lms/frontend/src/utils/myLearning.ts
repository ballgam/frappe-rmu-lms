/**
 * Grouping for the student "My learning" page. Pure, so it is tested alone.
 */
type Enrolled = { name: string; membership?: { progress?: number | string } | null }

export type LearningTab = 'in_progress' | 'completed' | 'all'

const progressOf = (course: Enrolled) =>
	Number(course.membership?.progress) || 0

/** Enrolled courses split by progress; a course at 100% counts as completed. */
export function groupByProgress<T extends Enrolled>(courses: T[]) {
	const inProgress: T[] = []
	const completed: T[] = []
	for (const course of courses) {
		if (!course.membership) continue
		if (progressOf(course) >= 100) completed.push(course)
		else inProgress.push(course)
	}
	return {
		in_progress: inProgress,
		completed,
		all: [...inProgress, ...completed],
	}
}

/**
 * The course the "Continue learning" banner offers. get_my_courses lists the
 * learner's enrolments most recently active first, or featured / popular
 * courses when there are none, which carry no membership and are skipped.
 */
export function pickResumeCourse<T extends Enrolled>(
	recent: T[] | null | undefined
): T | null {
	return (
		(recent || []).find(
			(course) => course.membership && progressOf(course) < 100
		) || null
	)
}

/** Which tab to open on: in progress if there is any, else everything. */
export function defaultTab(groups: ReturnType<typeof groupByProgress>): LearningTab {
	return groups.in_progress.length ? 'in_progress' : 'all'
}
