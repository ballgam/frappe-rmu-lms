<template>
	<!-- The catalog's masthead: a gradient band that runs the full width of the
	     page, since this route drops the app sidebar.

	     That is also why it carries a nav bar. Without the sidebar there is no
	     other way back into the app and no account menu, so the hero has to
	     supply both or the page is a dead end — on a phone especially, where
	     the bottom nav goes with the sidebar. -->
	<section class="catalog-hero relative overflow-hidden">
		<div class="relative mx-auto w-full max-w-7xl px-5 pb-12 pt-5 sm:px-8 sm:pb-16">
			<nav
				class="flex items-center justify-between gap-4"
				:aria-label="__('Catalog')"
			>
				<router-link
					:to="{ name: 'Home' }"
					class="flex min-w-0 items-center gap-2 rounded-md text-[color:var(--catalog-hero-ink)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
				>
					<img
						v-if="brand.logo"
						:src="brand.logo"
						:alt="brand.name || __('Home')"
						class="size-7 shrink-0 rounded"
					/>
					<span class="truncate text-p-base font-semibold">
						{{ brand.name || __('Learning') }}
					</span>
				</router-link>

				<div class="flex shrink-0 items-center gap-2">
					<router-link
						:to="{ name: 'Home' }"
						class="hidden items-center gap-1.5 rounded-full px-3 py-1.5 text-p-sm font-medium text-[color:var(--catalog-hero-ink-muted)] transition-colors hover:bg-white/10 hover:text-[color:var(--catalog-hero-ink)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 sm:inline-flex"
					>
						<span class="lucide-arrow-left size-4 rtl:rotate-180" />
						{{ __('Back to Learning') }}
					</router-link>
					<slot name="actions" />
				</div>
			</nav>

			<div class="mt-10 sm:mt-14">
				<span
					class="inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-widest text-[color:var(--catalog-hero-ink)]"
					:style="{
						borderColor: 'var(--catalog-hero-border)',
						background: 'var(--catalog-hero-chip)',
					}"
				>
					<span class="lucide-graduation-cap size-3.5" />
					{{ __('Catalog') }}
				</span>

				<h1
					class="mt-5 max-w-2xl text-4xl font-semibold leading-[1.08] text-[color:var(--catalog-hero-ink)] sm:text-5xl"
				>
					{{ __('Learn something worth finishing.') }}
				</h1>
				<p
					class="mt-4 max-w-xl text-p-base leading-relaxed text-[color:var(--catalog-hero-ink-muted)]"
				>
					{{
						__(
							'Expert-led courses with structured lessons, hands-on projects and progress that follows you across every device.'
						)
					}}
				</p>

				<div class="mt-8 flex max-w-xl gap-3">
					<!-- A label, not a placeholder: the placeholder disappears the
					     moment anything is typed, and this is the page's primary
					     control. Visually hidden so the hero keeps the mock's line. -->
					<label class="relative min-w-0 flex-1">
						<span class="sr-only">{{ __('Search courses') }}</span>
						<span
							class="lucide-search pointer-events-none absolute start-4 top-1/2 size-4 -translate-y-1/2 text-ink-gray-5"
						/>
						<input
							:value="search"
							type="search"
							:placeholder="__('Search courses or instructors')"
							class="h-12 w-full rounded-full border border-transparent bg-surface-white ps-11 pe-4 text-p-base text-ink-gray-9 shadow-[var(--catalog-shadow-card)] outline-none placeholder:text-ink-gray-5 focus:border-[color:var(--catalog-primary)]"
							@input="
								emit('update:search', ($event.target as HTMLInputElement).value)
							"
						/>
					</label>
					<button
						type="button"
						:aria-expanded="filtersOpen"
						class="inline-flex h-12 shrink-0 items-center gap-2 rounded-full bg-surface-white px-5 text-p-base font-semibold text-ink-gray-9 shadow-[var(--catalog-shadow-card)] transition-colors hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
						@click="emit('toggle-filters')"
					>
						<span class="lucide-sliders-horizontal size-4" />
						<span class="hidden sm:inline">{{ __('Filters') }}</span>
						<span
							v-if="activeFilterCount"
							class="grid size-5 place-items-center rounded-full bg-[color:var(--catalog-primary)] text-xs font-semibold text-white"
						>
							{{ activeFilterCount }}
						</span>
					</button>
				</div>
			</div>
		</div>
	</section>
</template>

<script setup lang="ts">
import { sessionStore } from '@/stores/session'

defineProps<{
	search: string
	filtersOpen: boolean
	/** Shown on the Filters button so a collapsed panel still says it is on. */
	activeFilterCount: number
}>()

const emit = defineEmits<{
	'update:search': [value: string]
	'toggle-filters': []
}>()

const { brand } = sessionStore()
</script>
