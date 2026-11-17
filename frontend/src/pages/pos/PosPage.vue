<script setup lang="ts">
// The till: scan or tap products into the cart, take payment, print the receipt.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import PosReceipt from '@/components/PosReceipt.vue'
import { formatMoney, formatQty } from '@/inventory'
import {
  type CartLine,
  loadCart,
  methodLabel,
  posApi,
  type PosProduct,
  quickCash,
  type Sale,
  type SaleRow,
  saveCart,
  type Till,
} from '@/pos'
import AppDialog from '@/components/AppDialog.vue'
import TillReport from '@/components/TillReport.vue'
import { newRequestId } from '@/receiving'
import { session } from '@/session'
import { formatWhen, type SessionReport, tillApi } from '@/till'

const { t, locale } = useI18n()

const shops = computed(() => session.context?.shops ?? [])
const shop = ref(shops.value[0]?.name ?? '')

const till = ref<Till | null>(null)
const products = ref<PosProduct[]>([])
const cart = ref<CartLine[]>([])
const query = ref('')
const scanInput = ref<HTMLInputElement | null>(null)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const lastAdded = ref('')

type Step = 'cart' | 'pay' | 'done'
const stepName = ref<Step>('cart')
const mode = ref('')
const tendered = ref<number | ''>('')
const busy = ref(false)
const sale = ref<Sale | null>(null)
const printSale = ref<Sale | null>(null)
const recent = ref<SaleRow[]>([])
let requestId = newRequestId()

const money = (value: number) => formatMoney(value, till.value?.currency ?? null, locale.value)
const total = computed(() => Math.round(cart.value.reduce((sum, line) => sum + line.price * line.qty, 0) * 100) / 100)
const units = computed(() => cart.value.reduce((sum, line) => sum + line.qty, 0))
const method = computed(() => till.value?.payments.find((p) => p.mode === mode.value))
const paid = computed(() => (method.value?.cash ? Number(tendered.value) || 0 : total.value))
const change = computed(() => Math.max(0, Math.round((paid.value - total.value) * 100) / 100))
const canPay = computed(() => cart.value.length > 0 && paid.value + 0.005 >= total.value && !busy.value)

function focusScan() {
  nextTick(() => scanInput.value?.focus())
}

// ---- Till session -------------------------------------------------------
const tillSession = computed(() => till.value?.session ?? null)
/** Selling is possible: the user's own session, opened today. */
const selling = computed(() => !!tillSession.value?.mine && !tillSession.value.outdated)
const openingCash = ref<number | ''>('')

