<template>
	<div class="mt-7 mb-10">
		<h2 class="mb-3 text-lg-semibold text-ink-gray-9">
			{{ __('Certificates') }}
		</h2>
		<div
			v-if="certificates.data?.length"
			class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
		>
			<!-- New student experience: the same link, drawn as a certificate
			     card with a download affordance. -->
			<a
				v-for="certificate in certificates.data"
				:key="certificate.name"
				:href="certificateUrl(certificate)"
				target="_blank"
				rel="noopener noreferrer"
				:class="
					studentUI
						? 'catalog-panel group flex gap-4 rounded-2xl border bg-surface-white p-5 transition-colors hover:border-[var(--sx-primary)]'
						: 'flex flex-col bg-surface-base border rounded-lg p-3 cursor-pointer hover:bg-surface-sidebar'
				"
			>
				<span
					v-if="studentUI"
					class="grid size-11 shrink-0 place-items-center rounded-xl bg-[var(--sx-primary-soft)]"
					aria-hidden="true"
				>
					<span class="lucide-award size-6 text-[color:var(--sx-primary-ink)]" />
				</span>
				<div :class="studentUI ? 'flex min-w-0 flex-1 flex-col' : 'contents'">
					<div class="font-medium leading-5 mb-2 text-ink-gray-9">
						{{ certificate.course_title || certificate.batch_title }}
					</div>
					<div class="text-sm-medium text-ink-gray-7 mt-auto">
						<span> {{ __('Issued on') }}: </span>
						{{ dayjs(certificate.issue_date).format('DD MMM YYYY') }}
					</div>
					<span
						v-if="studentUI"
						class="mt-3 inline-flex items-center gap-1.5 text-p-sm font-medium text-[color:var(--sx-primary-ink)] group-hover:underline"
					>
						<span class="lucide-download size-4" aria-hidden="true" />
						{{ __('Download PDF') }}
					</span>
				</div>
			</a>
		</div>
		<div v-else class="text-sm italic text-ink-gray-5">
			{{ __('You have not received any certificates yet.') }}
		</div>
	</div>
</template>
<script setup>
import { createListResource } from 'frappe-ui'
import { inject, onMounted } from 'vue'
import { useStudentExperience } from '@/composables/useStudentExperience'

const dayjs = inject('$dayjs')
const { enabled: studentUI } = useStudentExperience()
const props = defineProps({
	profile: {
		type: Object,
		required: true,
	},
})

onMounted(() => {
	if (props.profile.data?.name) {
		certificates.reload()
	}
})

const certificates = createListResource({
	doctype: 'LMS Certificate',
	filters: {
		member: props.profile.data?.name,
	},
	fields: ['name', 'course_title', 'batch_title', 'issue_date', 'template'],
	cache: ['certificates', props.profile.data?.name],
})

const certificateUrl = (certificate) =>
	`/api/method/frappe.utils.print_format.download_pdf?doctype=LMS+Certificate&name=${
		certificate.name
	}&format=${encodeURIComponent(certificate.template)}`
</script>
