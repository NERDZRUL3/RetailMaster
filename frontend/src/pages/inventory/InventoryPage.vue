<script setup lang="ts">
// Inventory: stock on hand and its value, every stock movement, transfers
// between shops and stock counts.
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import ProductPicker from '@/components/ProductPicker.vue'
import { formatMoney, formatQty, type Product } from '@/inventory'
import { newRequestId } from '@/receiving'
import { session } from '@/session'
import { type Count, type Movement, type QtyLine, stockApi, type StockList, type Transfer } from '@/stock'

type Tab = 'stock' | 'movements' | 'transfer' | 'count'
const TABS: Tab[] = ['stock', 'movements', 'transfer', 'count']

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

const shops = computed(() => session.context?.shops ?? [])
const canChange = computed(() => !!session.context?.can_receive)
const tabs = computed(() => TABS.filter((tab) => canChange.value || tab === 'stock' || tab === 'movements'))
const tab = ref<Tab>(TABS.includes(route.query.tab as Tab) ? (route.query.tab as Tab) : 'stock')
watch(tab, (value) => router.replace({ query: { ...route.query, tab: value } }))

const error = ref('')
const fail = (err: unknown) => (error.value = err instanceof ApiError ? err.message : String(err))
const currency = ref<string | null>(null)
const money = (value: number) => formatMoney(value, currency.value, locale.value)
const qty = (value: number) => formatQty(value, locale.value)
const signed = (value: number) => (value > 0 ? `+${qty(value)}` : qty(value))
const when = (iso: string) => new Date(iso).toLocaleString(locale.value, { dateStyle: 'short', timeStyle: 'short' })

// ---- Stock on hand ------------------------------------------------------
type Only = 'all' | 'in' | 'low' | 'out'
const ONLY: Only[] = ['all', 'in', 'low', 'out']
const stockShop = ref('')
const stockQuery = ref('')
const stockOnly = ref<Only>('all')
const stock = ref<StockList | null>(null)
const stockLoading = ref(false)
let stockTimer: ReturnType<typeof setTimeout> | undefined
async function loadStock() {
  stockLoading.value = true
  error.value = ''
  try {
    stock.value = await stockApi.stock(stockShop.value, stockQuery.value.trim(), stockOnly.value)
    currency.value = stock.value.currency
  } catch (err) {
    fail(err)
  } finally {
    stockLoading.value = false
  }
}
watch([stockShop, stockOnly], loadStock)
watch(stockQuery, () => {
  clearTimeout(stockTimer)
  stockTimer = setTimeout(loadStock, 250)
})

// ---- Movements ----------------------------------------------------------
const KINDS = ['sale', 'return', 'receipt', 'purchase', 'transfer', 'count']
const KIND_CLASS: Record<string, string> = {
  sale: 'badge-neutral',
  return: 'badge-warn',
  receipt: 'badge-ok',
  purchase: 'badge-ok',
  transfer: 'badge-brand',
  count: 'badge-warn',
  other: 'badge-neutral',
}
const moveShop = ref('')
const moveKind = ref('')
const moveItem = ref(typeof route.query.item === 'string' ? route.query.item : '')
const moves = ref<Movement[]>([])
const moreMoves = ref(false)
const movesLoading = ref(false)
async function loadMoves(append = false) {
  movesLoading.value = true
  error.value = ''
  try {
    const page = await stockApi.movements(moveShop.value, moveKind.value, append ? moves.value.length : 0, moveItem.value)
    moves.value = append ? [...moves.value, ...page.rows] : page.rows
    moreMoves.value = page.more
  } catch (err) {
    fail(err)
  } finally {
    movesLoading.value = false
  }
}
watch([moveShop, moveKind, moveItem], () => loadMoves())
function showMovesOf(itemCode: string) {
  moveItem.value = itemCode
  tab.value = 'movements'
}

