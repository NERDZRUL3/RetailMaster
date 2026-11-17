<script setup lang="ts">
// Scan a barcode or type a name; an exact barcode/code match is picked at
// once, several matches are listed to choose from.
import { nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import { inventoryApi, type Product } from '@/inventory'

const props = defineProps<{ shop: string; label: string; inputId: string }>()
const emit = defineEmits<{ pick: [product: Product, barcode: string] }>()
const { t } = useI18n()

const scan = ref('')
const input = ref<HTMLInputElement | null>(null)
const busy = ref(false)
const matches = ref<Product[]>([])
const message = ref('')

function focus() {
  nextTick(() => input.value?.focus())
}
defineExpose({ focus })

function pick(product: Product, barcode = '') {
  matches.value = []
  message.value = ''
  emit('pick', product, barcode)
  focus()
}

async function onEnter() {
  const code = scan.value.trim()
  scan.value = ''
  message.value = ''
  if (!code) return
  busy.value = true
  try {
    const results = await inventoryApi.search(code, props.shop, false)
    const exact = results.find((p) => p.item_code === code || p.barcodes.includes(code))
    if (exact) pick(exact, exact.barcodes.includes(code) ? code : '')
    else if (results.length === 1) pick(results[0])
    else if (results.length) matches.value = results.slice(0, 8)
    else message.value = t('picker.notFound', { code })
  } catch (err) {
    message.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div>
    <label class="label" :for="inputId">{{ label }}</label>
    <div class="relative">
      <svg viewBox="0 0 24 24" class="pointer-events-none absolute start-4 top-1/2 h-6 w-6 -translate-y-1/2 text-slate-400" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true">
        <path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2M8 8v8M11 8v8M14 8v8M17 8v8" />
      </svg>
      <input
        :id="inputId"
        ref="input"
        v-model="scan"
        type="search"
        dir="auto"
        autocomplete="off"
        :placeholder="t('picker.placeholder')"
        class="field py-3.5 ps-14 text-[17px]"
        :aria-busy="busy"
        @keydown.enter.prevent="onEnter"
      />
    </div>
    <ul v-if="matches.length" class="list mt-3" :aria-label="t('picker.choose')">
      <li v-for="p in matches" :key="p.item_code">
        <button type="button" class="flex w-full items-center justify-between gap-3 px-4 py-3 text-start hover:bg-[var(--row-hover)]" @click="pick(p)">
          <span class="min-w-0">
            <span class="block truncate font-medium text-slate-900" dir="auto">{{ p.item_name }}</span>
            <span class="block truncate text-[13px] text-slate-500" dir="ltr">{{ p.barcodes[0] || p.item_code }}</span>
          </span>
          <span class="btn-quiet shrink-0 py-1.5 text-[14px]">{{ t('picker.add') }}</span>
        </button>
      </li>
    </ul>
    <p v-if="message" class="notice-warn mt-3" role="status">{{ message }}</p>
  </div>
</template>
