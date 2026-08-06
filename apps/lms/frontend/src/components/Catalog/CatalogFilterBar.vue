<template>
	<div class="flex flex-col gap-4">
		<div class="flex flex-wrap items-center justify-between gap-3">
			<TabButtons :options="tabs" :modelValue="tab" class="!w-fit shrink-0" @update:modelValue="emit('update:tab', $event)" />
			<!-- The count is the answer to whatever the filters just did, so it
			     lives with them rather than in a footer. `courseCount` is null
			     when the endpoint has not answered yet; say nothing rather than
			     flash a zero. -->
			<p
				v-if="count !== null"
				aria-live="polite"
				class="shrink-0 text-p-sm text-ink-gray-6"
			>
				{{ count }} {{ count === 1 ? __('course') : __('courses') }}
			</p>
		</div>

		<!-- Categories as chips, one row that scrolls rather than wraps: the set
		     is server-defined and can be long, and a wrapping row would push the
		     grid down the page by an amount nobody can predict.

		     `-mx-1 px-1` so a focus ring on the first or last chip is not clipped
		     by the scroll box. -->
		<div
			v-if="options.length > 1"
			role="group"
			:aria-label="__('Category')"
			class="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1"
		>
			<button
				v-for="option in options"
				:key="option.value ?? 'all'"
				type="button"
				:aria-pressed="option.value === category"
				:class="[
					'shrink-0 rounded-full border px-4 py-2 text-p-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--catalog-primary)]',
					option.value === category
						? 'border-transparent bg-[color:var(--catalog-primary-ink)] text-white'
						: 'border-outline-gray-2 bg-surface-white text-ink-gray-6 hover:text-ink-gray-9',
				]"
				@click="emit('update:category', option.value)"
			>
				{{ option.label }}
			</button>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { TabButtons } from 'frappe-ui'

type CategoryOption = { label: string; value: string | null }

const props = defineProps<{
	tabs: { label: string; value: string }[]
	tab: string
	categories: CategoryOption[]
	category: string | null
	count: number | null
}>()

const emit = defineEmits<{
	'update:tab': [value: string]
	'update:category': [value: string | null]
}>()

// `get_course_categories` leads its list with a blank option for the combobox's
// clear state. Here that slot is a named chip instead, so drop the blank and
// put "All" in front.
const options = computed<CategoryOption[]>(() => [
	{ label: __('All'), value: null },
	...props.categories.filter((option) => option.value),
])
</script>
