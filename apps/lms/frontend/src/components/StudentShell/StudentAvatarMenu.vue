<template>
	<Dropdown :options="options" placement="right">
		<template #default="{ open }">
			<button
				type="button"
				class="sx-focus grid size-10 place-items-center rounded-full transition-shadow"
				:class="open ? 'ring-2 ring-[var(--sx-primary)]' : ''"
				:aria-label="__('Account menu')"
			>
				<UserAvatar :user="userResource.data" size="lg" />
			</button>
		</template>
	</Dropdown>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { Dropdown } from 'frappe-ui'
import { useRouter } from 'vue-router'
import { sessionStore } from '@/stores/session'
import { usersStore } from '@/stores/user'
import { theme, toggleTheme } from '@/utils/theme'
import UserAvatar from '@/components/UserAvatar.vue'

const router = useRouter()
const { logout } = sessionStore()
const { userResource } = usersStore()

// Batches, Programs, Jobs and the rest are deliberately absent: the student
// experience is courses first. Those routes still work by direct URL.
const options = computed(() => {
	const username = userResource.data?.username
	return [
		{
			group: userResource.data?.full_name || '',
			items: [
				{
					label: __('My learning'),
					icon: 'lucide-book-open',
					onClick: () => router.push({ name: 'Home' }),
				},
				{
					label: __('Profile'),
					icon: 'lucide-user',
					onClick: () =>
						router.push({ name: 'ProfileAbout', params: { username } }),
				},
				{
					label: __('Certificates'),
					icon: 'lucide-award',
					onClick: () =>
						router.push({
							name: 'ProfileCertificates',
							params: { username },
						}),
				},
			],
		},
		{
			group: '',
			hideLabel: true,
			items: [
				{
					label: theme.value === 'dark' ? __('Light mode') : __('Dark mode'),
					icon: theme.value === 'dark' ? 'lucide-sun' : 'lucide-moon',
					onClick: () => toggleTheme(),
				},
				{
					label: __('Log out'),
					icon: 'lucide-log-out',
					onClick: () => logout.submit(),
				},
			],
		},
	]
})
</script>
