/**
 * utils/courseEnrollment — the rules both enrolment cards share.
 */
import { describe, expect, it, vi } from 'vitest'

vi.stubGlobal('__', (s: string) => s)

import {
	getContinueRoute,
	getCourseCta,
	getEnrolledLabel,
	getPriceLabel,
	canGetCertificate,
	isCourseAdmin,
} from '@/utils/courseEnrollment'

const course = (extra: Record<string, unknown> = {}) =>
	({ name: 'C', instructors: [{ name: 'i@x.io' }], ...extra }) as any

describe('getCourseCta', () => {
	it.each([
		['member beats everything', { membership: {}, paid_course: 1, disable_self_learning: 1 }, true, 'continue'],
		['paid for a learner', { paid_course: 1, disable_self_learning: 1 }, false, 'billing'],
		['self-learning off', { disable_self_learning: 1 }, false, 'contact_admin'],
		['open course', {}, false, 'enroll'],
		['admin, not a member', { paid_course: 1 }, true, 'none'],
	])('%s', (_label, extra, admin, expected) => {
		expect(getCourseCta(course(extra), admin as boolean)).toBe(expected)
	})

	it('is none before the course loads', () => {
		expect(getCourseCta(null, false)).toBe('none')
	})
})

describe('isCourseAdmin', () => {
	it('is true for a moderator and for an instructor of the course', () => {
		expect(isCourseAdmin({ name: 'm', is_moderator: true }, course())).toBe(true)
		expect(isCourseAdmin({ name: 'i@x.io' }, course())).toBe(true)
	})

	it('is false for anyone else, and for a guest', () => {
		expect(isCourseAdmin({ name: 'other' }, course())).toBe(false)
		expect(isCourseAdmin(null, course())).toBe(false)
	})
})

describe('getContinueRoute', () => {
	it('resumes at current_lesson, else 1-1', () => {
		expect(getContinueRoute(course({ current_lesson: '4-2' })).params).toEqual({
			courseName: 'C',
			chapterNumber: '4',
			lessonNumber: '2',
		})
		expect(getContinueRoute(course()).params).toEqual({
			courseName: 'C',
			chapterNumber: 1,
			lessonNumber: 1,
		})
	})
})

describe('labels', () => {
	it('prices a paid course and calls the rest free', () => {
		expect(getPriceLabel(course({ paid_course: 1, price: '$5' }))).toBe('$5')
		expect(getPriceLabel(course())).toBe('Free')
	})

	it('buckets large enrolment counts', () => {
		expect(getEnrolledLabel(0)).toBe('')
		expect(getEnrolledLabel(49)).toBe('49')
		expect(getEnrolledLabel(120)).toBe('100+')
		expect(getEnrolledLabel(1234)).toBe('1200+')
	})

	it('offers a certificate only at 100% on a certified course', () => {
		expect(canGetCertificate(course({ enable_certification: 1, membership: { progress: 100 } }))).toBe(true)
		expect(canGetCertificate(course({ enable_certification: 1, membership: { progress: 60 } }))).toBe(false)
		expect(canGetCertificate(course({ membership: { progress: 100 } }))).toBe(false)
	})
})
