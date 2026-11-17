<script setup lang="ts">
// Receive a delivery: scan barcodes (or search by name), adjust quantities
// and costs, then post one stock receipt into the shop.
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import { timeAgo } from '@/dashboard'
import { formatMoney, formatQty, inventoryApi, type Product } from '@/inventory'
import {
  loadDraft,
  newRequestId,
  type Receipt,
  type ReceiveLine,
  receivingApi,
  saveDraft,
} from '@/receiving'
import { session } from '@/session'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

const shops = computed(() => session.context?.shops ?? [])
const shop = ref(shops.value[0]?.name ?? '')
const shopName = computed(() => shops.value.find((s) => s.name === shop.value)?.shop_name ?? '')

const lines = ref<ReceiveLine[]>([])
const reference = ref('')
const scan = ref('')
const scanInput = ref<HTMLInputElement | null>(null)
const searching = ref(false)
const matches = ref<Product[]>([])
const unknown = ref('')
const lastAdded = ref('')
const busy = ref(false)
const message = ref<{ kind: 'ok' | 'error'; text: string } | null>(null)
const receipts = ref<Receipt[]>([])
const currency = ref<string | null>(null)
let requestId = newRequestId()

function restore() {
  const draft = loadDraft(shop.value)
  lines.value = draft.lines
  reference.value = draft.reference
}
watch(shop, () => {
  restore()
  loadReceipts()
})
watch([lines, reference], () => saveDraft(shop.value, { lines: lines.value, reference: reference.value }), { deep: true })

async function loadReceipts() {
  try {
    receipts.value = await receivingApi.receipts(shop.value)
  } catch {
    receipts.value = []
  }
}

function focusScan() {
  nextTick(() => scanInput.value?.focus())
}

function add(product: Product, barcode = '') {
  matches.value = []
  unknown.value = ''
  const existing = lines.value.find((line) => line.item_code === product.item_code)
  if (existing) {
    existing.qty += 1
    lines.value = [existing, ...lines.value.filter((line) => line !== existing)]
  } else {
    lines.value.unshift({
      item_code: product.item_code,
      item_name: product.item_name,
      stock_uom: product.stock_uom,
      barcode: barcode || product.barcodes[0] || '',
      in_stock: product.stock.find((row) => row.shop === shop.value)?.qty ?? 0,
      qty: 1,
      rate: '',
    })
  }
  lastAdded.value = product.item_code
  setTimeout(() => {
    if (lastAdded.value === product.item_code) lastAdded.value = ''
  }, 1500)
  focusScan()
}

// A scanner types the code and presses Enter.
async function onScan() {
  const code = scan.value.trim()
  scan.value = ''
  message.value = null
  if (!code) return
  searching.value = true
  try {
    const results = await inventoryApi.search(code, shop.value, false)
    const exact = results.find((p) => p.item_code === code || p.barcodes.includes(code))
    if (exact) add(exact, exact.barcodes.includes(code) ? code : '')
    else if (results.length) {
      matches.value = results.slice(0, 6)
      unknown.value = ''
    } else {
      matches.value = []
      unknown.value = code
    }
  } catch (err) {
    message.value = { kind: 'error', text: err instanceof ApiError ? err.message : String(err) }
  } finally {
    searching.value = false
  }
}

function createUnknown() {
  router.push({ path: '/products/new', query: { barcode: unknown.value, return: '/receive' } })
}

function step(line: ReceiveLine, delta: number) {
  line.qty = Math.max(1, (Number(line.qty) || 0) + delta)
}
function remove(line: ReceiveLine) {
  lines.value = lines.value.filter((l) => l !== line)
  focusScan()
}

const units = computed(() => lines.value.reduce((sum, line) => sum + (Number(line.qty) || 0), 0))
const value = computed(() =>
  lines.value.reduce((sum, line) => sum + (line.rate === '' ? 0 : Number(line.rate) * (Number(line.qty) || 0)), 0),
)
const allCosted = computed(() => lines.value.every((line) => line.rate !== ''))
const valid = computed(() => lines.value.length > 0 && lines.value.every((line) => Number(line.qty) > 0))

