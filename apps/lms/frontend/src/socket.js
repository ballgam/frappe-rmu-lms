import { io } from 'socket.io-client'
import { socketio_port } from '../../../../sites/common_site_config.json'

// Memoized so the components EditorJS mounts as their own Vue apps (VideoBlock)
// can reach the same connection the main app provides, instead of opening a
// second socket per block.
let socket = null

export function initSocket() {
	if (socket) return socket

	let host = window.location.hostname
	let siteName = window.site_name || host
	let port = window.location.port ? `:${socketio_port}` : ''
	let protocol = port ? 'http' : 'https'
	let url = `${protocol}://${host}${port}/${siteName}`

	socket = io(url, {
		withCredentials: true,
		reconnectionAttempts: 5,
	})
	return socket
}
