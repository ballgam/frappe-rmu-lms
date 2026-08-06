import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'

// frappe-ui's real entry pulls in a resources plugin that can't resolve under
// vitest, so its primitives are stubbed down to the bare elements this block
// uses — the same approach as EmailAdd/Billing.
vi.mock('frappe-ui', () => ({
	Button: {
		props: ['label', 'variant', 'size', 'disabled'],
		emits: ['click'],
		template: `<button :disabled="disabled" @click="$emit('click')">{{ label }}</button>`,
	},
	FormControl: {
		props: [
			'modelValue',
			'label',
			'type',
			'placeholder',
			'options',
			'size',
			'rows',
			'min',
		],
		emits: ['update:modelValue'],
		template: `<textarea v-if="type === 'textarea'" :value="modelValue"
				@input="$emit('update:modelValue', $event.target.value)"></textarea>
			<input v-else :value="modelValue"
				@input="$emit('update:modelValue', $event.target.value)" />`,
	},
}))

import IframeBlock from '@/components/IframeBlock.vue'

globalThis.__ = (text: string) => text
// eslint-disable-next-line no-extend-native
String.prototype.format = function (...args: unknown[]) {
	return this.replace(/{(\d+)}/g, (match, index) =>
		args[index] !== undefined ? String(args[index]) : match
	)
}

const HOSTS = ['h5p.org', 'miro.com']

const mountBlock = (props = {}) =>
	mount(IframeBlock, {
		props: { data: {}, readOnly: false, allowedHosts: HOSTS, ...props },
		global: { mocks: { __: (s: string) => s } },
	})

const embed = async (wrapper: VueWrapper, input: string) => {
	await wrapper.find('textarea').setValue(input)
	await wrapper.findAll('button').at(-1)!.trigger('click')
}

describe('IframeBlock — authoring', () => {
	let wrapper: VueWrapper

	beforeEach(() => {
		wrapper = mountBlock()
	})

	it('starts on the input form with no frame', () => {
		expect(wrapper.find('textarea').exists()).toBe(true)
		expect(wrapper.find('iframe').exists()).toBe(false)
	})

	it('renders a frame from a pasted embed snippet and emits the saved data', async () => {
		await embed(
			wrapper,
			'<iframe src="https://h5p.org/h5p/embed/1234" width="800" height="450" allowfullscreen></iframe>'
		)

		const frame = wrapper.find('iframe')
		expect(frame.exists()).toBe(true)
		expect(frame.attributes('src')).toBe('https://h5p.org/h5p/embed/1234')

		const change = wrapper.emitted('change')
		expect(change).toBeTruthy()
		expect(change!.at(-1)![0]).toMatchObject({
			src: 'https://h5p.org/h5p/embed/1234',
			aspectRatio: '16:9',
			height: null,
			allowFullscreen: true,
		})
	})

	it('renders a frame from a plain link', async () => {
		await embed(wrapper, 'https://miro.com/app/embed/abc/')
		expect(wrapper.find('iframe').attributes('src')).toBe(
			'https://miro.com/app/embed/abc/'
		)
	})

	// Third-party content is untrusted; these attributes are the containment.
	it('sandboxes the frame and sets safe loading/referrer attributes', async () => {
		await embed(wrapper, 'https://miro.com/app/embed/abc/')
		const frame = wrapper.find('iframe')
		expect(frame.attributes('sandbox')).toBe(
			'allow-scripts allow-same-origin allow-popups allow-forms allow-presentation'
		)
		expect(frame.attributes('loading')).toBe('lazy')
		expect(frame.attributes('referrerpolicy')).toBe(
			'strict-origin-when-cross-origin'
		)
		// Never a fixed pixel width — that is what overflows on a phone.
		expect(frame.attributes('width')).toBeUndefined()
	})

	it('names the host in the error when it is not on the allowlist', async () => {
		await embed(wrapper, 'https://attacker.test/evil')
		expect(wrapper.find('iframe').exists()).toBe(false)
		expect(wrapper.text()).toContain('attacker.test')
		expect(wrapper.emitted('change')).toBeFalsy()
	})

	it('rejects a javascript: src', async () => {
		await embed(wrapper, '<iframe src="javascript:alert(1)"></iframe>')
		expect(wrapper.find('iframe').exists()).toBe(false)
		expect(wrapper.emitted('change')).toBeFalsy()
	})

	// A YouTube link must become an `embed` block, or the lesson loses the Plyr
	// player, the video progress tracking and the outline's video icon.
	it('hands a known video service off instead of framing it', async () => {
		await embed(wrapper, 'https://www.youtube.com/watch?v=QhA4h6qD4wY')
		const convert = wrapper.emitted('convert')
		expect(convert).toBeTruthy()
		expect(convert![0][0]).toMatchObject({
			service: 'youtube',
			embed: 'QhA4h6qD4wY',
		})
		expect(wrapper.find('iframe').exists()).toBe(false)
	})

	it('hands off a known service even though its host is not on the allowlist', async () => {
		// youtube.com is absent from HOSTS above: the handoff is decided before
		// the allowlist check, because the `embed` block is a trusted path.
		await embed(wrapper, 'https://vimeo.com/76979871')
		expect(wrapper.emitted('convert')).toBeTruthy()
	})
})

describe('IframeBlock — saved data', () => {
	it('restores a frame from existing block data', () => {
		const wrapper = mountBlock({
			data: {
				src: 'https://h5p.org/h5p/embed/1',
				caption: 'Try it',
				aspectRatio: 'custom',
				height: 900,
			},
		})
		expect(wrapper.find('iframe').attributes('src')).toBe(
			'https://h5p.org/h5p/embed/1'
		)
		expect(wrapper.find('textarea').exists()).toBe(false)
	})
})

describe('IframeBlock — read-only (learner view)', () => {
	const readOnly = (data: object) => mountBlock({ data, readOnly: true })

	it('renders the frame and caption with no authoring controls', () => {
		const wrapper = readOnly({
			src: 'https://h5p.org/h5p/embed/1',
			caption: 'Try it',
		})
		expect(wrapper.find('iframe').attributes('src')).toBe(
			'https://h5p.org/h5p/embed/1'
		)
		expect(wrapper.text()).toContain('Try it')
		expect(wrapper.find('textarea').exists()).toBe(false)
		expect(wrapper.find('button').exists()).toBe(false)
	})

	// Content saved while a domain was allowed must stop framing once an
	// administrator removes it, without waiting for the lesson to be re-saved.
	it('hides a frame whose host has since been removed from the allowlist', () => {
		const wrapper = readOnly({
			src: 'https://removed.test/x',
			caption: 'Try it',
		})
		expect(wrapper.find('iframe').exists()).toBe(false)
		expect(wrapper.text()).toContain('no longer allowed')
		expect(wrapper.text()).not.toContain('Try it')
	})

	it('renders nothing for an empty block', () => {
		const wrapper = readOnly({})
		expect(wrapper.find('iframe').exists()).toBe(false)
		expect(wrapper.text()).toBe('')
	})
})
