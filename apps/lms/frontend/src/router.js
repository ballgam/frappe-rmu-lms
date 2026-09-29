import { createRouter, createWebHistory } from 'vue-router'
import { call } from 'frappe-ui'
import { usersStore } from './stores/user'
import { sessionStore } from './stores/session'
import { useSettings } from './stores/settings'
import { getLmsBasePath } from './utils/basePath'

// Run the fresh-site-admin persona check at most once per app load.
let personaChecked = false

async function shouldCapturePersona() {
	const captured = await call('frappe.client.get_single_value', {
		doctype: 'LMS Settings',
		field: 'persona_captured',
	})
	if (captured) return false
	const courseCount = await call('frappe.client.get_count', {
		doctype: 'LMS Course',
		filters: {
			title: ['not like', '%A guide to Frappe Learning%'],
		},
	})
	return !courseCount
}

// `meta.adminOnly` marks staff screens. With the new student experience on,
// they keep the sidebar shell (see App.vue) instead of the student navbar, so an
// instructor who follows a link out of Student View lands in familiar chrome.
const routes = [
	{
		path: '/',
		name: 'Home',
		component: () => import('@/pages/Home/Home.vue'),
	},
	{
		// The classic list, or the catalog for the new student experience
		// (see CoursesEntry). One URL either way.
		path: '/courses',
		name: 'Courses',
		component: () => import('@/pages/Courses/CoursesEntry.vue'),
	},
	{
		// Where the catalog prototype lived while it was tried against real data.
		path: '/catalog',
		redirect: (to) => ({ name: 'Courses', query: to.query }),
	},
	{
		path: '/catalog/courses/:courseName',
		redirect: (to) => ({
			name: 'CourseDetail',
			params: { courseName: to.params.courseName },
			query: to.query,
		}),
	},
	{
		// The tabbed course page, or the catalog's course page for the new
		// student experience (see CourseDetailEntry).
		path: '/courses/:courseName',
		name: 'CourseDetail',
		component: () => import('@/pages/Courses/CourseDetailEntry.vue'),
		props: true,
	},
	{
		path: '/courses/:courseName/learn/:chapterNumber-:lessonNumber',
		name: 'Lesson',
		component: () => import('@/pages/Lesson.vue'),
		props: true,
	},
	{
		path: '/courses/:courseName/certification',
		name: 'CourseCertification',
		component: () => import('@/pages/Courses/CourseCertification.vue'),
		props: true,
	},
	{
		path: '/courses/:courseName/learn/:chapterName',
		name: 'SCORMChapter',
		component: () => import('@/pages/SCORMChapter.vue'),
		props: true,
	},
	{
		path: '/batches',
		name: 'Batches',
		component: () => import('@/pages/Batches/Batches.vue'),
	},
	{
		path: '/batches/details/:batchName',
		redirect: (to) => `/batches/${to.params.batchName}`,
	},
	{
		path: '/batches/:batchName',
		name: 'BatchDetail',
		component: () => import('@/pages/Batches/BatchDetail.vue'),
		props: true,
	},
	{
		path: '/billing/:type/:name',
		name: 'Billing',
		component: () => import('@/pages/Billing.vue'),
		props: true,
	},
	{
		path: '/statistics',
		name: 'Statistics',
		component: () => import('@/pages/Statistics.vue'),
	},
	{
		path: '/user/:username',
		name: 'Profile',
		component: () => import('@/pages/Profile.vue'),
		props: true,
		redirect: { name: 'ProfileAbout' },
		children: [
			{
				name: 'ProfileAbout',
				path: '',
				component: () => import('@/pages/ProfileAbout.vue'),
			},
			{
				name: 'ProfileCertificates',
				path: 'certificates',
				component: () => import('@/pages/ProfileCertificates.vue'),
			},
			{
				name: 'ProfileRoles',
				path: 'roles',
				component: () => import('@/pages/ProfileRoles.vue'),
			},
			{
				name: 'ProfileEvaluator',
				path: 'slots',
				component: () => import('@/pages/ProfileEvaluator.vue'),
			},
			{
				name: 'ProfileEvaluationSchedule',
				path: 'schedule',
				component: () =>
					import('@/pages/ProfileEvaluationSchedule.vue'),
			},
		],
	},
	{
		path: '/job-openings',
		name: 'Jobs',
		component: () => import('@/pages/Jobs.vue'),
	},
	{
		path: '/job-openings/:job',
		name: 'JobDetail',
		component: () => import('@/pages/JobDetail.vue'),
		props: true,
	},
	{
		path: '/job-openings/:job/applications',
		name: 'JobApplications',
		meta: { adminOnly: true },
		component: () => import('@/pages/JobApplications.vue'),
		props: true,
	},
	{
		path: '/job-opening/:jobName/edit',
		name: 'JobForm',
		meta: { adminOnly: true },
		component: () => import('@/pages/JobForm.vue'),
		props: true,
	},
	{
		path: '/certified-participants',
		name: 'CertifiedParticipants',
		component: () => import('@/pages/CertifiedParticipants.vue'),
	},
	{
		path: '/quizzes',
		name: 'Quizzes',
		meta: { adminOnly: true },
		component: () => import('@/pages/Quizzes.vue'),
	},
	{
		path: '/quizzes/:quizID',
		name: 'QuizForm',
		meta: { adminOnly: true },
		component: () => import('@/pages/QuizForm.vue'),
		props: true,
	},
	{
		path: '/quiz/:quizID',
		name: 'QuizPage',
		component: () => import('@/pages/QuizPage.vue'),
		props: true,
	},
	{
		path: '/quiz-submissions/:quizID',
		name: 'QuizSubmissionList',
		meta: { adminOnly: true },
		component: () => import('@/pages/QuizSubmissionList.vue'),
		props: true,
	},
	{
		path: '/quiz-submission/:submission',
		name: 'QuizSubmission',
		meta: { adminOnly: true },
		component: () => import('@/pages/QuizSubmission.vue'),
		props: true,
	},
	{
		path: '/programs',
		name: 'Programs',
		component: () => import('@/pages/Programs/Programs.vue'),
	},
	{
		path: '/programs/:programName',
		name: 'ProgramDetail',
		component: () => import('@/pages/Programs/ProgramDetail.vue'),
		props: true,
	},
	{
		path: '/assignments',
		name: 'Assignments',
		meta: { adminOnly: true },
		component: () => import('@/pages/Assignments.vue'),
	},
	{
		path: '/assignment-submission/:assignmentID/:submissionName',
		name: 'AssignmentSubmission',
		component: () => import('@/pages/AssignmentSubmission.vue'),
		props: true,
	},
	{
		path: '/assignment-submissions',
		name: 'AssignmentSubmissionList',
		meta: { adminOnly: true },
		component: () => import('@/pages/AssignmentSubmissionList.vue'),
	},
	{
		path: '/persona',
		name: 'PersonaForm',
		meta: { adminOnly: true },
		component: () => import('@/pages/PersonaForm.vue'),
	},
	{
		path: '/programming-exercises',
		name: 'ProgrammingExercises',
		meta: { adminOnly: true },
		component: () =>
			import('@/pages/ProgrammingExercises/ProgrammingExercises.vue'),
	},
	{
		path: '/programming-exercises/submissions',
		name: 'ProgrammingExerciseSubmissions',
		meta: { adminOnly: true },
		component: () =>
			import(
				'@/pages/ProgrammingExercises/ProgrammingExerciseSubmissions.vue'
			),
		props: true,
	},
	{
		path: '/programming-exercises/:exerciseID/submission/:submissionID',
		name: 'ProgrammingExerciseSubmission',
		component: () =>
			import(
				'@/pages/ProgrammingExercises/ProgrammingExerciseSubmission.vue'
			),
		props: true,
	},
	{
		path: '/data-import',
		name: 'DataImportList',
		meta: { adminOnly: true },
		component: () => import('@/pages/DataImport.vue'),
	},
	{
		path: '/data-import/doctype/:doctype',
		name: 'NewDataImport',
		meta: { adminOnly: true },
		component: () => import('@/pages/DataImport.vue'),
		props: true,
	},
	{
		path: '/data-import/:importName',
		name: 'DataImport',
		meta: { adminOnly: true },
		component: () => import('@/pages/DataImport.vue'),
		props: true,
	},
	{
		path: '/:pathMatch(.*)*',
		name: 'NotFound',
		component: () => import('@/pages/NotFound.vue'),
	},
]

