<template>
	<FrappeUIProvider>
		<Layout class="isolate text-p-base">
			<router-view />
		</Layout>
		<NotificationPanel />
		<InstallPrompt v-if="isMobile && !settings.data?.disable_pwa" />
		<Dialogs />
	</FrappeUIProvider>
</template>
<script setup>
import { FrappeUIProvider } from 'frappe-ui'
import { Dialogs } from '@/utils/dialogs'
import { computed, watchEffect } from 'vue'
import { useScreenSize } from './utils/composables'
import { useSettings } from '@/stores/settings'
import { useRoute } from 'vue-router'
import DesktopLayout from './components/Layouts/DesktopLayout.vue'
import MobileLayout from './components/Layouts/MobileLayout.vue'
import NoSidebarLayout from './components/Layouts/NoSidebarLayout.vue'
import StudentLayout from './components/StudentShell/StudentLayout.vue'
import { useStudentExperience } from '@/composables/useStudentExperience'
import InstallPrompt from './components/InstallPrompt.vue'
import NotificationPanel from '@/components/Notifications/NotificationPanel.vue'

const { isMobile } = useScreenSize()
const route = useRoute()
const { settings } = useSettings()
const { enabled: studentUI } = useStudentExperience()

// Lesson blocks (quiz, video) mount as separate Vue apps and assignments load
// in an iframe, so the student palette has to hang off <html> to reach them.
watchEffect(() => {
	document.documentElement.toggleAttribute('data-student-ui', studentUI.value)
})

// Derive the layout from the current route, not a navigation guard. Flipping it
// in beforeEach swaps the layout the instant a navigation starts — before a lazy
// route component resolves — which re-mounts <router-view> while the old page is
// still showing, flashing it back into view. A route-driven computed changes in
// the same tick as the route, so the swap and the page change happen together.
// `meta.noSidebar` is how a route asks for the bare layout: it travels with the
// route definition instead of adding another path to match on here.
const embedded = computed(
	() => Boolean(route.query.fromLesson) || route.path === '/persona'
)

const Layout = computed(() => {
	// Iframed lesson blocks stay bare whoever is viewing.
	if (embedded.value) {
		return NoSidebarLayout
	}
	// Admin-only screens keep the staff shell even for an instructor who
	// follows a link out of Student View.
	if (studentUI.value && !route.meta.adminOnly) {
		return StudentLayout
	}
	if (route.meta.noSidebar) {
		return NoSidebarLayout
	}
	if (isMobile.value) {
		return MobileLayout
	}
	return DesktopLayout
})
</script>