// ---- Lines shared by transfers and counts ---------------------------------
function addLine(lines: QtyLine[], product: Product, barcode: string, shop: string, startQty: number | ''): QtyLine[] {
  const existing = lines.find((l) => l.item_code === product.item_code)
  if (existing) {
    if (startQty !== '') existing.qty = (Number(existing.qty) || 0) + 1
    return [existing, ...lines.filter((l) => l !== existing)]
  }
  const line: QtyLine = {
    item_code: product.item_code,
    item_name: product.item_name,
    barcode: barcode || product.barcodes[0] || '',
    in_stock: product.stock.find((s) => s.shop === shop)?.qty ?? 0,
    qty: startQty,
  }
  return [line, ...lines]
}
const busy = ref(false)

// ---- Transfer -----------------------------------------------------------
const fromShop = ref(shops.value[0]?.name ?? '')
const toShop = ref(shops.value[1]?.name ?? '')
const targets = computed(() => shops.value.filter((s) => s.name !== fromShop.value))
const transferLines = ref<QtyLine[]>([])
const transferRef = ref('')
const transfers = ref<Transfer[]>([])
const done = ref('')
let transferRequest = newRequestId()
const transferValid = computed(
  () =>
    !!fromShop.value &&
    !!toShop.value &&
    fromShop.value !== toShop.value &&
    transferLines.value.length > 0 &&
    transferLines.value.every((l) => Number(l.qty) > 0),
)
watch(fromShop, () => {
  transferLines.value = []
  if (toShop.value === fromShop.value) toShop.value = targets.value[0]?.name ?? ''
})
async function loadTransfers() {
  try {
    transfers.value = await stockApi.transfers('')
  } catch {
    transfers.value = []
  }
}
function pickForTransfer(product: Product, barcode: string) {
  done.value = ''
  transferLines.value = addLine(transferLines.value, product, barcode, fromShop.value, 1)
}
async function submitTransfer() {
  if (!transferValid.value || busy.value) return
  busy.value = true
  error.value = ''
  done.value = ''
  try {
    const result = await stockApi.transfer(fromShop.value, toShop.value, transferLines.value, transferRef.value, transferRequest)
    done.value = t('stock.transferDone', { qty: qty(result.qty), from: result.from_shop, to: result.to_shop, name: result.name })
    transferLines.value = []
    transferRef.value = ''
    transferRequest = newRequestId()
    loadTransfers()
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

// ---- Count --------------------------------------------------------------
const countShop = ref(shops.value[0]?.name ?? '')
const countLines = ref<QtyLine[]>([])
const countRef = ref('')
const counts = ref<Count[]>([])
const countResult = ref<Count | null>(null)
let countRequest = newRequestId()
const countValid = computed(
  () => countLines.value.length > 0 && countLines.value.every((l) => l.qty !== '' && Number(l.qty) >= 0),
)
watch(countShop, () => {
  countLines.value = []
  countResult.value = null
})
async function loadCounts() {
  try {
    counts.value = await stockApi.counts('')
  } catch {
    counts.value = []
  }
}
function pickForCount(product: Product, barcode: string) {
  countResult.value = null
  countLines.value = addLine(countLines.value, product, barcode, countShop.value, '')
}
const countDiff = (line: QtyLine) => (line.qty === '' ? null : Number(line.qty) - line.in_stock)
async function submitCount() {
  if (!countValid.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    countResult.value = await stockApi.count(countShop.value, countLines.value, countRef.value, countRequest)
    countLines.value = []
    countRef.value = ''
    countRequest = newRequestId()
    loadCounts()
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

watch(
  tab,
  (value) => {
    error.value = ''
    done.value = ''
    if (value === 'movements' && !moves.value.length) loadMoves()
    if (value === 'transfer') loadTransfers()
    if (value === 'count') loadCounts()
  },
  { immediate: true },
)
onMounted(loadStock) // stock tab, and the currency for every tab
</script>

<template>
  <div class="mx-auto max-w-6xl">
    <h1 class="page-title">{{ t('stock.title') }}</h1>
    <p class="page-subtitle">{{ t('stock.subtitle') }}</p>

    <div class="mt-6 max-w-full overflow-x-auto">
      <div class="segmented" role="tablist" :aria-label="t('stock.title')">
        <button
          v-for="item in tabs"
          :key="item"
          type="button"
          role="tab"
          class="segment h-9 px-4 text-[14px] whitespace-nowrap"
          :aria-selected="tab === item"
          :aria-pressed="tab === item"
          @click="tab = item"
        >
          {{ t(`stock.tabs.${item}`) }}
        </button>
      </div>
    </div>

    <p v-if="error" class="notice-error mt-6" role="alert">{{ error }}</p>

    <!-- Stock on hand -->
    <section v-if="tab === 'stock'" class="mt-6">
      <div v-if="stock" class="stagger grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div class="card p-4">
          <div class="text-[13px] text-slate-500">{{ t('stock.value') }}</div>
          <div class="mt-1 text-[22px] font-semibold text-slate-900 tabular-nums">{{ money(stock.totals.value) }}</div>
        </div>
        <div class="card p-4">
          <div class="text-[13px] text-slate-500">{{ t('stock.units') }}</div>
          <div class="mt-1 text-[22px] font-semibold text-slate-900 tabular-nums">{{ qty(stock.totals.units) }}</div>
        </div>
        <button type="button" class="card lift p-4 text-start" @click="stockOnly = 'low'">
          <div class="text-[13px] text-slate-500">{{ t('stock.low') }}</div>
          <div class="mt-1 text-[22px] font-semibold text-amber-600 tabular-nums">{{ stock.totals.low }}</div>
        </button>
        <button type="button" class="card lift p-4 text-start" @click="stockOnly = 'out'">
          <div class="text-[13px] text-slate-500">{{ t('stock.out') }}</div>
          <div class="mt-1 text-[22px] font-semibold text-red-600 tabular-nums">{{ stock.totals.out }}</div>
        </button>
      </div>

      <div class="card mt-4 p-3">
        <div class="flex flex-wrap items-center gap-2">
          <input
            v-model="stockQuery"
            type="search"
            dir="auto"
            class="field min-w-0 flex-1 py-2.5 text-[15px]"
            :placeholder="t('stock.search')"
            :aria-label="t('stock.search')"
          />
          <select v-if="shops.length > 1" v-model="stockShop" class="field w-auto py-2.5 text-[15px]" :aria-label="t('stock.shop')">
            <option value="">{{ t('stock.allShops') }}</option>
            <option v-for="s in shops" :key="s.name" :value="s.name">{{ s.shop_name }}</option>
          </select>
          <div class="segmented" role="group" :aria-label="t('stock.show')">
            <button v-for="f in ONLY" :key="f" type="button" class="segment" :aria-pressed="stockOnly === f" @click="stockOnly = f">
              {{ t(`stock.only.${f}`) }}
            </button>
          </div>
        </div>
      </div>

      <div class="card mt-4 overflow-x-auto" :aria-busy="stockLoading">
        <table class="w-full min-w-[640px] text-[14px]">
          <thead>
            <tr class="text-[12px] text-slate-500">
              <th class="px-4 py-3 text-start font-medium">{{ t('stock.col.product') }}</th>
              <th v-if="shops.length > 1" class="px-4 py-3 text-start font-medium">{{ t('stock.col.shop') }}</th>
              <th class="px-4 py-3 text-end font-medium">{{ t('stock.col.qty') }}</th>
              <th class="px-4 py-3 text-end font-medium">{{ t('stock.col.cost') }}</th>
              <th class="px-4 py-3 text-end font-medium">{{ t('stock.col.value') }}</th>
              <th class="px-4 py-3"><span class="sr-only">{{ t('stock.col.history') }}</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in stock?.rows ?? []" :key="row.item_code + row.shop" class="border-t border-[var(--hairline)]">
              <td class="px-4 py-3">
                <RouterLink :to="`/products/${encodeURIComponent(row.item_code)}`" class="font-medium text-slate-900 hover:underline" dir="auto">{{ row.item_name }}</RouterLink>
                <span class="block text-[12px] text-slate-500">{{ row.item_group }}</span>
              </td>
              <td v-if="shops.length > 1" class="px-4 py-3 text-slate-600">{{ row.shop_name }}</td>
              <td class="px-4 py-3 text-end tabular-nums">
                <span class="font-semibold" :class="row.out ? 'text-red-600' : row.low ? 'text-amber-600' : 'text-slate-900'">{{ qty(row.qty) }}</span>
                <span v-if="row.reorder_level" class="block text-[12px] text-slate-500">{{ t('stock.reorderAt', { qty: qty(row.reorder_level) }) }}</span>
              </td>
              <td class="px-4 py-3 text-end text-slate-600 tabular-nums">{{ money(row.rate) }}</td>
              <td class="px-4 py-3 text-end font-medium text-slate-900 tabular-nums">{{ money(row.value) }}</td>
              <td class="px-4 py-3 text-end">
                <button type="button" class="btn-quiet px-2.5 py-1 text-[13px]" @click="showMovesOf(row.item_code)">{{ t('stock.history') }}</button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!stockLoading && !stock?.rows.length" class="hint p-6 text-center">{{ t('stock.empty') }}</p>
      </div>
    </section>

    <!-- Movements -->
    <section v-else-if="tab === 'movements'" class="mt-6">
      <div class="card p-3">
        <div class="flex flex-wrap items-center gap-2">
          <select v-if="shops.length > 1" v-model="moveShop" class="field w-auto py-2.5 text-[15px]" :aria-label="t('stock.shop')">
            <option value="">{{ t('stock.allShops') }}</option>
            <option v-for="s in shops" :key="s.name" :value="s.name">{{ s.shop_name }}</option>
          </select>
          <select v-model="moveKind" class="field w-auto py-2.5 text-[15px]" :aria-label="t('stock.kindFilter')">
            <option value="">{{ t('stock.allKinds') }}</option>
            <option v-for="k in KINDS" :key="k" :value="k">{{ t(`stock.kind.${k}`) }}</option>
          </select>
          <span v-if="moveItem" class="badge-brand gap-2 py-1.5 text-[13px]">
            <span dir="auto">{{ moves[0]?.item_name ?? moveItem }}</span>
            <button type="button" :aria-label="t('stock.clearProduct')" @click="moveItem = ''">✕</button>
          </span>
        </div>
      </div>
      <div class="card mt-4 overflow-x-auto" :aria-busy="movesLoading">
        <table class="w-full min-w-[680px] text-[14px]">
          <thead>
            <tr class="text-[12px] text-slate-500">
              <th class="px-4 py-3 text-start font-medium">{{ t('stock.col.when') }}</th>
              <th class="px-4 py-3 text-start font-medium">{{ t('stock.col.product') }}</th>
              <th class="px-4 py-3 text-start font-medium">{{ t('stock.col.what') }}</th>
              <th class="px-4 py-3 text-end font-medium">{{ t('stock.col.change') }}</th>
              <th class="px-4 py-3 text-end font-medium">{{ t('stock.col.after') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(m, i) in moves" :key="i" class="border-t border-[var(--hairline)]">
              <td class="px-4 py-3 whitespace-nowrap text-slate-600 tabular-nums">{{ when(m.posted) }}</td>
              <td class="px-4 py-3">
                <button type="button" class="text-start font-medium text-slate-900 hover:underline" dir="auto" @click="moveItem = m.item_code">{{ m.item_name }}</button>
                <span class="block text-[12px] text-slate-500">{{ m.shop_name }} · {{ m.by }}</span>
              </td>
              <td class="px-4 py-3">
                <span :class="KIND_CLASS[m.kind]">{{ t(`stock.kind.${m.kind}`) }}</span>
                <span class="block text-[12px] text-slate-500">{{ m.voucher_no }}</span>
              </td>
              <td class="px-4 py-3 text-end font-semibold tabular-nums" :class="m.qty < 0 ? 'text-red-600' : 'text-green-700'">{{ signed(m.qty) }}</td>
              <td class="px-4 py-3 text-end text-slate-600 tabular-nums">{{ qty(m.balance) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!movesLoading && !moves.length" class="hint p-6 text-center">{{ t('stock.noMoves') }}</p>
      </div>
      <div v-if="moreMoves" class="mt-4 text-center">
        <button type="button" class="btn-secondary" :disabled="movesLoading" @click="loadMoves(true)">{{ t('stock.more') }}</button>
      </div>
    </section>

    <!-- Transfer -->
    <section v-else-if="tab === 'transfer'" class="mt-6 space-y-5">
      <p v-if="shops.length < 2" class="notice-warn">{{ t('stock.needTwoShops') }}</p>
      <template v-else>
        <p v-if="done" class="notice-ok" role="status">{{ done }}</p>
        <div class="card-pad grid gap-4 sm:grid-cols-2">
          <div>
            <label class="label" for="from-shop">{{ t('stock.from') }}</label>
            <select id="from-shop" v-model="fromShop" class="field text-[15px]">
              <option v-for="s in shops" :key="s.name" :value="s.name">{{ s.shop_name }}</option>
            </select>
          </div>
          <div>
            <label class="label" for="to-shop">{{ t('stock.to') }}</label>
            <select id="to-shop" v-model="toShop" class="field text-[15px]">
              <option v-for="s in targets" :key="s.name" :value="s.name">{{ s.shop_name }}</option>
            </select>
          </div>
          <div class="sm:col-span-2">
            <ProductPicker :shop="fromShop" input-id="transfer-scan" :label="t('stock.scanTransfer')" @pick="pickForTransfer" />
          </div>
        </div>

        <div class="card-pad">
          <p v-if="!transferLines.length" class="hint">{{ t('stock.noLines') }}</p>
          <ul v-else class="space-y-2">
            <li v-for="line in transferLines" :key="line.item_code" class="flex flex-wrap items-center gap-3 border-b border-[var(--hairline)] pb-2">
              <span class="min-w-0 flex-1">
                <span class="block font-medium text-slate-900" dir="auto">{{ line.item_name }}</span>
                <span class="block text-[12px]" :class="Number(line.qty) > line.in_stock ? 'text-red-600' : 'text-slate-500'">
                  {{ t('stock.available', { qty: qty(line.in_stock) }) }}
                </span>
              </span>
              <input v-model.number="line.qty" type="number" min="1" step="any" class="field w-24 py-2 text-center tabular-nums" :aria-label="t('stock.qtyFor', { name: line.item_name })" />
              <button type="button" class="icon-btn" :aria-label="t('stock.removeLine', { name: line.item_name })" @click="transferLines = transferLines.filter((l) => l !== line)">✕</button>
            </li>
          </ul>
          <label class="label mt-4" for="transfer-ref">{{ t('stock.reference') }}</label>
          <input id="transfer-ref" v-model="transferRef" maxlength="140" class="field text-[15px]" :placeholder="t('stock.referencePlaceholder')" />
          <button type="button" class="btn-primary btn-lg mt-5 w-full sm:w-auto" :disabled="!transferValid || busy" @click="submitTransfer">
            {{ busy ? t('pos.saving') : t('stock.transferSubmit') }}
          </button>
        </div>

        <div v-if="transfers.length">
          <h2 class="label">{{ t('stock.recentTransfers') }}</h2>
          <ul class="list">
            <li v-for="tr in transfers" :key="tr.name" class="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-[14px]">
              <span class="whitespace-nowrap text-slate-500 tabular-nums">{{ when(tr.posted) }}</span>
              <span class="min-w-0 flex-1 text-slate-900">{{ tr.from_shop }} → {{ tr.to_shop }}</span>
              <span class="text-slate-600">{{ t('stock.unitsN', { n: qty(tr.qty) }, tr.qty) }}</span>
              <span class="text-[12px] text-slate-500">{{ tr.name }} · {{ tr.by }}</span>
            </li>
          </ul>
        </div>
      </template>
    </section>

    <!-- Stock count -->
    <section v-else-if="tab === 'count'" class="mt-6 space-y-5">
      <div v-if="countResult" class="card-pad" role="status">
        <p v-if="!countResult.name" class="notice-ok">{{ t('stock.countNoChange', { n: countResult.unchanged ?? 0 }, countResult.unchanged ?? 0) }}</p>
        <template v-else>
          <p class="notice-ok">{{ t('stock.countDone', { n: countResult.lines.length, name: countResult.name }, countResult.lines.length) }}</p>
          <ul class="mt-3 space-y-1 text-[14px]">
            <li v-for="l in countResult.lines" :key="l.item_code" class="flex gap-3">
              <span class="min-w-0 flex-1 truncate" dir="auto">{{ l.item_name }}</span>
              <span class="text-slate-500 tabular-nums">{{ qty(l.before) }} → {{ qty(l.counted) }}</span>
              <span class="w-16 text-end font-semibold tabular-nums" :class="l.difference < 0 ? 'text-red-600' : 'text-green-700'">{{ signed(l.difference) }}</span>
            </li>
          </ul>
          <p class="mt-3 text-[14px] text-slate-600">{{ t('stock.valueDiff', { value: money(countResult.value_difference) }) }}</p>
        </template>
      </div>

      <div class="card-pad grid gap-4">
        <p class="hint">{{ t('stock.countHint') }}</p>
        <div v-if="shops.length > 1">
          <label class="label" for="count-shop">{{ t('stock.shop') }}</label>
          <select id="count-shop" v-model="countShop" class="field text-[15px]">
            <option v-for="s in shops" :key="s.name" :value="s.name">{{ s.shop_name }}</option>
          </select>
        </div>
        <ProductPicker :shop="countShop" input-id="count-scan" :label="t('stock.scanCount')" @pick="pickForCount" />
      </div>

      <div class="card-pad">
        <p v-if="!countLines.length" class="hint">{{ t('stock.noLines') }}</p>
        <ul v-else class="space-y-2">
          <li v-for="line in countLines" :key="line.item_code" class="flex flex-wrap items-center gap-3 border-b border-[var(--hairline)] pb-2">
            <span class="min-w-0 flex-1">
              <span class="block font-medium text-slate-900" dir="auto">{{ line.item_name }}</span>
              <span class="block text-[12px] text-slate-500">
                {{ t('stock.onRecord', { qty: qty(line.in_stock) }) }}
                <template v-if="countDiff(line) !== null">
                  ·
                  <span :class="(countDiff(line) ?? 0) < 0 ? 'text-red-600' : (countDiff(line) ?? 0) > 0 ? 'text-green-700' : ''">{{ signed(countDiff(line) ?? 0) }}</span>
                </template>
              </span>
            </span>
            <input v-model.number="line.qty" type="number" min="0" step="any" class="field w-24 py-2 text-center tabular-nums" :placeholder="t('stock.counted')" :aria-label="t('stock.countFor', { name: line.item_name })" />
            <button type="button" class="icon-btn" :aria-label="t('stock.removeLine', { name: line.item_name })" @click="countLines = countLines.filter((l) => l !== line)">✕</button>
          </li>
        </ul>
        <label class="label mt-4" for="count-ref">{{ t('stock.reference') }}</label>
        <input id="count-ref" v-model="countRef" maxlength="140" class="field text-[15px]" :placeholder="t('stock.countReferencePlaceholder')" />
        <button type="button" class="btn-primary btn-lg mt-5 w-full sm:w-auto" :disabled="!countValid || busy" @click="submitCount">
          {{ busy ? t('pos.saving') : t('stock.countSubmit') }}
        </button>
      </div>

      <div v-if="counts.length">
        <h2 class="label">{{ t('stock.recentCounts') }}</h2>
        <ul class="list">
          <li v-for="c in counts" :key="c.name ?? ''" class="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-[14px]">
            <span class="whitespace-nowrap text-slate-500 tabular-nums">{{ c.posted ? when(c.posted) : '' }}</span>
            <span class="min-w-0 flex-1 text-slate-900">{{ c.shop_name }} · {{ t('stock.adjusted', { n: c.lines.length }, c.lines.length) }}</span>
            <span class="font-medium tabular-nums" :class="c.value_difference < 0 ? 'text-red-600' : 'text-slate-900'">{{ money(c.value_difference) }}</span>
            <span class="text-[12px] text-slate-500">{{ c.name }} · {{ c.by }}</span>
          </li>
        </ul>
      </div>
    </section>
  </div>
</template>
