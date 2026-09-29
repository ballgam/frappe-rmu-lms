<template>
	<header class="sx-navbar relative z-30 bg-surface-white">
		<!-- Staff previewing a course: say so, and give them the way back. -->
		<div
			v-if="isStudentView"
			class="flex items-center justify-center gap-3 bg-[var(--sx-primary-soft)] px-4 py-1 text-p-xs text-ink-gray-8"
		>
			<span class="lucide-eye size-3.5" aria-hidden="true" />
			<span>{{ __('You are previewing as a student') }}</span>
			<button
				type="button"
				class="sx-focus rounded font-medium text-[color:var(--sx-primary-ink)] underline-offset-2 hover:underline"
				@click="exitStudentView"
			>
				{{ __('Exit preview') }}
			</button>
		</div>

		<div
			class="mx-auto flex h-[var(--sx-navbar-height)] w-full max-w-7xl items-center gap-3 px-4 sm:gap-6 sm:px-8"
		>
			<router-link
				:to="homeRoute"
				class="sx-focus flex min-w-0 shrink-0 items-center gap-2.5 rounded-lg"
			>
				<img
					:src="logo"
					:alt="brand.name || __('Home')"
					class="h-8 w-auto max-w-[8rem] object-contain"
				/>
				<span
					class="hidden truncate text-p-base font-semibold text-ink-gray-9 lg:inline"
				>
					{{ brand.name || __('Learning') }}
				</span>
			</router-link>

			<nav
				:aria-label="__('Primary')"
				class="hidden items-center gap-1 md:flex"
			>
				<router-link
					v-for="link in links"
					:key="link.label"
					:to="link.to"
					:aria-current="link.active ? 'page' : undefined"
					class="sx-focus rounded-lg px-3 py-2 text-p-sm font-medium transition-colors hover:bg-surface-gray-2"
					:class="link.active ? 'sx-link-active' : 'text-ink-gray-7'"
				>
					{{ link.label }}
				</router-link>
			</nav>

			<form
				role="search"
				class="hidden min-w-0 flex-1 md:block"
				@submit.prevent="search"
			>
				<label class="sr-only" for="sx-navbar-search">
					{{ __('Search courses') }}
				</label>
				<div class="relative max-w-xl">
					<span
						class="lucide-search pointer-events-none absolute start-3.5 top-1/2 size-4 -translate-y-1/2 text-ink-gray-5"
						aria-hidden="true"
					/>
					<input
						id="sx-navbar-search"
						v-model="query"
						type="search"
						:placeholder="__('Search for courses')"
						class="h-10 w-full rounded-full border border-outline-gray-2 bg-surface-gray-1 ps-10 pe-4 text-p-sm text-ink-gray-9 placeholder:text-ink-gray-5 focus:border-[var(--sx-primary)] focus:bg-surface-white focus:outline-none focus:ring-2 focus:ring-[var(--sx-primary-soft)]"
					/>
				</div>
			</form>

			<div class="ms-auto flex shrink-0 items-center gap-1 sm:gap-2">
				<router-link
					:to="{ name: 'Courses' }"
					class="sx-focus grid size-10 place-items-center rounded-full text-ink-gray-7 hover:bg-surface-gray-2 md:hidden"
					:aria-label="__('Search courses')"
				>
					<span class="lucide-search size-5" aria-hidden="true" />
				</router-link>

				<button
					type="button"
					class="sx-focus hidden size-10 place-items-center rounded-full text-ink-gray-7 hover:bg-surface-gray-2 sm:grid"
					:aria-label="
						theme === 'dark'
							? __('Switch to light mode')
							: __('Switch to dark mode')
					"
					@click="toggleTheme"
				>
					<span
						:class="theme === 'dark' ? 'lucide-sun' : 'lucide-moon'"
						class="size-5"
						aria-hidden="true"
					/>
				</button>

				<template v-if="isLoggedIn">
					<button
						type="button"
						class="sx-focus relative hidden size-10 place-items-center rounded-full text-ink-gray-7 hover:bg-surface-gray-2 md:grid"
						:aria-label="
							unread
								? __('Notifications ({0} unread)').format(unread)
								: __('Notifications')
						"
						@click="toggleNotifications"
					>
						<span class="lucide-bell size-5" aria-hidden="true" />
						<span
							v-if="unread"
							class="absolute end-1.5 top-1.5 grid min-w-[1.1rem] place-items-center rounded-full bg-[var(--sx-accent)] px-1 text-[0.65rem] font-semibold leading-[1.1rem] text-[#1a1300]"
							aria-hidden="true"
						>
							{{ unread > 9 ? '9+' : unread }}
						</span>
					</button>
					<StudentAvatarMenu />
				</template>

				<template v-else>
					<a
						:href="loginUrl"
						class="sx-focus rounded-lg px-3 py-2 text-p-sm font-medium text-ink-gray-8 hover:bg-surface-gray-2"
					>
						{{ __('Log in') }}
					</a>
					<a
						v-if="!signupDisabled"
						:href="signupUrl"
						class="sx-focus sx-btn-primary hidden rounded-lg px-4 py-2 text-p-sm font-medium sm:inline-block"
					>
						{{ __('Sign up') }}
					</a>
				</template>
			</div>
		</div>
	</header>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { sessionStore } from '@/stores/session'
import { useSettings } from '@/stores/settings'
import { toggleNotifications } from '@/stores/notifications'
import { applyTheme, theme, toggleTheme } from '@/utils/theme'
import { useUnreadNotifications } from '@/composables/useUnreadNotifications'
import StudentAvatarMenu from '@/components/StudentShell/StudentAvatarMenu.vue'

const route = useRoute()
const router = useRouter()
const session = sessionStore()
const { brand } = session
const { settings } = useSettings()

const isLoggedIn = computed(() => session.isLoggedIn)
const isStudentView = computed(() => route.query.studentView === '1')

// The UN lockup the catalog was designed around, until Website Settings has a
// logo of its own.
const UN_LOGO = '/assets/lms/frontend/un-somalia-logo.png'
const logo = computed(() => brand.logo || UN_LOGO)

// Guests are sent from Home to the catalog by the router anyway.
const homeRoute = computed(() =>
	isLoggedIn.value ? { name: 'Home' } : { name: 'Courses' }
)

const links = computed(() => {
	const items = [
		{
			label: __('Browse'),
			to: { name: 'Courses' },
			active: ['Courses', 'CourseDetail'].includes(String(route.name)),
		},
	]
	if (isLoggedIn.value) {
		items.push({
			label: __('My learning'),
			to: { name: 'Home' },
			active: route.name === 'Home',
		})
	}
	return items
})

const query = ref('')
watch(
	() => route.query.title,
	(title) => {
		query.value = typeof title === 'string' ? title : ''
	},
	{ immediate: true }
)

const search = () => {
	const title = query.value.trim()
	router.push({ name: 'Courses', query: title ? { title } : {} })
}

const { count: unread } = useUnreadNotifications()

const redirectTo = computed(() =>
	encodeURIComponent(window.location.pathname + window.location.search)
)
const loginUrl = computed(() => `/login?redirect-to=${redirectTo.value}`)
const signupUrl = computed(() => `/login?redirect-to=${redirectTo.value}#signup`)
const signupDisabled = computed(() => Boolean(settings.data?.disable_signup))

const exitStudentView = () => {
	const { studentView, ...rest } = route.query
	router.replace({ query: rest })
}

// The sidebar's UserDropdown applies the stored theme on mount; this shell
// replaces it, so it has to do the same.
onMounted(() => {
	if (['light', 'dark'].includes(theme.value)) applyTheme(theme.value)
})
</script>