async function submit() {
  if (!valid.value || busy.value) return
  busy.value = true
  message.value = null
  try {
    const receipt = await receivingApi.receive(shop.value, lines.value, reference.value, requestId)
    message.value = {
      kind: 'ok',
      text: t('receive.done', { units: formatQty(receipt.qty, locale.value), shop: receipt.shop_name, name: receipt.name }),
    }
    lines.value = []
    reference.value = ''
    requestId = newRequestId()
    await loadReceipts()
  } catch (err) {
    message.value = { kind: 'error', text: err instanceof ApiError ? err.message : String(err) }
  } finally {
    busy.value = false
    focusScan()
  }
}

onMounted(async () => {
  restore()
  loadReceipts()
  try {
    currency.value = (await inventoryApi.options()).currency
  } catch {
    currency.value = null
  }
  // Back from "create product": add the new product to the delivery.
  const added = route.query.added
  if (typeof added === 'string' && added) {
    try {
      add(await inventoryApi.get(added))
    } catch {
      // the product page already showed any error
    }
    router.replace({ path: '/receive' })
  }
  focusScan()
})

const money = (amount: number) => formatMoney(amount, currency.value, locale.value)
</script>

<template>
  <div class="mx-auto max-w-5xl">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="page-title">{{ t('receive.title') }}</h1>
        <p class="page-subtitle">{{ t('receive.subtitle') }}</p>
        <RouterLink v-if="session.context?.can_buy" to="/delivery-notes/new" class="hint mt-1 inline-block font-medium text-brand-700 hover:underline">
          {{ t('note.fromReceive') }}
        </RouterLink>
      </div>
      <select
        v-if="shops.length > 1"
        v-model="shop"
        class="field w-auto rounded-xl bg-white py-2.5 text-[15px]"
        :aria-label="t('receive.shop')"
      >
        <option v-for="s in shops" :key="s.name" :value="s.name">{{ s.shop_name }}</option>
      </select>
    </div>

    <p v-if="!shop" class="notice-warn mt-6">{{ t('dash.noShop') }}</p>

    <template v-else>
      <p
        v-if="message"
        class="mt-6"
        :class="message.kind === 'ok' ? 'notice-ok' : 'notice-error'"
        role="status"
      >
        {{ message.text }}
      </p>

      <!-- Scan -->
      <section class="card-pad relative mt-6">
        <label class="label" for="receive-scan">{{ t('receive.scanLabel', { shop: shopName }) }}</label>
        <div class="relative">
          <svg viewBox="0 0 24 24" class="pointer-events-none absolute start-4 top-1/2 h-6 w-6 -translate-y-1/2 text-slate-400" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true">
            <path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2M8 8v8M11 8v8M14 8v8M17 8v8" />
          </svg>
          <input
            id="receive-scan"
            ref="scanInput"
            v-model="scan"
            type="search"
            dir="auto"
            autocomplete="off"
            :placeholder="t('receive.scanPlaceholder')"
            class="field py-4 ps-14 text-[19px]"
            :aria-busy="searching"
            @keydown.enter.prevent="onScan"
          />
        </div>

        <!-- Several products match a typed name -->
        <ul v-if="matches.length" class="list mt-3" :aria-label="t('receive.pick')">
          <li v-for="p in matches" :key="p.item_code">
            <button type="button" class="row flex w-full items-center justify-between gap-3 px-4 py-3 text-start" @click="add(p)">
              <span class="min-w-0">
                <span class="block truncate font-medium text-slate-900" dir="auto">{{ p.item_name }}</span>
                <span class="block truncate text-[13px] text-slate-500" dir="ltr">{{ p.item_code }}</span>
              </span>
              <span class="btn-quiet shrink-0 py-1.5 text-[14px]">{{ t('receive.add') }}</span>
            </button>
          </li>
        </ul>

        <!-- Unknown barcode -->
        <div v-if="unknown" class="notice-warn mt-3 flex flex-wrap items-center justify-between gap-3">
          <span>{{ t('receive.unknown', { code: unknown }) }}</span>
          <span class="flex gap-2">
            <button type="button" class="btn-primary py-2" @click="createUnknown">{{ t('receive.create') }}</button>
            <button type="button" class="btn-secondary py-2" @click="unknown = ''; focusScan()">{{ t('receive.dismiss') }}</button>
          </span>
        </div>
      </section>

      <!-- Delivery lines -->
      <section class="card-pad mt-6">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <h2 class="section-title">{{ t('receive.delivery') }}</h2>
          <span class="hint">{{ t('receive.counts', { lines: lines.length, units: formatQty(units, locale) }) }}</span>
        </div>

        <p v-if="!lines.length" class="mt-4 text-[15px] text-slate-500">{{ t('receive.empty') }}</p>
        <template v-else>
        <!-- Wide screens: table -->
        <div class="-mx-2 mt-4 hidden overflow-x-auto sm:block">
          <table class="w-full min-w-[560px] text-[14px]">
            <thead>
              <tr class="text-[12px] text-slate-500">
                <th class="px-2 py-2 text-start font-normal">{{ t('receive.col.product') }}</th>
                <th class="px-2 py-2 text-end font-normal">{{ t('receive.col.inStock') }}</th>
                <th class="px-2 py-2 text-center font-normal">{{ t('receive.col.qty') }}</th>
                <th class="px-2 py-2 text-end font-normal">{{ t('receive.col.cost') }}</th>
                <th class="w-10"><span class="sr-only">{{ t('receive.remove') }}</span></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="line in lines"
                :key="line.item_code"
                class="border-t border-[var(--hairline)] transition-colors duration-700"
                :class="{ 'bg-brand-tint': lastAdded === line.item_code }"
              >
                <td class="px-2 py-3">
                  <span class="block font-medium text-slate-900" dir="auto">{{ line.item_name }}</span>
                  <span class="block text-[12px] text-slate-500" dir="ltr">{{ line.barcode || line.item_code }}</span>
                </td>
                <td class="px-2 py-3 text-end text-slate-600 tabular-nums">
                  {{ formatQty(line.in_stock, locale) }}
                  <span class="block text-[12px] text-green-700 dark:text-green-400">→ {{ formatQty(line.in_stock + (Number(line.qty) || 0), locale) }}</span>
                </td>
                <td class="px-2 py-3">
                  <div class="mx-auto flex w-36 items-center gap-1">
                    <button type="button" class="icon-btn h-9 w-9 bg-slate-100" :aria-label="t('receive.less')" @click="step(line, -1)">−</button>
                    <input
                      v-model.number="line.qty"
                      type="number"
                      min="1"
                      step="any"
                      dir="ltr"
                      class="field w-16 px-2 py-2 text-center tabular-nums"
                      :aria-label="t('receive.qtyFor', { name: line.item_name })"
                    />
                    <button type="button" class="icon-btn h-9 w-9 bg-slate-100" :aria-label="t('receive.more')" @click="step(line, 1)">+</button>
                  </div>
                </td>
                <td class="px-2 py-3 text-end">
                  <input
                    v-model.number="line.rate"
                    type="number"
                    min="0"
                    step="0.01"
                    dir="ltr"
                    :placeholder="t('receive.keepCost')"
                    class="field ms-auto w-28 px-3 py-2 text-end tabular-nums"
                    :aria-label="t('receive.costFor', { name: line.item_name })"
                  />
                </td>
                <td class="px-1 py-3 text-center">
                  <button type="button" class="icon-btn mx-auto hover:text-red-700" :aria-label="t('receive.removeLine', { name: line.item_name })" @click="remove(line)">
                    <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
                      <path d="M6 6l12 12M18 6 6 18" />
                    </svg>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Phones: one card per line -->
        <ul class="mt-4 space-y-3 sm:hidden">
          <li
            v-for="line in lines"
            :key="line.item_code"
            class="rounded-xl bg-slate-50 p-3 transition-colors duration-700"
            :class="{ 'bg-brand-tint': lastAdded === line.item_code }"
          >
            <div class="flex items-start justify-between gap-2">
              <span class="min-w-0">
                <span class="block font-medium text-slate-900" dir="auto">{{ line.item_name }}</span>
                <span class="block text-[12px] text-slate-500" dir="ltr">{{ line.barcode || line.item_code }}</span>
              </span>
              <button type="button" class="icon-btn shrink-0 hover:text-red-700" :aria-label="t('receive.removeLine', { name: line.item_name })" @click="remove(line)">
                <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
                  <path d="M6 6l12 12M18 6 6 18" />
                </svg>
              </button>
            </div>
            <div class="mt-2 flex flex-wrap items-center justify-between gap-3">
              <div class="flex items-center gap-1">
                <button type="button" class="icon-btn h-10 w-10 bg-white" :aria-label="t('receive.less')" @click="step(line, -1)">−</button>
                <input
                  v-model.number="line.qty"
                  type="number"
                  min="1"
                  step="any"
                  dir="ltr"
                  class="field w-16 bg-white px-2 py-2 text-center tabular-nums"
                  :aria-label="t('receive.qtyFor', { name: line.item_name })"
                />
                <button type="button" class="icon-btn h-10 w-10 bg-white" :aria-label="t('receive.more')" @click="step(line, 1)">+</button>
              </div>
              <span class="text-[13px] text-slate-600 tabular-nums">
                {{ t('receive.col.inStock') }}: {{ formatQty(line.in_stock, locale) }}
                <span class="text-green-700 dark:text-green-400">→ {{ formatQty(line.in_stock + (Number(line.qty) || 0), locale) }}</span>
              </span>
            </div>
            <label class="mt-2 flex items-center justify-between gap-3 text-[13px] text-slate-600">
              {{ t('receive.col.cost') }}
              <input
                v-model.number="line.rate"
                type="number"
                min="0"
                step="0.01"
                dir="ltr"
                :placeholder="t('receive.keepCost')"
                class="field w-28 bg-white px-3 py-2 text-end tabular-nums"
              />
            </label>
          </li>
        </ul>
        </template>

        <div v-if="lines.length" class="mt-5 grid gap-4 border-t border-[var(--hairline)] pt-5 sm:grid-cols-[1fr_auto] sm:items-end">
          <div>
            <label class="label" for="receive-ref">{{ t('receive.reference') }}</label>
            <input id="receive-ref" v-model="reference" type="text" dir="auto" maxlength="500" :placeholder="t('receive.referenceHint')" class="field" />
          </div>
          <div class="text-end">
            <div v-if="value" class="mb-2 text-[13px] text-slate-500">
              {{ t('receive.value') }}: <span class="font-semibold text-slate-900 tabular-nums">{{ money(value) }}</span>
              <span v-if="!allCosted">*</span>
            </div>
            <button type="button" class="btn-primary btn-lg" :disabled="!valid || busy" @click="submit">
              {{ busy ? t('receive.saving') : t('receive.submit', { units: formatQty(units, locale) }) }}
            </button>
          </div>
        </div>
        <p v-if="lines.length && !allCosted" class="hint mt-2 text-end">{{ t('receive.costNote') }}</p>
      </section>

      <!-- History -->
      <section class="card-pad mt-6">
        <h2 class="section-title">{{ t('receive.history') }}</h2>
        <p v-if="!receipts.length" class="mt-3 text-[15px] text-slate-500">{{ t('receive.noHistory') }}</p>
        <ul v-else class="mt-3">
          <li v-for="r in receipts" :key="r.name" class="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-[var(--hairline)] py-3 first:border-0">
            <span class="min-w-0 flex-1">
              <span class="block font-medium text-slate-900" dir="ltr">{{ r.name }}</span>
              <span class="block truncate text-[13px] text-slate-500">
                <bdi>{{ r.shop_name }}</bdi> · <bdi>{{ r.by }}</bdi><template v-if="r.reference"> · <bdi>{{ r.reference }}</bdi></template>
              </span>
            </span>
            <span class="text-[14px] text-slate-700 tabular-nums">{{ t('receive.counts', { lines: r.lines, units: formatQty(r.qty, locale) }) }}</span>
            <span v-if="r.value" class="text-[14px] font-medium text-slate-900 tabular-nums">{{ money(r.value) }}</span>
            <span class="w-28 text-end text-[13px] text-slate-500">{{ timeAgo(r.posted, locale) }}</span>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>