async function openSession() {
  if (!till.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    till.value.session = await tillApi.open(shop.value, Number(openingCash.value) || 0)
    await Promise.all([search(), loadRecent()])
    focusScan()
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

// Short confirmation messages
const info = ref('')
let infoTimer: ReturnType<typeof setTimeout> | undefined
function showInfo(text: string) {
  info.value = text
  clearTimeout(infoTimer)
  infoTimer = setTimeout(() => (info.value = ''), 4000)
}

// Cash in / cash out
const moveOpen = ref(false)
const moveType = ref<'In' | 'Out'>('Out')
const moveAmount = ref<number | ''>('')
const moveReason = ref('')
function startMove(type: 'In' | 'Out') {
  moveType.value = type
  moveAmount.value = ''
  moveReason.value = ''
  error.value = ''
  moveOpen.value = true
}
const moveValid = computed(() => Number(moveAmount.value) > 0 && moveReason.value.trim().length > 0)
async function saveMove() {
  if (!moveValid.value || busy.value) return
  busy.value = true
  try {
    await tillApi.move(shop.value, moveType.value, Number(moveAmount.value), moveReason.value.trim())
    moveOpen.value = false
    showInfo(t(moveType.value === 'In' ? 'till.movedIn' : 'till.movedOut', { amount: money(Number(moveAmount.value)) }))
  } catch (err) {
    fail(err)
    moveOpen.value = false
  } finally {
    busy.value = false
  }
}

// X report
const xReport = ref<SessionReport | null>(null)
async function showX() {
  try {
    xReport.value = await tillApi.current(shop.value)
  } catch (err) {
    fail(err)
  }
}

// Closing: count (blind), review the differences, close, Z report
const view = ref<'sell' | 'close'>('sell')
const closeStep = ref<'count' | 'review' | 'done'>('count')
const counts = ref<Record<string, number | ''>>({})
const closeNote = ref('')
const closeReport = ref<SessionReport | null>(null)
function startClose() {
  if (!till.value) return
  counts.value = Object.fromEntries(till.value.payments.map((p) => [p.mode, '']))
  closeNote.value = ''
  closeReport.value = null
  closeStep.value = 'count'
  error.value = ''
  view.value = 'close'
}
const countsValid = computed(() => Object.values(counts.value).every((v) => v !== '' && Number(v) >= 0))
const cleanCounts = () => Object.fromEntries(Object.entries(counts.value).map(([mode, v]) => [mode, Number(v) || 0]))
async function reviewClose() {
  if (!countsValid.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    closeReport.value = await tillApi.preview(shop.value, cleanCounts())
    closeStep.value = 'review'
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}
async function confirmClose() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    closeReport.value = await tillApi.close(shop.value, cleanCounts(), closeNote.value)
    closeStep.value = 'done'
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}
function finishClose() {
  view.value = 'sell'
  openTill()
}
const hasDifference = computed(() => closeReport.value?.rows.some((r) => Math.abs(r.difference ?? 0) >= 0.005) ?? false)

// Printing: one printout at a time (a receipt or a session report)
const printReport = ref<SessionReport | null>(null)
async function printTillReport(report: SessionReport) {
  printSale.value = null
  printReport.value = report
  await nextTick()
  window.print()
}

function fail(err: unknown) {
  error.value = err instanceof ApiError ? err.message : String(err)
}

async function openTill() {
  if (!shop.value) return
  error.value = ''
  notice.value = ''
  till.value = null
  cart.value = loadCart(shop.value)
  stepName.value = 'cart'
  try {
    till.value = await posApi.till(shop.value)
    mode.value = (till.value.payments.find((p) => p.default) ?? till.value.payments[0])?.mode ?? ''
    openingCash.value = till.value.last_cash ?? ''
    await Promise.all([search(), loadRecent()])
  } catch (err) {
    fail(err)
  }
  focusScan()
}
watch(shop, openTill)
watch(cart, () => saveCart(shop.value, cart.value), { deep: true })

async function loadRecent() {
  try {
    recent.value = await posApi.sales(shop.value)
  } catch {
    recent.value = []
  }
}

let searchTimer: ReturnType<typeof setTimeout> | undefined
async function search() {
  loading.value = true
  try {
    products.value = await posApi.find(shop.value, query.value.trim())
  } catch (err) {
    fail(err)
  } finally {
    loading.value = false
  }
}
function onType() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(search, 250)
}

function add(product: PosProduct) {
  notice.value = ''
  if (!product.price) {
    notice.value = t('pos.noPrice', { name: product.item_name })
    return
  }
  const line = cart.value.find((l) => l.item_code === product.item_code)
  if (line) {
    line.qty += 1
    cart.value = [line, ...cart.value.filter((l) => l !== line)]
  } else {
    cart.value.unshift({
      item_code: product.item_code,
      item_name: product.item_name,
      price: product.price,
      stock: product.stock,
      qty: 1,
    })
  }
  if (stepName.value === 'done') startNew(false)
  lastAdded.value = product.item_code
  setTimeout(() => {
    if (lastAdded.value === product.item_code) lastAdded.value = ''
  }, 1200)
}

// A scanner types the barcode and presses Enter.
async function onEnter() {
  clearTimeout(searchTimer)
  const code = query.value.trim()
  if (!code) return
  error.value = ''
  loading.value = true
  try {
    const found = await posApi.find(shop.value, code)
    const exact = found.find((p) => p.barcode === code || p.item_code === code) ?? (found.length === 1 ? found[0] : null)
    if (exact) {
      add(exact)
      query.value = ''
      await search()
    } else {
      products.value = found
      if (!found.length) notice.value = t('pos.notFound', { code })
    }
  } catch (err) {
    fail(err)
  } finally {
    loading.value = false
    focusScan()
  }
}

function setQty(line: CartLine, qty: number) {
  if (qty <= 0) cart.value = cart.value.filter((l) => l !== line)
  else line.qty = qty
}

function clearCart() {
  if (cart.value.length && !window.confirm(t('pos.confirmClear'))) return
  cart.value = []
  stepName.value = 'cart'
  focusScan()
}

function goPay() {
  if (!cart.value.length) return
  error.value = ''
  tendered.value = ''
  stepName.value = 'pay'
}

const cartBox = ref<HTMLElement | null>(null)
function payFromBar() {
  goPay()
  nextTick(() => cartBox.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
}

async function pay() {
  if (!canPay.value || !till.value) return
  busy.value = true
  error.value = ''
  try {
    const amount = method.value?.cash ? paid.value : total.value
    sale.value = await posApi.sell(shop.value, cart.value, [{ mode: mode.value, amount }], requestId)
    cart.value = []
    stepName.value = 'done'
    requestId = newRequestId()
    loadRecent()
    search()
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

function startNew(focus = true) {
  sale.value = null
  stepName.value = 'cart'
  tendered.value = ''
  if (focus) focusScan()
}

async function print(target: Sale | string) {
  try {
    printReport.value = null
    printSale.value = typeof target === 'string' ? await posApi.sale(target) : target
    await nextTick()
    window.print()
  } catch (err) {
    fail(err)
  }
}

function onKey(event: KeyboardEvent) {
  if (!selling.value || view.value !== 'sell' || moveOpen.value || xReport.value) return
  if (event.key === 'F2') {
    event.preventDefault()
    focusScan()
  } else if (event.key === 'F9' && stepName.value === 'cart') {
    event.preventDefault()
    goPay()
  } else if (event.key === 'Escape' && stepName.value === 'pay') {
    stepName.value = 'cart'
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKey)
  openTill()
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="solid-surfaces mx-auto max-w-7xl pb-20 lg:pb-0">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="page-title">{{ t('pos.title') }}</h1>
        <p class="page-subtitle">{{ till?.shop_name ?? t('pos.subtitle') }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <template v-if="selling && view === 'sell'">
          <button type="button" class="btn-secondary px-3.5 py-2 text-[14px]" @click="startMove('In')">{{ t('till.cashIn') }}</button>
          <button type="button" class="btn-secondary px-3.5 py-2 text-[14px]" @click="startMove('Out')">{{ t('till.cashOut') }}</button>
          <button type="button" class="btn-secondary px-3.5 py-2 text-[14px]" @click="showX">{{ t('till.xReport') }}</button>
          <button type="button" class="btn-secondary px-3.5 py-2 text-[14px]" :disabled="stepName === 'pay'" @click="startClose">
            {{ t('till.close') }}
          </button>
        </template>
        <RouterLink v-if="till" to="/pos/sessions" class="btn-quiet px-3.5 py-2 text-[14px]">{{ t('till.history') }}</RouterLink>
        <select
          v-if="shops.length > 1"
          v-model="shop"
          class="field w-auto rounded-xl bg-white py-2.5 text-[15px]"
          :aria-label="t('pos.shop')"
          :disabled="stepName !== 'cart' || view !== 'sell'"
        >
          <option v-for="s in shops" :key="s.name" :value="s.name">{{ s.shop_name }}</option>
        </select>
      </div>
    </div>

    <p v-if="!shop" class="notice-warn mt-6">{{ t('shop.noShop') }}</p>
    <p v-if="error" class="notice-error mt-6" role="alert">{{ error }}</p>
    <p v-if="info" class="notice-ok mt-6" role="status">{{ info }}</p>

    <!-- Closing the till -->
    <section v-if="shop && till && view === 'close'" class="card-pad mt-6 max-w-2xl">
      <template v-if="closeStep === 'count'">
        <h2 class="text-[20px] font-semibold text-slate-900">{{ t('till.countTitle') }}</h2>
        <p class="hint mt-1">{{ t('till.countHint') }}</p>
        <div class="mt-5 grid gap-4 sm:grid-cols-2">
          <div v-for="p in till.payments" :key="p.mode">
            <label class="label" :for="`count-${p.mode}`">{{ p.cash ? t('till.cashInDrawer') : t('till.methodTotal', { method: methodLabel(p.mode, t) }) }}</label>
            <input
              :id="`count-${p.mode}`"
              v-model.number="counts[p.mode]"
              type="number"
              min="0"
              step="0.01"
              inputmode="decimal"
              class="field text-[20px] tabular-nums"
              @keydown.enter.prevent="reviewClose"
            />
          </div>
        </div>
        <div class="mt-6 flex flex-wrap gap-2">
          <button type="button" class="btn-secondary btn-lg" @click="view = 'sell'">{{ t('pos.back') }}</button>
          <button type="button" class="btn-primary btn-lg" :disabled="!countsValid || busy" @click="reviewClose">{{ t('till.review') }}</button>
        </div>
      </template>

      <template v-else-if="closeReport">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h2 class="text-[20px] font-semibold text-slate-900">
            {{ closeStep === 'done' ? t('till.zReport') : t('till.reviewTitle') }}
          </h2>
          <span v-if="closeStep === 'done'" class="badge-neutral">{{ t('till.closedBadge') }}</span>
        </div>
        <p v-if="closeStep === 'review'" class="mt-3" :class="hasDifference ? 'notice-warn' : 'notice-ok'">
          {{ hasDifference ? t('till.differenceWarn') : t('till.balanced') }}
        </p>
        <div class="mt-5">
          <TillReport :report="closeReport" />
        </div>
        <template v-if="closeStep === 'review'">
          <label class="label mt-5" for="close-note">{{ t('till.note') }}</label>
          <textarea id="close-note" v-model="closeNote" rows="2" maxlength="1000" class="field text-[15px]" :placeholder="t('till.notePlaceholder')" />
          <div class="mt-6 flex flex-wrap gap-2">
            <button type="button" class="btn-secondary btn-lg" :disabled="busy" @click="closeStep = 'count'">{{ t('till.recount') }}</button>
            <button type="button" class="btn-primary btn-lg" :disabled="busy" @click="confirmClose">
              {{ busy ? t('pos.saving') : t('till.confirmClose') }}
            </button>
          </div>
        </template>
        <div v-else class="mt-6 flex flex-wrap gap-2">
          <button type="button" class="btn-secondary btn-lg" @click="printTillReport(closeReport)">{{ t('till.printReport') }}</button>
          <button type="button" class="btn-primary btn-lg" @click="finishClose">{{ t('till.done') }}</button>
        </div>
      </template>
    </section>

    <!-- No open session: open the till -->
    <section v-else-if="shop && till && !tillSession" class="card-pad mt-6 max-w-md">
      <h2 class="text-[20px] font-semibold text-slate-900">{{ t('till.openTitle') }}</h2>
      <p class="hint mt-1">{{ t('till.openHint') }}</p>
      <label class="label mt-5" for="opening-cash">{{ t('till.openingCash') }}</label>
      <input
        id="opening-cash"
        v-model.number="openingCash"
        type="number"
        min="0"
        step="0.01"
        inputmode="decimal"
        class="field text-[22px] tabular-nums"
        :placeholder="money(0)"
        @keydown.enter.prevent="openSession"
      />
      <p v-if="till.last_cash !== null" class="hint mt-2">{{ t('till.lastCash', { amount: money(till.last_cash) }) }}</p>
      <button type="button" class="btn-primary btn-lg mt-6 w-full" :disabled="busy || Number(openingCash) < 0" @click="openSession">
        {{ t('till.open') }}
      </button>
    </section>

    <!-- Someone else's session, or the user's own from an earlier day -->
    <section v-else-if="shop && till && tillSession && !selling" class="card-pad mt-6 max-w-md">
      <template v-if="tillSession.mine">
        <h2 class="text-[20px] font-semibold text-slate-900">{{ t('till.outdatedTitle') }}</h2>
        <p class="mt-2 text-[15px] text-slate-600">{{ t('till.outdatedBody', { when: formatWhen(tillSession.opened, locale) }) }}</p>
        <button type="button" class="btn-primary btn-lg mt-6 w-full" @click="startClose">{{ t('till.close') }}</button>
      </template>
      <template v-else>
        <h2 class="text-[20px] font-semibold text-slate-900">{{ t('till.busyTitle') }}</h2>
        <p class="mt-2 text-[15px] text-slate-600">
          {{ t('till.busyBody', { name: tillSession.user_name, when: formatWhen(tillSession.opened, locale) }) }}
        </p>
        <button v-if="till.can_manage" type="button" class="btn-primary btn-lg mt-6 w-full" @click="startClose">
          {{ t('till.closeTheirs', { name: tillSession.user_name }) }}
        </button>
        <p v-else class="hint mt-4">{{ t('till.askToClose') }}</p>
      </template>
    </section>

    <div v-if="shop && till && selling && view === 'sell'" class="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
      <!-- Products -->
      <section class="min-w-0">
        <div class="card p-3">
          <label class="sr-only" for="pos-scan">{{ t('pos.scan') }}</label>
          <input
            id="pos-scan"
            ref="scanInput"
            v-model="query"
            type="search"
            dir="auto"
            autocomplete="off"
            class="field py-3.5 text-[18px]"
            :placeholder="t('pos.scan')"
            @input="onType"
            @keydown.enter.prevent="onEnter"
          />
        </div>
        <p v-if="notice" class="notice-warn mt-3" role="status">{{ notice }}</p>

        <ul class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4" :aria-busy="loading">
          <li v-for="product in products" :key="product.item_code">
            <button
              type="button"
              class="card flex h-full w-full flex-col items-start gap-1 p-4 text-start transition hover:ring-2 hover:ring-brand-200 focus-visible:ring-2 focus-visible:ring-brand-600 disabled:opacity-50"
              :class="lastAdded === product.item_code ? 'ring-2 ring-brand-600' : ''"
              :disabled="stepName === 'pay' || busy"
              @click="add(product)"
            >
              <span class="line-clamp-2 text-[15px] font-medium text-slate-900" dir="auto">{{ product.item_name }}</span>
              <span class="mt-auto pt-2 text-[17px] font-semibold text-slate-900">
                {{ product.price ? money(product.price) : t('pos.noPriceShort') }}
              </span>
              <span class="text-[13px]" :class="product.stock > 0 ? 'text-slate-500' : 'text-red-600'">
                {{ t('pos.inStock', { qty: formatQty(product.stock, locale) }) }}
              </span>
            </button>
          </li>
        </ul>
        <p v-if="!loading && !products.length" class="hint mt-6 text-center">{{ t('pos.noProducts') }}</p>

        <!-- Today's sales -->
        <div v-if="recent.length" class="mt-8">
          <h2 class="label">{{ t('pos.today') }}</h2>
          <ul class="list">
            <li v-for="row in recent" :key="row.name" class="flex items-center gap-3 px-4 py-3">
              <span class="w-14 text-[14px] text-slate-500 tabular-nums">{{ row.time }}</span>
              <span class="min-w-0 flex-1 truncate text-[14px] text-slate-700">{{ row.name }}</span>
              <span class="text-[15px] font-medium text-slate-900 tabular-nums">{{ money(row.total) }}</span>
              <button type="button" class="btn-quiet px-2.5 py-1 text-[13px]" @click="print(row.name)">
                {{ t('pos.reprint') }}
              </button>
            </li>
          </ul>
        </div>
      </section>

      <!-- Cart and payment -->
      <aside ref="cartBox" class="card flex min-w-0 flex-col p-5 lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:self-start lg:overflow-y-auto">
        <template v-if="stepName === 'done' && sale">
          <div class="py-6 text-center" role="status">
            <div class="mx-auto grid h-14 w-14 place-items-center rounded-full bg-green-50 text-green-700">
              <svg viewBox="0 0 24 24" class="h-7 w-7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 5 5 9-10" /></svg>
            </div>
            <p class="mt-4 text-[15px] text-slate-500">{{ t('pos.paidTotal', { total: money(sale.total) }) }}</p>
            <template v-if="sale.change">
              <p class="mt-4 text-[14px] text-slate-500">{{ t('pos.giveChange') }}</p>
              <p class="text-[40px] font-semibold tracking-tight text-slate-900 tabular-nums">{{ money(sale.change) }}</p>
            </template>
            <p class="hint mt-2">{{ sale.name }}</p>
          </div>
          <div class="mt-auto grid gap-2">
            <button type="button" class="btn-secondary btn-lg w-full" @click="print(sale)">{{ t('pos.print') }}</button>
            <button type="button" class="btn-primary btn-lg w-full" @click="startNew()">{{ t('pos.newSale') }}</button>
          </div>
        </template>

        <template v-else>
          <div class="flex items-center justify-between">
            <h2 class="text-[17px] font-semibold text-slate-900">
              {{ t('pos.cart') }}
              <span v-if="units" class="ms-1 text-slate-500">· {{ formatQty(units, locale) }}</span>
            </h2>
            <button v-if="cart.length && stepName === 'cart'" type="button" class="btn-quiet px-2.5 py-1 text-[13px]" @click="clearCart">
              {{ t('pos.clear') }}
            </button>
          </div>

          <p v-if="!cart.length" class="hint py-10 text-center">{{ t('pos.empty') }}</p>
          <ul v-else class="-mx-1 mt-3 min-h-0 flex-1 space-y-1 overflow-y-auto px-1">
            <li v-for="line in cart" :key="line.item_code" class="rounded-xl px-2 py-2 hover:bg-[var(--row-hover)]">
              <div class="flex items-start gap-2">
                <span class="min-w-0 flex-1 text-[15px] text-slate-900" dir="auto">{{ line.item_name }}</span>
                <span class="text-[15px] font-medium text-slate-900 tabular-nums">{{ money(line.price * line.qty) }}</span>
              </div>
              <div class="mt-1.5 flex items-center gap-2">
                <div class="inline-flex items-center rounded-full bg-slate-100">
                  <button type="button" class="icon-btn h-8 w-8" :disabled="stepName !== 'cart'" :aria-label="t('pos.less', { name: line.item_name })" @click="setQty(line, line.qty - 1)">−</button>
                  <input
                    :value="line.qty"
                    type="number"
                    min="1"
                    inputmode="numeric"
                    class="w-12 bg-transparent text-center text-[15px] tabular-nums outline-none"
                    :disabled="stepName !== 'cart'"
                    :aria-label="t('pos.qty', { name: line.item_name })"
                    @change="setQty(line, Number(($event.target as HTMLInputElement).value) || 0)"
                  />
                  <button type="button" class="icon-btn h-8 w-8" :disabled="stepName !== 'cart'" :aria-label="t('pos.more', { name: line.item_name })" @click="setQty(line, line.qty + 1)">+</button>
                </div>
                <span class="text-[13px] text-slate-500">× {{ money(line.price) }}</span>
                <span v-if="line.qty > line.stock" class="badge-warn ms-auto">{{ t('pos.lowStock') }}</span>
              </div>
            </li>
          </ul>

          <div class="mt-4 border-t border-[var(--hairline)] pt-4">
            <div class="flex items-baseline justify-between">
              <span class="text-[15px] text-slate-500">{{ t('pos.total') }}</span>
              <span class="text-[32px] font-semibold tracking-tight text-slate-900 tabular-nums">{{ money(total) }}</span>
            </div>

            <!-- Payment -->
            <div v-if="stepName === 'pay'" class="mt-4 space-y-4">
              <div class="segmented w-full" role="group" :aria-label="t('pos.method')">
                <button
                  v-for="p in till.payments"
                  :key="p.mode"
                  type="button"
                  class="segment h-10 flex-1 text-[15px]"
                  :aria-pressed="mode === p.mode"
                  @click="mode = p.mode"
                >
                  {{ methodLabel(p.mode, t) }}
                </button>
              </div>

              <template v-if="method?.cash">
                <div>
                  <label class="label" for="pos-tendered">{{ t('pos.tendered') }}</label>
                  <input
                    id="pos-tendered"
                    v-model.number="tendered"
                    type="number"
                    min="0"
                    step="0.01"
                    inputmode="decimal"
                    class="field text-[20px] tabular-nums"
                    :placeholder="money(total)"
                    @keydown.enter.prevent="pay"
                  />
                </div>
                <div class="flex flex-wrap gap-2">
                  <button v-for="amount in quickCash(total)" :key="amount" type="button" class="btn-secondary px-3 py-2 text-[14px] tabular-nums" @click="tendered = amount">
                    {{ money(amount) }}
                  </button>
                </div>
                <div class="flex items-baseline justify-between">
                  <span class="text-[15px] text-slate-500">{{ t('pos.change') }}</span>
                  <span class="text-[22px] font-semibold text-slate-900 tabular-nums">{{ money(change) }}</span>
                </div>
              </template>
              <p v-else class="hint">{{ t('pos.cardHint', { total: money(total) }) }}</p>

              <div class="grid grid-cols-[auto_1fr] gap-2">
                <button type="button" class="btn-secondary btn-lg" :disabled="busy" @click="stepName = 'cart'">{{ t('pos.back') }}</button>
                <button type="button" class="btn-primary btn-lg" :disabled="!canPay" @click="pay">
                  {{ busy ? t('pos.saving') : t('pos.confirm') }}
                </button>
              </div>
            </div>

            <button v-else type="button" class="btn-primary btn-lg mt-4 w-full" :disabled="!cart.length" @click="goPay">
              {{ t('pos.pay') }} <span class="ms-2 opacity-70">F9</span>
            </button>
          </div>
        </template>
      </aside>
    </div>

    <!-- Phone: the cart is below the products, so keep the total and Pay in reach -->
    <button
      v-if="till && selling && view === 'sell' && cart.length && stepName === 'cart'"
      type="button"
      class="btn-primary btn-lg fixed inset-x-3 bottom-3 z-30 justify-between shadow-lg lg:hidden"
      @click="payFromBar"
    >
      <span>{{ t('pos.pay') }} · {{ formatQty(units, locale) }}</span>
      <span class="tabular-nums">{{ money(total) }}</span>
    </button>

    <!-- Cash in / cash out -->
    <AppDialog v-if="moveOpen" :title="moveType === 'In' ? t('till.cashIn') : t('till.cashOut')" @close="moveOpen = false">
      <p class="hint">{{ moveType === 'In' ? t('till.cashInHint') : t('till.cashOutHint') }}</p>
      <label class="label mt-4" for="move-amount">{{ t('till.amount') }}</label>
      <input id="move-amount" v-model.number="moveAmount" autofocus type="number" min="0" step="0.01" inputmode="decimal" class="field text-[20px] tabular-nums" />
      <label class="label mt-4" for="move-reason">{{ t('till.reason') }}</label>
      <input
        id="move-reason"
        v-model="moveReason"
        maxlength="140"
        dir="auto"
        class="field text-[15px]"
        :placeholder="moveType === 'In' ? t('till.reasonInPlaceholder') : t('till.reasonOutPlaceholder')"
        @keydown.enter.prevent="saveMove"
      />
      <div class="mt-6 grid grid-cols-[auto_1fr] gap-2">
        <button type="button" class="btn-secondary btn-lg" @click="moveOpen = false">{{ t('categories.cancel') }}</button>
        <button type="button" class="btn-primary btn-lg" :disabled="!moveValid || busy" @click="saveMove">{{ t('till.record') }}</button>
      </div>
    </AppDialog>

    <!-- X report -->
    <AppDialog v-if="xReport" wide :title="t('till.xReport')" @close="xReport = null">
      <TillReport :report="xReport" />
      <div class="mt-6 flex justify-end">
        <button type="button" class="btn-secondary" @click="printTillReport(xReport)">{{ t('till.printReport') }}</button>
      </div>
    </AppDialog>

    <PosReceipt v-if="printSale" :sale="printSale" />
    <TillReport v-if="printReport" :report="printReport" variant="print" />
  </div>
</template>
