/**
 * utils/myLearning — grouping for the student "My learning" page.
 */
import { describe, expect, it } from 'vitest'
import { defaultTab, groupByProgress, pickResumeCourse } from '@/utils/myLearning'

const course = (name: string, progress?: number | string | null) => ({
	name,
	membership: progress === null ? null : { progress },
})

describe('groupByProgress', () => {
	it('splits enrolments by progress, 100% counting as completed', () => {
		const groups = groupByProgress([
			course('a', 20),
			course('b', 100),
			course('c', '0'),
			course('d', 100.0),
		])
		expect(groups.in_progress.map((c) => c.name)).toEqual(['a', 'c'])
		expect(groups.completed.map((c) => c.name)).toEqual(['b', 'd'])
		expect(groups.all.map((c) => c.name)).toEqual(['a', 'c', 'b', 'd'])
	})

	it('ignores rows with no membership', () => {
		expect(groupByProgress([course('x', null)]).all).toEqual([])
	})
})

describe('pickResumeCourse', () => {
	it('picks the most recent unfinished enrolment', () => {
		expect(
			pickResumeCourse([course('done', 100), course('next', 30), course('old', 10)])
				?.name
		).toBe('next')
	})

	it('offers nothing when get_my_courses fell back to suggestions', () => {
		expect(pickResumeCourse([course('popular', null)])).toBe(null)
		expect(pickResumeCourse(undefined)).toBe(null)
	})
})

describe('defaultTab', () => {
	it('opens on in progress when there is any, else all', () => {
		expect(defaultTab(groupByProgress([course('a', 10)]))).toBe('in_progress')
		expect(defaultTab(groupByProgress([course('a', 100)]))).toBe('all')
	})
})
