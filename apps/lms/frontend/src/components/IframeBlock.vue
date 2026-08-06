<template>
	<!-- Read-only (learner view): just the frame and its caption. -->
	<div v-if="readOnly" class="my-4">
		<div v-if="renderable" :style="frameWrapperStyle" class="w-full">
			<iframe
				:src="src"
				:title="frameTitle"
				:allowfullscreen="allowFullscreen"
				:sandbox="SANDBOX"
				referrerpolicy="strict-origin-when-cross-origin"
				loading="lazy"
				class="w-full h-full rounded-md border border-outline-gray-2"
			></iframe>
		</div>
		<p
			v-else-if="src"
			class="border rounded-md p-4 text-center bg-surface-sidebar text-sm text-ink-gray-6"
		>
			{{
				__('This embedded content is no longer allowed and has been hidden.')
			}}
		</p>
		<p
			v-if="caption && renderable"
			class="mt-2 text-sm text-ink-gray-6 text-center"
		>
			{{ caption }}
		</p>
	</div>

	<!-- Authoring, filled: preview plus the sizing/caption controls. -->
	<div v-else-if="src" class="my-4">
		<div :style="frameWrapperStyle" class="w-full">
			<iframe
				:src="src"
				:title="frameTitle"
				:allowfullscreen="allowFullscreen"
				:sandbox="SANDBOX"
				referrerpolicy="strict-origin-when-cross-origin"
				loading="lazy"
				class="w-full h-full rounded-md border border-outline-gray-2"
			></iframe>
		</div>

		<div class="flex flex-wrap items-end gap-2 mt-2">
			<FormControl
				type="select"
				size="sm"
				:label="__('Size')"
				:options="ratioOptions"
				:modelValue="aspectRatio"
				@update:modelValue="onRatioChange"
			/>
			<FormControl
				v-if="aspectRatio === 'custom'"
				type="number"
				size="sm"
				min="100"
				:label="__('Height (px)')"
				:modelValue="height ?? 400"
				@update:modelValue="onHeightChange"
			/>
			<FormControl
				type="text"
				size="sm"
				class="grow min-w-40"
				:label="__('Caption')"
				:placeholder="__('Optional')"
				:modelValue="caption"
				@update:modelValue="onCaptionChange"
			/>
			<Button size="sm" :label="__('Replace')" @click="reset()" />
		</div>
	</div>

	<!-- Authoring, empty: the one input that takes either form. -->
	<div v-else class="border rounded-md p-4 bg-surface-sidebar my-4">
		<FormControl
			type="textarea"
			:label="__('Paste an embed code or a link')"
			:placeholder="placeholder"
			rows="3"
			v-model="input"
			@keydown.enter.meta.prevent="submit()"
			@keydown.enter.ctrl.prevent="submit()"
		/>
		<div class="flex items-center justify-between gap-2 mt-2">
			<p v-if="error" class="text-sm text-ink-red-3">
				{{ error }}
			</p>
			<span v-else class="text-sm text-ink-gray-5">
				{{
					__('Works with YouTube, Vimeo, Google Docs, Slides, Forms and more.')
				}}
			</span>
			<Button
				variant="solid"
				size="sm"
				:label="__('Embed')"
				:disabled="!input.trim()"
				@click="submit()"
			/>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, FormControl } from 'frappe-ui'
import {
	aspectRatioValue,
	DEFAULT_EMBED_HOSTS,
	isAllowedEmbedHost,
	matchKnownService,
	parseEmbedInput,
	stripAngleBrackets,
	type AspectRatio,
	type EmbedData,
	type KnownService,
} from '@/utils/iframeEmbed'

// Third-party content is untrusted, so the frame gets the same sandbox the
// CodeSandbox service already uses in getEditorTools(): enough to run a real
// interactive embed (H5P, Miro, a form) and nothing more. allow-same-origin is
// safe here because "same origin" for a cross-origin embed is the provider's
// origin, not the LMS's — it never gets access to our DOM or cookies.
const SANDBOX =
	'allow-scripts allow-same-origin allow-popups allow-forms allow-presentation'

