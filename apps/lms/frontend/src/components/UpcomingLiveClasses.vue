<template>
	<!-- Today's and upcoming live classes, with Join (and Start for moderators
	     and evaluators) while a class is running. Shared by both home pages. -->
	<div v-if="myLiveClasses.data?.length">
		<h2 class="font-semibold text-md mb-3 text-ink-gray-9">
			{{ __('Upcoming Live Classes') }}
		</h2>
		<div class="grid grid-cols-1 md:grid-cols-4 gap-5">
			<div
				v-for="cls in myLiveClasses.data"
				:key="cls.name"
				class="border rounded-md hover:border-outline-gray-3 p-3"
			>
				<div class="font-semibold text-ink-gray-9 leading-5 mb-1">
					{{ cls.title }}
				</div>
				<div class="text-ink-gray-5 leading-5 mb-4">
					{{ cls.description }}
				</div>
				<div class="mt-auto space-y-4 text-ink-gray-7">
					<div class="flex items-center gap-x-2">
						<span class="lucide-calendar size-4" />
						<span>
							{{ dayjs(cls.date).format('DD MMMM YYYY') }}
						</span>
					</div>
					<div class="flex items-center gap-x-2">
						<span class="lucide-clock size-4" />
						<span>
							{{ formatTime(cls.time) }} -
							{{ dayjs(getClassEnd(cls)).format('HH:mm A') }}
						</span>
					</div>
					<div
						v-if="canAccessClass(cls)"
						class="flex items-center gap-x-2 text-ink-gray-9 mt-auto"
					>
						<a
							v-if="user.data?.is_moderator || user.data?.is_evaluator"
							:href="cls.start_url"
							target="_blank"
							class="cursor-pointer inline-flex items-center justify-center gap-2 transition-colors focus:outline-none text-ink-gray-8 bg-surface-gray-2 hover:bg-surface-gray-3 active:bg-surface-gray-4 focus-visible:ring focus-visible:ring-outline-gray-3 h-7 text-base px-2 rounded"
							:class="cls.join_url ? 'w-full' : 'w-1/2'"
						>
							<span class="lucide-monitor size-4" />
							{{ __('Start') }}
						</a>
						<a
							:href="cls.join_url"
							target="_blank"
							class="w-full cursor-pointer inline-flex items-center justify-center gap-2 transition-colors focus:outline-none text-ink-gray-8 bg-surface-gray-2 hover:bg-surface-gray-3 active:bg-surface-gray-4 focus-visible:ring focus-visible:ring-outline-gray-3 h-7 text-base px-2 rounded"
						>
							<span class="lucide-video size-4" />
							{{ __('Join') }}
						</a>
					</div>
					<Tooltip
						v-else-if="hasClassEnded(cls)"
						:text="__('This class has ended')"
						placement="right"
					>
						<div class="flex items-center gap-x-2 text-ink-amber-3 w-fit">
							<span class="lucide-info size-4" />
							<span>
								{{ __('Ended') }}
							</span>
						</div>
					</Tooltip>
				</div>
			</div>
		</div>
	</div>
</template>
<script setup lang="ts">
import { inject } from 'vue'
import { Tooltip } from 'frappe-ui'
import { formatTime } from '@/utils'

const dayjs = inject<any>('$dayjs')
const user = inject<any>('$user')

defineProps<{
	myLiveClasses: any
}>()

const getClassEnd = (cls: { date: string; time: string; duration: number }) => {
	const classStart = new Date(`${cls.date}T${cls.time}`)
	return new Date(classStart.getTime() + cls.duration * 60000)
}

const canAccessClass = (cls: {
	date: string
	time: string
	duration: number
}) => {
	if (cls.date < dayjs().format('YYYY-MM-DD')) return false
	if (cls.date > dayjs().format('YYYY-MM-DD')) return false
	if (hasClassEnded(cls)) return false
	return true
}

const hasClassEnded = (cls: {
	date: string
	time: string
	duration: number
}) => {
	const classEnd = getClassEnd(cls)
	const now = new Date()
	return now > classEnd
}
</script>
