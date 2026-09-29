import { computed, inject, onMounted, onUnmounted } from 'vue'
import { createResource } from 'frappe-ui'
import { sessionStore } from '@/stores/session'

/**
 * Unread notification count for the student navbar.
 *
 * The sidebar keeps its own resource (cache key 'Unread Notifications Count').
 * This one uses a separate key on purpose: frappe-ui hands back the existing
 * resource for a repeated key, with the first caller's onSuccess, so sharing a
 * key would let whichever shell mounted first silence the other's updates.
 * `stores/notifications.js` refreshes both keys after marking as read.
 */
export const STUDENT_UNREAD_CACHE_KEY = 'Student Unread Notifications Count'

export function useUnreadNotifications() {
	const session = sessionStore()
	const socket = inject<any>('$socket', null)

	const resource = createResource({
		cache: STUDENT_UNREAD_CACHE_KEY,
		url: 'frappe.client.get_count',
		makeParams() {
			return {
				doctype: 'Notification Log',
				filters: { for_user: session.user, read: 0 },
			}
		},
		auto: Boolean(session.user),
	})

	const onPublish = () => resource.reload()

	onMounted(() => {
		socket?.on('publish_lms_notifications', onPublish)
	})
	onUnmounted(() => {
		// Pass the handler so the sidebar's listener, if mounted, survives.
		socket?.off('publish_lms_notifications', onPublish)
	})

	const count = computed(() => Number(resource.data) || 0)

	return { count, resource }
}
