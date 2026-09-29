<template>
	<!-- The catalog's masthead: a gradient band that runs the full width of the
	     page, under the student navbar (which carries the brand, search and
	     account menu).

	     The UN treatment keeps the navy band but tightens the vertical rhythm
	     and layers three faint marks over the gradient: a longitude grid (the
	     world the emblem maps), a wash of the lockup itself, and a blurred
	     accent orb in the corner. All three are decorative, so they are plain
	     divs rather than meaningful content. -->
	<section class="catalog-hero relative overflow-hidden">
		<div aria-hidden="true" class="catalog-hero-grid" />
		<div aria-hidden="true" class="catalog-hero-glow" />
		<div aria-hidden="true" class="catalog-hero-emblem">
			<img :src="UN_LOGO" alt="" />
		</div>

		<div
			class="relative mx-auto w-full max-w-7xl px-5 pb-16 pt-5 sm:px-8 sm:pb-20"
		>
			<!-- Page actions (e.g. staff's Create menu). Brand and account links
			     live in the student navbar above the hero. -->
			<div v-if="$slots.actions" class="flex justify-end">
				<slot name="actions" />
			</div>

			<div class="mt-4 sm:mt-8">
				<!-- Editorial kicker: a short UN-blue rule instead of the old
				     pill chip, so the heading can carry the whole first beat. -->
				<div class="flex items-center gap-3">
					<span
						class="h-px w-10 shrink-0 bg-[var(--catalog-primary)]"
						aria-hidden="true"
					/>
					<span
						class="text-[0.7rem] font-semibold uppercase tracking-[0.22em] text-[color:var(--catalog-hero-ink-muted)]"
					>
						{{ __('Catalog') }}
					</span>
				</div>

				<h1
					class="mt-6 max-w-2xl text-4xl font-light leading-[1.08] tracking-tight text-[color:var(--catalog-hero-ink)] sm:text-6xl"
				>
					{{ __('Learn something') }}<br />
					<span class="font-medium">{{ __('worth finishing.') }}</span>
				</h1>
				<p
					class="mt-5 max-w-xl text-p-lg leading-relaxed text-[color:var(--catalog-hero-ink-muted)]"
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
					     control. Visually hidden so the hero keeps the mock's line.
					     The glassy fill reads as part of the band rather than a
					     floating white pill. -->
					<label class="relative min-w-0 flex-1">
						<span class="sr-only">{{ __('Search courses') }}</span>
						<span
							class="lucide-search pointer-events-none absolute start-4 top-1/2 size-4 -translate-y-1/2 text-[color:var(--catalog-hero-ink-muted)]"
						/>
						<input
							:value="search"
							type="search"
							:placeholder="__('Search courses or instructors')"
							class="h-12 w-full rounded-2xl border border-[color:var(--catalog-hero-border)] bg-[color:var(--catalog-hero-chip)] ps-11 pe-4 text-p-base text-[color:var(--catalog-hero-ink)] outline-none backdrop-blur-md transition-colors placeholder:text-[color:var(--catalog-hero-ink-muted)] focus:border-[color:var(--catalog-primary)]"
							@input="
								emit('update:search', ($event.target as HTMLInputElement).value)
							"
						/>
					</label>
					<button
						type="button"
						:aria-expanded="filtersOpen"
						class="inline-flex h-12 shrink-0 items-center gap-2 rounded-2xl border border-[color:var(--catalog-hero-border)] bg-[color:var(--catalog-hero-chip)] px-5 text-p-base font-semibold text-[color:var(--catalog-hero-ink)] backdrop-blur-md transition-colors hover:bg-white/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
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

// The UN Somalia lockup, served from the frontend's public folder; used here
// only as the faint watermark over the band.
const UN_LOGO = '/assets/lms/frontend/un-somalia-logo.png'
</script>

<style scoped>
/* A longitude/latitude grid, faded out towards the bottom-right so the
   headline stays the loudest thing on the band. */
.catalog-hero-grid {
	position: absolute;
	inset: 0;
	background-image:
		repeating-linear-gradient(
			90deg,
			rgb(255 255 255 / 0.05) 0 1px,
			transparent 1px 64px
		),
		repeating-linear-gradient(
			0deg,
			rgb(255 255 255 / 0.05) 0 1px,
			transparent 1px 64px
		);
	-webkit-mask-image: radial-gradient(
		120% 95% at 25% 0%,
		black 25%,
		transparent 72%
	);
	mask-image: radial-gradient(120% 95% at 25% 0%, black 25%, transparent 72%);
	pointer-events: none;
}

/* A blurred accent orb in the top-right corner, so the navy band gets a warm
   counterpoint to the blue corner light .catalog-hero::after already adds.
   Decorative, hence a plain div rather than content. */
.catalog-hero-glow {
	position: absolute;
	inset-block-start: -10rem;
	inset-inline-end: -6rem;
	width: 26rem;
	height: 26rem;
	border-radius: 9999px;
	background: radial-gradient(
		circle,
		rgb(242 169 0 / 0.18) 0%,
		transparent 65%
	);
	filter: blur(48px);
	pointer-events: none;
}

/* A wash of the lockup itself, tucked into the bottom-right corner like a
   watermark. The slight rotation stops it reading as a mis-dropped image. */
.catalog-hero-emblem {
	position: absolute;
	inset-block-end: -9rem;
	inset-inline-end: -6rem;
	width: 34rem;
	opacity: 0.14;
	transform: rotate(-6deg);
	pointer-events: none;
}

.catalog-hero-emblem img {
	width: 100%;
	height: auto;
}

@media (max-width: 767px) {
	.catalog-hero-emblem {
		display: none;
	}
}
</style>
