<template>
	<FileUploader
		:fileTypes="['image/*', 'video/*', 'audio/*', '.pdf']"
		:uploadArgs="uploadArgs"
		:validateFile="validateFile"
		@success="(data) => addFile(data)"
		ref="fileUploader"
		class="hide"
	/>
</template>
<script setup>
import { FileUploader } from 'frappe-ui'
import { onMounted, ref, nextTick, computed } from 'vue'

const fileUploader = ref(null)
const emit = defineEmits(['fileUploaded'])

const props = defineProps({
	onFileUploaded: {
		type: Function,
		required: true,
	},
	uploadContext: {
		type: Object,
		default: () => ({}),
	},
})

// Attach to the lesson only once it exists: a null docname with doctype set
// makes the File doctype reject the upload.
const uploadArgs = computed(() => {
	const args = { private: true }
	const docname = props.uploadContext?.docname
	if (docname) {
		args.doctype = 'Course Lesson'
		args.docname = docname
		args.fieldname = props.uploadContext?.fieldname || 'content'
	}
	return args
})

onMounted(async () => {
	await nextTick()
	const fileInput = fileUploader.value.$el.querySelector('input[type="file"]')
	if (fileInput) {
		fileInput.click()
	}
})

const addFile = (file) => {
	props.onFileUploaded({
		file_url: file.file_url,
		file_type: file.file_type,
	})
}

// Containers accepted for upload. Wider than what a browser can play natively,
// because uploads are transcoded server-side — an .mkv or .avi carrying several
// translated audio tracks is exactly the case this pipeline exists for, and
// rejecting it here would send instructors away to convert it by hand first.
const ALLOWED_EXTENSIONS = [
	'jpg',
	'jpeg',
	'png',
	'mp4',
	'mov',
	'mkv',
	'avi',
	'webm',
	'm4v',
	'mp3',
	'pdf',
]

const validateFile = (file) => {
	let extension = file.name.split('.').pop().toLowerCase()
	if (!ALLOWED_EXTENSIONS.includes(extension)) {
		return 'Only image, audio, video and PDF files are allowed.'
	}
}

const isVideo = (type) => {
	return ['mov', 'mp4', 'avi', 'mkv', 'webm', 'm4v'].includes(type.toLowerCase())
}

const isAudio = (type) => {
	return ['mp3', 'wav', 'ogg'].includes(type.toLowerCase())
}
</script>
