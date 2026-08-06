import { describe, it, expect, vi } from 'vitest'

// The tool mounts a Vue app and pulls in the translation plugin; neither is
// under test here, so both are stubbed down to keep this focused on the tool's
// contract with EditorJS (save/validate/the embed handoff).
vi.mock('@/components/IframeBlock.vue', () => ({
	default: { template: '<div />' },
}))
vi.mock('@/translation', () => ({ default: { install: () => {} } }))

import { Iframe } from '@/utils/iframe'

globalThis.__ = (text: string) => text

const makeTool = (data = {}) => {
	const insert = vi.fn()
	const api = {
		blocks: { insert, getBlockIndex: vi.fn(() => 3) },
	}
	const tool = new Iframe({
		data,
		api,
		block: { id: 'block-abc' },
		readOnly: false,
		config: { allowedHosts: 'h5p.org' },
	})
	return { tool, api, insert }
}

describe('Iframe tool — EditorJS contract', () => {
	it('appears in the "+" toolbox with a title and an icon', () => {
		// Without a static toolbox getter the block is unreachable from the
		// "+" menu — which is the entire point of this block existing.
		expect(Iframe.toolbox.title).toBe('Embed')
		expect(Iframe.toolbox.icon).toContain('<svg')
	})

	it('supports read-only mode', () => {
		// EditorJS throws when rendering a tool without this in the lesson view.
		expect(Iframe.isReadOnlySupported).toBe(true)
	})

	it('saves primitives only — no angle brackets reach block data', () => {
		const { tool } = makeTool({
			src: 'https://h5p.org/h5p/embed/1',
			title: 'A title',
			caption: 'A caption',
			aspectRatio: 'custom',
			height: 900,
			allowFullscreen: false,
		})
		const saved = tool.save()
		expect(saved).toEqual({
			src: 'https://h5p.org/h5p/embed/1',
			title: 'A title',
			caption: 'A caption',
			aspectRatio: 'custom',
			height: 900,
			allowFullscreen: false,
		})
		for (const value of Object.values(saved)) {
			if (typeof value === 'string') expect(value).not.toMatch(/[<>]/)
		}
	})

	it('fills defaults for a block saved before the author configured it', () => {
		expect(makeTool().tool.save()).toEqual({
			src: '',
			title: '',
			caption: '',
			aspectRatio: '16:9',
			height: null,
			allowFullscreen: true,
		})
	})

	it('drops a block the author never filled in', () => {
		const { tool } = makeTool()
		expect(tool.validate({ src: '' })).toBe(false)
		expect(tool.validate({})).toBe(false)
		expect(tool.validate({ src: 'https://h5p.org/x' })).toBe(true)
	})

	// The argument order here is easy to get wrong and would silently insert a
	// second block instead of replacing this one.
	it('replaces itself with an `embed` block at its own index', async () => {
		const { tool, api, insert } = makeTool()
		tool.convertToEmbed({
			service: 'youtube',
			source: 'https://www.youtube.com/watch?v=abc',
			embed: 'abc',
			caption: 'Watch this',
		})

		// Deferred so the block isn't destroyed inside its own event handler.
		expect(insert).not.toHaveBeenCalled()
		await new Promise((resolve) => setTimeout(resolve, 0))

		expect(api.blocks.getBlockIndex).toHaveBeenCalledWith('block-abc')
		expect(insert).toHaveBeenCalledWith(
			'embed',
			{
				service: 'youtube',
				source: 'https://www.youtube.com/watch?v=abc',
				embed: 'abc',
				caption: 'Watch this',
			},
			{},
			3, // the index this block occupies
			true, // focus the replacement
			true // replace, don't insert alongside
		)
	})

	it('does nothing when the block has no resolvable index', async () => {
		const insert = vi.fn()
		const tool = new Iframe({
			data: {},
			api: { blocks: { insert, getBlockIndex: vi.fn(() => -1) } },
			block: { id: 'gone' },
			readOnly: false,
		})
		tool.convertToEmbed({
			service: 'youtube',
			source: 'x',
			embed: 'y',
			caption: '',
		})
		await new Promise((resolve) => setTimeout(resolve, 0))
		expect(insert).not.toHaveBeenCalled()
	})
})