let router = createRouter({
	history: createWebHistory(`/${getLmsBasePath()}`),
	routes,
})

router.beforeEach(async (to, from, next) => {
	const { userResource } = usersStore()
	let { isLoggedIn } = sessionStore()
	const { settings } = useSettings()

	try {
		if (isLoggedIn) {
			await userResource.promise
		}
	} catch (error) {
		isLoggedIn = false
	}

	// The layout (student shell or sidebar) depends on an LMS setting; wait for
	// it so the first page renders in the right shell rather than swapping.
	if (isLoggedIn) {
		try {
			await settings.promise
		} catch (_) {
			// Settings failing to load leaves the current UI in place.
		}
	}

	if (!isLoggedIn) {
		if (to.name == 'Home') router.push({ name: 'Courses' })

		await settings.promise
		if (!settings.data.allow_guest_access) {
			window.location.href = '/login'
			return
		}
	}

	if (
		isLoggedIn &&
		!personaChecked &&
		to.name !== 'PersonaForm' &&
		userResource.data?.is_system_manager &&
		!userResource.data?.developer_mode
	) {
		personaChecked = true
		try {
			if (await shouldCapturePersona()) {
				return next({ name: 'PersonaForm' })
			}
		} catch (_) {
			// Fail open — a transient API error must not block navigation.
		}
	}

	return next()
})

export default router
