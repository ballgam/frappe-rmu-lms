/**
 * Tests for the gate that decides who gets the redesigned student experience.
 * Staff must never be switched into it by accident, and turning the setting
 * off must switch everyone back.
 */
import { describe, expect, it } from 'vitest'
import { isStudentExperience } from '@/utils/studentExperience'

const STUDENT = { is_student: true, is_system_manager: false }
const MODERATOR = { is_student: false, is_moderator: true }
const SYSTEM_MANAGER_ONLY = { is_student: true, is_system_manager: true }

const base = { flag: 1, isLoggedIn: true, user: STUDENT, studentView: false }

describe('isStudentExperience', () => {
	it('is off for everyone when the setting is off', () => {
		expect(isStudentExperience({ ...base, flag: 0 })).toBe(false)
		expect(
			isStudentExperience({ ...base, flag: 0, isLoggedIn: false, user: null })
		).toBe(false)
		expect(
			isStudentExperience({ ...base, flag: 0, user: MODERATOR, studentView: true })
		).toBe(false)
	})

	it('is on for a student', () => {
		expect(isStudentExperience(base)).toBe(true)
	})

	it('is on for a guest browsing the catalog', () => {
		expect(
			isStudentExperience({ ...base, isLoggedIn: false, user: null })
		).toBe(true)
	})

	it('is off for staff', () => {
		expect(isStudentExperience({ ...base, user: MODERATOR })).toBe(false)
	})

	it('is off for a System Manager the backend counts as a student', () => {
		expect(isStudentExperience({ ...base, user: SYSTEM_MANAGER_ONLY })).toBe(
			false
		)
	})

	it('is on for staff previewing in Student View', () => {
		expect(
			isStudentExperience({ ...base, user: MODERATOR, studentView: true })
		).toBe(true)
	})

	it('stays off until a logged-in user has loaded', () => {
		expect(isStudentExperience({ ...base, user: null })).toBe(false)
		expect(isStudentExperience({ ...base, user: undefined })).toBe(false)
	})
})