const props = withDefaults(
	defineProps<{
		data?: Partial<EmbedData>
		readOnly?: boolean
		allowedHosts?: readonly string[]
	}>(),
	{
		data: () => ({}),
		readOnly: false,
		// Defaults to the built-in list rather than [] — an empty array would mean
		// "nothing is allowed", so a missing prop would silently block every embed.
		allowedHosts: () => DEFAULT_EMBED_HOSTS,
	}
)

// change writes back to the tool's this.data (see utils/iframe.ts) so save()
// stays a plain read of primitives; convert hands a known video URL over to
// the existing `embed` block.
const emit = defineEmits<{
	change: [data: EmbedData]
	convert: [known: KnownService & { caption: string }]
}>()

const src = ref(props.data.src || '')
const title = ref(props.data.title || '')
const caption = ref(props.data.caption || '')
const aspectRatio = ref<AspectRatio>(props.data.aspectRatio || '16:9')
const height = ref<number | null>(props.data.height ?? null)
const allowFullscreen = ref(props.data.allowFullscreen !== false)

const input = ref('')
const error = ref('')

const placeholder = `<iframe src="https://..."></iframe>\n${__('or')}  https://...`

const ratioOptions = [
	{ label: __('Widescreen (16:9)'), value: '16:9' },
	{ label: __('Standard (4:3)'), value: '4:3' },
	{ label: __('Square (1:1)'), value: '1:1' },
	{ label: __('Custom height'), value: 'custom' },
]

const frameTitle = computed(() => title.value || __('Embedded content'))

// Re-checked at render, not just at input: content saved while a domain was
// allowed must stop framing once an administrator removes it.
const renderable = computed(
	() => !!src.value && isAllowedEmbedHost(src.value, props.allowedHosts)
)

// Ratio presets keep the frame responsive; a custom height is the escape hatch
// for embeds a ratio can't express (a tall form, a document). Width is never
// fixed — a hand-typed pixel width is what overflows on a phone.
const frameWrapperStyle = computed(() => {
	if (aspectRatio.value === 'custom') {
		return { height: `${height.value || 400}px` }
	}
	return { aspectRatio: aspectRatioValue(aspectRatio.value) }
})

function emitChange() {
	emit('change', {
		src: src.value,
		title: title.value,
		caption: caption.value,
		aspectRatio: aspectRatio.value,
		height: aspectRatio.value === 'custom' ? height.value || 400 : null,
		allowFullscreen: allowFullscreen.value,
	})
}

function submit() {
	error.value = ''
	const parsed = parseEmbedInput(input.value)
	if (!parsed.ok) {
		error.value = parsed.error
		return
	}

	// A YouTube/Vimeo URL becomes an `embed` block instead, so it keeps the Plyr
	// player, the video-progress tracking and the video icon in the course
	// outline — all of which key off type === 'embed'.
	const known = matchKnownService(parsed.src)
	if (known) {
		emit('convert', { ...known, caption: caption.value })
		return
	}

	if (!isAllowedEmbedHost(parsed.src, props.allowedHosts)) {
		// Name the host and say who can fix it — a bare "not allowed" here just
		// becomes a support ticket.
		error.value = __(
			"{0} isn't on the allowed embed list. Ask an administrator to add it under LMS Settings → Allowed Embed Domains."
		).format(hostOf(parsed.src))
		return
	}

	src.value = parsed.src
	title.value = parsed.title
	aspectRatio.value = parsed.aspectRatio
	height.value = parsed.height
	allowFullscreen.value = parsed.allowFullscreen
	input.value = ''
	emitChange()
}

function hostOf(url: string): string {
	try {
		return new URL(url).hostname
	} catch {
		return url
	}
}

function onRatioChange(value: AspectRatio) {
	aspectRatio.value = value
	if (value === 'custom' && !height.value) height.value = 400
	emitChange()
}

function onHeightChange(value: string | number) {
	const parsed = Number.parseInt(String(value), 10)
	height.value = Number.isFinite(parsed) && parsed > 0 ? parsed : 400
	emitChange()
}

function onCaptionChange(value: string) {
	// Stripped rather than escaped — the sanitizers would rewrite a caption
	// containing < or > on save, so it would not survive a reload as typed.
	caption.value = stripAngleBrackets(value)
	emitChange()
}

function reset() {
	input.value = src.value
	src.value = ''
	error.value = ''
	emitChange()
}
</script>
