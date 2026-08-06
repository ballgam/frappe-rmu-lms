<template>
	<div
		class="catalog-panel overflow-hidden rounded-2xl border bg-surface-white"
	>
		<div v-if="outline.loading && !outline.data" class="p-4">
			<SkeletonLoader variant="list" :count="4" />
		</div>

		<div
			v-else-if="!hasContent"
			class="flex items-center justify-center px-4 py-12 text-center"
		>
			<span class="text-p-sm text-ink-gray-5">
				{{ __('Course Content coming soon!') }}
			</span>
		</div>

		<div v-else class="divide-y divide-outline-gray-2">
			<Disclosure
				v-for="chapter in chapters"
				:key="chapter.name"
				v-slot="{ open }"
				:defaultOpen="chapter.idx === 1"
			>
				<!-- A SCORM chapter has no expandable outline: the package is the
				     lesson. Its header navigates straight to the player, so it is a
				     link-shaped row rather than an accordion button. -->
				<button
					v-if="chapter.is_scorm_package"
					type="button"
					class="flex w-full items-center gap-4 px-5 py-5 text-start transition-colors hover:bg-surface-gray-1 sm:px-6"
					@click="openScormChapter(chapter)"
				>
					<span class="lucide-package size-4 shrink-0 text-ink-gray-6" />
					<span class="min-w-0 flex-1 font-semibold text-ink-gray-9">
						{{ chapter.title }}
					</span>
					<span
						v-if="isScormComplete(chapter)"
						class="lucide-check size-4 shrink-0 text-green-700"
						:title="__('Completed')"
					/>
					<span
						class="lucide-arrow-right size-4 shrink-0 text-ink-gray-5 rtl:rotate-180"
						aria-hidden="true"
					/>
				</button>

				<template v-else>
					<DisclosureButton
						class="flex w-full items-center gap-4 px-5 py-5 text-start transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[color:var(--catalog-primary)] sm:px-6"
					>
						<span
							class="lucide-chevron-down size-4 shrink-0 transition-transform motion-reduce:transition-none"
							:class="open ? '' : '-rotate-90 rtl:rotate-90'"
							:style="{ color: 'var(--catalog-primary-ink)' }"
							aria-hidden="true"
						/>
						<span class="min-w-0 flex-1 font-semibold text-ink-gray-9">
							{{ chapter.title }}
						</span>
						<span class="shrink-0 text-p-sm text-ink-gray-5">
							{{ chapter.lessons?.length || 0 }}
							{{
								(chapter.lessons?.length || 0) === 1
									? __('lesson')
									: __('lessons')
							}}
						</span>
					</DisclosureButton>

					<DisclosurePanel>
						<ul
							class="border-t border-outline-gray-2 bg-surface-gray-1 px-5 py-1 sm:px-6"
						>
							<li
								v-for="lesson in chapter.lessons"
								:key="lesson.name"
								class="border-b border-outline-gray-2 last:border-0"
							>
								<router-link
									:to="lessonRoute(lesson)"
									class="-mx-2 flex items-center gap-3 rounded-md px-2 py-3 text-p-sm text-ink-gray-8 transition-colors hover:bg-surface-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--catalog-primary)]"
								>
									<span
										class="size-4 shrink-0"
										:class="lessonIcon(lesson)"
										:style="{ color: 'var(--catalog-primary-ink)' }"
										aria-hidden="true"
									/>
									<span class="min-w-0 flex-1 truncate">{{ lesson.title }}</span>
									<span
										v-if="lesson.include_in_preview"
										class="shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold"
										:style="{
											background: 'var(--catalog-primary-soft)',
											color: 'var(--catalog-primary-ink)',
										}"
									>
										{{ __('Preview') }}
									</span>
									<span
										v-if="lesson.is_complete"
										class="lucide-check size-4 shrink-0 text-green-700"
										:title="__('Completed')"
									/>
								</router-link>
							</li>
						</ul>
					</DisclosurePanel>
				</template>
			</Disclosure>
		</div>
	</div>
</template>

<script setup lang="ts">
/**
 * The catalog's read-only course outline.
 *
 * A component of its own rather than a restyled CourseOutline: that one carries
 * drag-and-drop, inline rename, delete and a ChapterModal it mounts on every
 * usage, none of which a student page wants. What is ported here is the part
 * that is behaviour rather than chrome — the lesson icon map, the lesson route,
 * SCORM chapters and the completion check.
 */
import { computed, inject, watch } from 'vue'
import { createResource, toast } from 'frappe-ui'
import { useRouter } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import { Disclosure, DisclosureButton, DisclosurePanel } from '@headlessui/vue'
import SkeletonLoader from '@/components/SkeletonLoader.vue'
import type {
	OutlineChapter,
	OutlineLesson,
	Resource,
	SessionUser,
} from '@/types'

const props = withDefaults(
	defineProps<{
		courseName: string
		/** Asks the API for per-lesson completion. Only useful once enrolled. */
		getProgress?: boolean
	}>(),
	{ getProgress: false }
)

const router = useRouter()
const user = inject<SessionUser>('$user')

// getProgress belongs in the cache key. CourseOutline omits it, so a progress
// and a non-progress mount of the same course share one entry.
const outline = createResource({
	url: 'lms.lms.utils.get_course_outline',
	cache: ['catalog_course_outline', props.courseName, props.getProgress],
	makeParams() {
		return { course: props.courseName, progress: props.getProgress }
	},
	auto: true,
}) as Resource<OutlineChapter[] | null>

watch(
	() => props.courseName,
	() => outline.reload()
)

const chapters = computed<OutlineChapter[]>(() => outline.data || [])

const lessonCount = computed<number>(() =>
	chapters.value.reduce((total, c) => total + (c.lessons?.length || 0), 0)
)

const hasContent = computed<boolean>(
	() => chapters.value.length > 0 && lessonCount.value > 0
)

// The page draws the "N chapters · M lessons" line above this card, and there
// is no reason to fetch the outline twice to do it — which is what
// CourseOverview does today.
defineExpose({ chapters, lessonCount, hasContent })

// get_lesson_icon classifies a lesson from its EditorJS blocks; these are the
// five values it can return.
const LESSON_ICONS: Record<string, string> = {
	'icon-youtube': 'lucide-monitor-play',
	'icon-quiz': 'lucide-help-circle',
	'icon-assignment': 'lucide-notebook-pen',
	'icon-code': 'lucide-square-code',
	'icon-list': 'lucide-file-text',
}

function lessonIcon(lesson: OutlineLesson): string {
	return LESSON_ICONS[lesson.icon || ''] || 'lucide-file-text'
}

function lessonRoute(lesson: OutlineLesson): RouteLocationRaw {
	const [chapterNumber, lessonNumber] = lesson.number.split('-')
	return {
		name: 'Lesson',
		params: { courseName: props.courseName, chapterNumber, lessonNumber },
	}
}

function isScormComplete(chapter: OutlineChapter): boolean {
	return Boolean(
		chapter.lessons?.length && chapter.lessons.every((l) => l.is_complete)
	)
}

function openScormChapter(chapter: OutlineChapter): void {
	if (!user?.data) {
		toast.success(__('Please enroll for this course to view this lesson'))
		return
	}
	router.push({
		name: 'SCORMChapter',
		params: { courseName: props.courseName, chapterName: chapter.name },
	})
}
</script>
