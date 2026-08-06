<template>
	<!-- What the hero's Filters button opens. The filters that do not fit the
	     chip row live here; on a phone they get a sheet, because an inline panel
	     under the hero would push the first card off the screen. -->
	<BottomSheet v-if="isMobile" v-model="open" :title="__('Filters')">
		<div class="flex flex-col gap-4 px-3 pb-2">
			<ToggleFilter
				:modelValue="certification"
				:label="__('Certification')"
				:mobileLabel="__('Certification available')"
				:tooltip="__('Only show courses that offer a certificate')"
				@update:modelValue="emit('update:certification', $event)"
			/>
			<Button v-if="canClear" :label="__('Clear filters')" @click="clear" />
		</div>
	</BottomSheet>

	<Transition
		v-else
		enter-active-class="transition duration-150 ease-out"
		enter-from-class="opacity-0 -translate-y-1"
		leave-active-class="transition duration-100 ease-in"
		leave-to-class="opacity-0 -translate-y-1"
	>
		<div
			v-if="open"
			class="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-2xl border bg-surface-white p-4 shadow-[var(--catalog-shadow-card)]"
		>
			<ToggleFilter
				:modelValue="certification"
				:label="__('Certification')"
				:tooltip="__('Only show courses that offer a certificate')"
				@update:modelValue="emit('update:certification', $event)"
			/>
			<button
				v-if="canClear"
				type="button"
				class="ms-auto rounded-md px-2 py-1 text-p-sm font-medium text-[color:var(--catalog-primary-ink)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--catalog-primary)]"
				@click="clear"
			>
				{{ __('Clear filters') }}
			</button>
		</div>
	</Transition>
</template>

<script setup lang="ts">
import { Button } from 'frappe-ui'
import BottomSheet from '@/components/BottomSheet.vue'
import ToggleFilter from '@/components/Controls/ToggleFilter.vue'
import { useScreenSize } from '@/utils/composables'

defineProps<{
	certification: boolean
	/** Whether anything outside this panel is filtering too, for Clear. */
	canClear: boolean
}>()

const emit = defineEmits<{
	'update:certification': [value: boolean]
	clear: []
}>()

const open = defineModel<boolean>({ default: false })

const { isMobile } = useScreenSize()

const clear = () => {
	emit('clear')
	if (isMobile.value) open.value = false
}
</script>
