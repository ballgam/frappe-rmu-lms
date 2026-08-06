import { createApp, h, type App } from 'vue'
import { Frame } from 'lucide-vue-next'
import translationPlugin from '@/translation'
import IframeBlock from '@/components/IframeBlock.vue'
import {
	resolveAllowedHosts,
	type EmbedData,
	type KnownService,
} from '@/utils/iframeEmbed'

type IframeConfig = {
	allowedHosts?: string
}

/**
 * EditorJS block for embedding third-party content — a provider's <iframe>
 * snippet or a plain link.
 *
 * Unlike the `embed` tool (which has no toolbox and only triggers on pasting a
 * URL matching one of a dozen hardcoded services) this one appears in the "+"
 * menu, so embedding is discoverable and isn't limited to that service list.
 *
 * What gets saved is src + primitives, never HTML: see the note at the top of
 * utils/iframeEmbed.ts for why the sanitizers leave no other option.
 */
export class Iframe {
	data: Partial<EmbedData>
	api: any
	block: any
	readOnly: boolean
	allowedHosts: readonly string[]
	wrapper!: HTMLDivElement
	app: App | null = null

	constructor({
		data,
		api,
		block,
		readOnly,
		config,
	}: {
		data: Partial<EmbedData>
		api: any
		block?: any
		readOnly: boolean
		config?: IframeConfig
	}) {
		this.data = data || {}
		this.api = api
		this.block = block
		this.readOnly = readOnly
		// The allowlist arrives through tool config rather than being read from
		// the settings store in here: EditorJS blocks are mounted outside the
		// app's Vue tree, the same reason `assignment` and `program` take their
		// studentView flag this way.
		this.allowedHosts = resolveAllowedHosts(config?.allowedHosts)
	}

	static get toolbox() {
		const app = createApp({
			render: () => h(Frame, { size: 5, strokeWidth: 1.5 }),
		})

		const div = document.createElement('div')
		app.mount(div)

		return {
			title: __('Embed'),
			icon: div.innerHTML,
		}
	}

	static get isReadOnlySupported() {
		return true
	}

	render() {
		this.wrapper = document.createElement('div')

		this.app = createApp(IframeBlock, {
			data: this.data,
			readOnly: this.readOnly,
			allowedHosts: this.allowedHosts,
			onChange: (data: EmbedData) => {
				this.data = data
			},
			onConvert: (known: KnownService & { caption?: string }) => {
				this.convertToEmbed(known)
			},
		})
		this.app.use(translationPlugin)
		this.app.mount(this.wrapper)

		return this.wrapper
	}

	/**
	 * Swap this block for an `embed` one when the author pasted a YouTube/Vimeo/
	 * Cloudflare/Bunny link, so the lesson keeps the Plyr player, the video
	 * progress tracking and the video icon in the course outline — all three
	 * check for type === 'embed'.
	 */
	convertToEmbed(known: KnownService & { caption?: string }) {
		const index = this.block?.id
			? this.api.blocks.getBlockIndex(this.block.id)
			: -1
		if (index < 0) return

		// Deferred: replacing the block destroys this tool, which unmounts the
		// Vue app we're currently inside an event handler of.
		setTimeout(() => {
			this.api.blocks.insert(
				'embed',
				{
					service: known.service,
					source: known.source,
					embed: known.embed,
					caption: known.caption || '',
				},
				{},
				index,
				true,
				true
			)
		}, 0)
	}

	// Drop blocks the author never filled in, rather than persisting an empty
	// frame that renders as a grey box in the lesson.
	validate(saved: Partial<EmbedData>) {
		return Boolean(saved?.src)
	}

	save(): EmbedData {
		return {
			src: this.data.src || '',
			title: this.data.title || '',
			caption: this.data.caption || '',
			aspectRatio: this.data.aspectRatio || '16:9',
			height: this.data.height ?? null,
			allowFullscreen: this.data.allowFullscreen !== false,
		}
	}

	destroy() {
		this.app?.unmount()
		this.app = null
	}
}
