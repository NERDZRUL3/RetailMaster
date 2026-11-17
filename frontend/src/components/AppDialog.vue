<script setup lang="ts">
// A modal panel: dims the page, closes on Escape or a click outside, keeps
// keyboard focus inside, and gives focus back when it closes.
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const props = withDefaults(defineProps<{ title: string; wide?: boolean }>(), { wide: false })
const emit = defineEmits<{ close: [] }>()
const panel = ref<HTMLElement | null>(null)
let before: Element | null = null

function focusables(): HTMLElement[] {
  return [
    ...(panel.value?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), select, textarea, a[href], [tabindex]:not([tabindex="-1"])',
    ) ?? []),
  ]
}

function onKey(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.stopPropagation()
    emit('close')
  } else if (event.key === 'Tab') {
    const items = focusables()
    if (!items.length) return
    const first = items[0]
    const last = items[items.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }
}

onMounted(() => {
  before = document.activeElement
  nextTick(() => (panel.value?.querySelector<HTMLElement>('[autofocus]') ?? focusables()[0] ?? panel.value)?.focus())
})
onBeforeUnmount(() => (before as HTMLElement | null)?.focus?.())
</script>

<template>
  <Teleport to="body">
    <div class="dialog-backdrop fixed inset-0 z-50 grid place-items-center bg-black/45 p-3 backdrop-blur-sm sm:p-6" @mousedown.self="emit('close')" @keydown="onKey">
      <div
        ref="panel"
        role="dialog"
        aria-modal="true"
        :aria-label="props.title"
        tabindex="-1"
        class="card dialog-panel flex max-h-[calc(100dvh-1.5rem)] w-full flex-col overflow-hidden outline-none sm:max-h-[calc(100dvh-3rem)]"
        :class="wide ? 'max-w-2xl' : 'max-w-md'"
      >
        <div class="flex items-center justify-between gap-3 px-5 pt-5">
          <h2 class="text-[18px] font-semibold text-slate-900">{{ props.title }}</h2>
          <button type="button" class="icon-btn h-9 w-9" :aria-label="t('pos.closeDialog')" @click="emit('close')">
            <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
          </button>
        </div>
        <div class="min-h-0 overflow-y-auto px-5 pt-3 pb-5">
          <slot />
        </div>
      </div>
    </div>
  </Teleport>
</template>
