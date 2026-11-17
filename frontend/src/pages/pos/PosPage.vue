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
import { newRequestId } from '@/receiving'
import { session } from '@/session'

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

function fail(err: unknown) {
  error.value = err instanceof ApiError ? err.message : String(err)
}

async function openTill() {
  if (!shop.value) return
  error.value = ''
  till.value = null
  cart.value = loadCart(shop.value)
  stepName.value = 'cart'
  try {
    till.value = await posApi.till(shop.value)
    mode.value = (till.value.payments.find((p) => p.default) ?? till.value.payments[0])?.mode ?? ''
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
    printSale.value = typeof target === 'string' ? await posApi.sale(target) : target
    await nextTick()
    window.print()
  } catch (err) {
    fail(err)
  }
}

function onKey(event: KeyboardEvent) {
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
  <div class="mx-auto max-w-7xl pb-20 lg:pb-0">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="page-title">{{ t('pos.title') }}</h1>
        <p class="page-subtitle">{{ till?.shop_name ?? t('pos.subtitle') }}</p>
      </div>
      <select
        v-if="shops.length > 1"
        v-model="shop"
        class="field w-auto rounded-xl bg-white py-2.5 text-[15px]"
        :aria-label="t('pos.shop')"
        :disabled="stepName !== 'cart'"
      >
        <option v-for="s in shops" :key="s.name" :value="s.name">{{ s.shop_name }}</option>
      </select>
    </div>

    <p v-if="!shop" class="notice-warn mt-6">{{ t('shop.noShop') }}</p>
    <p v-if="error" class="notice-error mt-6" role="alert">{{ error }}</p>

    <div v-if="shop && till" class="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
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
      v-if="till && cart.length && stepName === 'cart'"
      type="button"
      class="btn-primary btn-lg fixed inset-x-3 bottom-3 z-30 justify-between shadow-lg lg:hidden"
      @click="payFromBar"
    >
      <span>{{ t('pos.pay') }} · {{ formatQty(units, locale) }}</span>
      <span class="tabular-nums">{{ money(total) }}</span>
    </button>

    <PosReceipt v-if="printSale" :sale="printSale" />
  </div>
</template>
