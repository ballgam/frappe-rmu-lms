<template>
	<nav
		:aria-label="__('Primary')"
		class="standalone:pb-4 z-10 flex w-full items-stretch border-t border-outline-gray-2 bg-surface-white"
	>
		<button
			v-for="tab in tabs"
			:key="tab.label"
			type="button"
			:aria-current="tab.active ? 'page' : undefined"
			class="flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 px-1 py-2"
			@click="tab.onClick"
		>
			<span class="relative">
				<span
					:class="[
						tab.icon,
						tab.active ? 'sx-link-active' : 'text-ink-gray-5',
					]"
					class="block size-6"
					aria-hidden="true"
				/>
				<span
					v-if="tab.badge"
					class="absolute -end-1.5 -top-1 grid min-w-[1rem] place-items-center rounded-full bg-[var(--sx-accent)] px-1 text-[0.6rem] font-semibold leading-4 text-[#1a1300]"
					aria-hidden="true"
				>
					{{ tab.badge > 9 ? '9+' : tab.badge }}
				</span>
			</span>
			<span
				class="max-w-full truncate text-p-xs"
				:class="tab.active ? 'sx-link-active font-medium' : 'text-ink-gray-5'"
			>
				{{ tab.label }}
			</span>
		</button>
	</nav>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { sessionStore } from '@/stores/session'
import { usersStore } from '@/stores/user'
import { panelVisible, toggleNotifications } from '@/stores/notifications'
import { useUnreadNotifications } from '@/composables/useUnreadNotifications'

const route = useRoute()
const router = useRouter()
const session = sessionStore()
const { userResource } = usersStore()
const { count: unread } = useUnreadNotifications()

const name = computed(() => String(route.name))

const tabs = computed(() => {
	const browse = {
		label: __('Browse'),
		icon: 'lucide-search',
		active: ['Courses', 'CourseDetail'].includes(name.value),
		badge: 0,
		onClick: () => router.push({ name: 'Courses' }),
	}
	if (!session.isLoggedIn) {
		const redirect = encodeURIComponent(
			window.location.pathname + window.location.search
		)
		return [
			browse,
			{
				label: __('Log in'),
				icon: 'lucide-log-in',
				active: false,
				badge: 0,
				onClick: () => {
					window.location.href = `/login?redirect-to=${redirect}`
				},
			},
		]
	}
	return [
		browse,
		{
			label: __('My learning'),
			icon: 'lucide-book-open',
			active: name.value === 'Home',
			badge: 0,
			onClick: () => router.push({ name: 'Home' }),
		},
		{
			label: __('Notifications'),
			icon: 'lucide-bell',
			active: panelVisible.value,
			badge: unread.value,
			onClick: () => toggleNotifications(),
		},
		{
			label: __('Account'),
			icon: 'lucide-circle-user',
			active: name.value.startsWith('Profile'),
			badge: 0,
			onClick: () =>
				router.push({
					name: 'ProfileAbout',
					params: { username: userResource.data?.username },
				}),
		},
	]
})
</script>
