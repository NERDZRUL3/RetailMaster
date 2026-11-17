<script setup lang="ts">
// Read a supplier's delivery note (PDF or photo): the server reads the text
// (or OCRs a scan) and proposes supplier, note number and products. The user
// checks and corrects the draft, then is asked whether to update the shop's
// stock. Only a "yes" posts anything.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { ApiError } from '@/api'
import AppDialog from '@/components/AppDialog.vue'
import ProductPicker from '@/components/ProductPicker.vue'
import { formatDay } from '@/dashboard'
import { type DraftLine, deliveryNotesApi, type NoteDraft, type UnmatchedLine } from '@/deliveryNotes'
import { formatMoney, formatQty, type Product } from '@/inventory'
import { type OrderRow, purchasingApi, type Supplier } from '@/purchasing'
import { newRequestId } from '@/receiving'
import { session } from '@/session'

const { t, locale } = useI18n()
const router = useRouter()

const shops = computed(() => session.context?.shops ?? [])
const suppliers = ref<Supplier[]>([])
const openOrders = ref<OrderRow[]>([])

const draft = ref<NoteDraft | null>(null)
const supplier = ref('')
const shop = ref(shops.value[0]?.name ?? '')
const order = ref('')
const reference = ref('')
const lines = ref<DraftLine[]>([])
const unmatched = ref<UnmatchedLine[]>([])
const assigning = ref<UnmatchedLine | null>(null)

const reading = ref(false)
const busy = ref(false)
const error = ref('')
const dragging = ref(false)
const confirming = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
let requestId = newRequestId()

const qty = (value: number) => formatQty(value, locale.value)
const money = (value: number) => formatMoney(value, null, locale.value)
const fail = (err: unknown) => (error.value = err instanceof ApiError ? err.message : String(err))
const shopName = computed(() => shops.value.find((s) => s.name === shop.value)?.shop_name ?? '')
const supplierName = computed(() => suppliers.value.find((s) => s.name === supplier.value)?.supplier_name ?? '')
const ordersForSupplier = computed(() => openOrders.value.filter((o) => o.supplier_name === supplierName.value))
const units = computed(() => lines.value.reduce((sum, l) => sum + (Number(l.qty) || 0), 0))
const valid = computed(
  () =>
    !!supplier.value &&
    !!shop.value &&
    !!reference.value.trim() &&
    units.value > 0 &&
    lines.value.every((l) => l.qty === '' || Number(l.qty) >= 0) &&
    lines.value.every((l) => l.rate === '' || l.rate === null || Number(l.rate) >= 0),
)
const stockNow = (line: DraftLine) => line.stock[shop.value] ?? 0

async function loadOrders() {
  if (!shop.value) return
  try {
    openOrders.value = await purchasingApi.orders(shop.value, 'open', '')
  } catch {
    openOrders.value = []
  }
  if (order.value && !openOrders.value.some((o) => o.name === order.value)) order.value = ''
}
watch(shop, loadOrders)
watch(supplier, () => {
  if (order.value && !ordersForSupplier.value.some((o) => o.name === order.value)) order.value = ''
})

async function read(file: File | undefined) {
  if (!file || reading.value) return
  error.value = ''
  reading.value = true
  try {
    const [result, list] = await Promise.all([
      deliveryNotesApi.read(file),
      suppliers.value.length ? Promise.resolve(suppliers.value) : purchasingApi.suppliers(),
    ])
    suppliers.value = list.filter((s) => !s.disabled)
    draft.value = result
    supplier.value = result.supplier ?? ''
    if (result.shop) shop.value = result.shop
    reference.value = result.reference
    lines.value = result.lines.map((l) => ({ ...l, rate: l.rate ?? '' }))
    unmatched.value = result.unmatched
    requestId = newRequestId()
    await loadOrders()
    order.value = result.order ?? ''
  } catch (err) {
    fail(err)
  } finally {
    reading.value = false
    dragging.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

function onDrop(event: DragEvent) {
  dragging.value = false
  read(event.dataTransfer?.files?.[0])
}

function addProduct(product: Product) {
  const from = assigning.value
  const stock = Object.fromEntries(product.stock.map((s) => [s.shop, s.qty]))
  const existing = lines.value.find((l) => l.item_code === product.item_code)
  if (existing) existing.qty = (Number(existing.qty) || 0) + (from?.qty ?? 1)
  else
    lines.value.push({
      item_code: product.item_code,
      item_name: product.item_name,
      qty: from?.qty ?? 1,
      rate: from?.rate ?? '',
      raw: from?.raw,
      stock,
    })
  if (from) unmatched.value = unmatched.value.filter((u) => u !== from)
  assigning.value = null
}

function startOver() {
  draft.value = null
  lines.value = []
  unmatched.value = []
  error.value = ''
}

async function receive() {
  if (!draft.value || !valid.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const saved = await deliveryNotesApi.receive(
      {
        supplier: supplier.value,
        shop: shop.value,
        order: order.value,
        reference: reference.value.trim(),
        file: draft.value.file,
        lines: lines.value,
      },
      requestId,
    )
    router.push({
      path: '/supplier-invoices',
      query: { delivered: saved.bill_no, units: String(units.value), shop: saved.shop_name },
    })
  } catch (err) {
    confirming.value = false
    fail(err)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-5xl">
    <RouterLink to="/supplier-invoices" class="btn-quiet -ms-3 px-3 py-1.5 text-[14px]">← {{ t('bill.title') }}</RouterLink>
    <div class="mt-2">
      <h1 class="page-title">{{ t('note.title') }}</h1>
      <p class="page-subtitle">{{ t('note.subtitle') }}</p>
    </div>

    <p v-if="error" class="notice-error mt-6" role="alert">{{ error }}</p>

    <!-- 1. Upload -->
    <section v-if="!draft" class="mt-6">
      <label
        for="note-file"
        class="card lift flex cursor-pointer flex-col items-center justify-center gap-3 border-2 border-dashed px-6 py-14 text-center transition"
        :class="dragging ? 'border-brand-500 bg-brand-50/60' : 'border-[var(--hairline)]'"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="onDrop"
      >
        <svg viewBox="0 0 24 24" class="h-12 w-12 text-brand-600" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M7 3h7l5 5v13H7z" />
          <path d="M14 3v5h5M12 18v-6M9.5 14.5 12 12l2.5 2.5" />
        </svg>
        <span v-if="reading" class="text-[16px] font-medium text-slate-900">{{ t('note.reading') }}</span>
        <template v-else>
          <span class="text-[16px] font-medium text-slate-900">{{ t('note.drop') }}</span>
          <span class="hint">{{ t('note.dropHint') }}</span>
          <span class="btn-primary mt-2">{{ t('note.chooseFile') }}</span>
        </template>
        <input
          id="note-file"
          ref="fileInput"
          type="file"
          accept="application/pdf,image/jpeg,image/png"
          class="sr-only"
          :disabled="reading"
          @change="read(($event.target as HTMLInputElement).files?.[0])"
        />
      </label>
      <div v-if="reading" class="mt-6 space-y-3">
        <div class="skeleton h-24 rounded-2xl" />
        <div class="skeleton h-40 rounded-2xl" />
      </div>
    </section>

    <!-- 2. Review -->
    <template v-else>
      <div class="mt-6 flex flex-wrap items-center gap-2 text-[14px]">
        <span class="font-medium text-slate-900" dir="auto">{{ draft.file_name }}</span>
        <span :class="draft.method === 'ocr' ? 'badge-warn' : 'badge-ok'">{{ t(`note.method.${draft.method}`) }}</span>
        <button type="button" class="btn-quiet ms-auto px-3 py-1.5" @click="startOver">{{ t('note.another') }}</button>
      </div>
      <p v-if="draft.method === 'ocr'" class="hint mt-2">{{ t('note.ocrHint') }}</p>

      <section class="card-pad animate-rise mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <label class="label" for="note-supplier">{{ t('po.supplier') }}</label>
          <select id="note-supplier" v-model="supplier" class="field text-[15px]" :class="supplier ? '' : 'ring-2 ring-amber-400'">
            <option value="" disabled>{{ t('po.chooseSupplier') }}</option>
            <option v-for="s in suppliers" :key="s.name" :value="s.name">{{ s.supplier_name }}</option>
          </select>
          <p v-if="!draft.supplier" class="hint mt-1">{{ t('note.supplierNotFound') }}</p>
        </div>
        <div>
          <label class="label" for="note-shop">{{ t('bill.shop') }}</label>
          <select id="note-shop" v-model="shop" class="field text-[15px]">
            <option v-for="s in shops" :key="s.name" :value="s.name">{{ s.shop_name }}</option>
          </select>
        </div>
        <div>
          <label class="label" for="note-ref">{{ t('note.number') }}</label>
          <input id="note-ref" v-model="reference" maxlength="140" dir="auto" class="field text-[15px]" :class="reference ? '' : 'ring-2 ring-amber-400'" />
          <p v-if="draft.date" class="hint mt-1">{{ t('note.dated', { date: formatDay(draft.date, locale, { day: 'numeric', month: 'long', year: 'numeric' }) }) }}</p>
        </div>
        <div>
          <label class="label" for="note-order">{{ t('bill.order') }}</label>
          <select id="note-order" v-model="order" class="field text-[15px]" :disabled="!supplier">
            <option value="">{{ t('note.noOrder') }}</option>
            <option v-for="o in ordersForSupplier" :key="o.name" :value="o.name">
              {{ o.name }} · {{ t(`po.status.${o.status}`) }} · {{ formatMoney(o.total, o.currency, locale) }}
            </option>
          </select>
          <p class="hint mt-1">{{ order ? t('note.orderHint') : t('note.noOrderHint') }}</p>
        </div>
      </section>

      <section class="card-pad mt-6">
        <h2 class="text-[17px] font-semibold text-slate-900">{{ t('note.products') }}</h2>
        <p v-if="!lines.length" class="hint mt-2">{{ t('note.noLines') }}</p>
        <div v-else class="-mx-2 mt-2 overflow-x-auto">
          <table class="w-full min-w-[560px] text-[14px]">
            <thead>
              <tr class="text-[12px] text-slate-500">
                <th class="px-2 py-2 text-start font-medium">{{ t('po.col.product') }}</th>
                <th class="px-2 py-2 text-center font-medium">{{ t('note.col.delivered') }}</th>
                <th class="px-2 py-2 text-end font-medium">{{ t('po.col.cost') }}</th>
                <th class="w-10"><span class="sr-only">{{ t('stock.removeLine', { name: '' }) }}</span></th>
              </tr>
            </thead>
            <tbody class="stagger">
              <tr v-for="line in lines" :key="line.item_code" class="border-t border-[var(--hairline)]">
                <td class="px-2 py-2.5">
                  <span class="block font-medium text-slate-900" dir="auto">{{ line.item_name }}</span>
                  <span v-if="line.raw" class="block max-w-[22rem] truncate text-[12px] text-slate-500" dir="auto" :title="line.raw">« {{ line.raw }} »</span>
                </td>
                <td class="px-2 py-2.5 text-center">
                  <input v-model.number="line.qty" type="number" min="0" step="any" class="field mx-auto w-24 px-2 py-2 text-center tabular-nums" :aria-label="t('stock.qtyFor', { name: line.item_name })" />
                </td>
                <td class="px-2 py-2.5 text-end">
                  <input
                    v-model.number="line.rate"
                    type="number"
                    min="0"
                    step="0.01"
                    class="field ms-auto w-28 px-3 py-2 text-end tabular-nums"
                    :placeholder="line.suggested_rate ? money(line.suggested_rate) : t('note.costOptional')"
                    :aria-label="t('po.costFor', { name: line.item_name })"
                  />
                </td>
                <td class="px-1 py-2.5 text-center">
                  <button type="button" class="icon-btn" :aria-label="t('stock.removeLine', { name: line.item_name })" @click="lines = lines.filter((l) => l !== line)">✕</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="unmatched.length" class="mt-5 rounded-xl bg-amber-50/70 p-3 ring-1 ring-amber-200">
          <h3 class="text-[14px] font-semibold text-amber-900">{{ t('note.unmatched', { n: unmatched.length }) }}</h3>
          <p class="mt-0.5 text-[13px] text-amber-800">{{ t('note.unmatchedHint') }}</p>
          <ul class="mt-2 space-y-1.5">
            <li v-for="(u, i) in unmatched" :key="i" class="flex flex-wrap items-center gap-2 text-[14px]">
              <span class="min-w-0 flex-1 truncate text-slate-800" dir="auto" :title="u.raw">« {{ u.raw }} »</span>
              <span class="tabular-nums text-slate-600">× {{ qty(u.qty) }}</span>
              <button type="button" class="btn-secondary px-3 py-1.5 text-[13px]" :aria-pressed="assigning === u" @click="assigning = assigning === u ? null : u">
                {{ assigning === u ? t('note.choosing') : t('note.choose') }}
              </button>
              <button type="button" class="btn-quiet px-2 py-1.5 text-[13px]" @click="unmatched = unmatched.filter((x) => x !== u)">{{ t('note.ignore') }}</button>
            </li>
          </ul>
        </div>

        <div class="mt-5">
          <ProductPicker
            :shop="shop"
            input-id="note-scan"
            :label="assigning ? t('note.pickFor', { line: assigning.raw }) : t('note.addProduct')"
            @pick="addProduct"
          />
        </div>

        <details class="mt-5 text-[13px]">
          <summary class="cursor-pointer text-slate-500 hover:text-slate-800">{{ t('note.showText') }}</summary>
          <pre class="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-xl bg-slate-50 p-3 text-[12px] text-slate-700" dir="auto">{{ draft.text || '—' }}</pre>
        </details>

        <div class="mt-6 flex flex-wrap gap-2 border-t border-[var(--hairline)] pt-5">
          <button type="button" class="btn-primary btn-lg" :disabled="!valid || busy" @click="confirming = true">
            {{ t('note.next', { units: qty(units) }) }}
          </button>
          <RouterLink to="/supplier-invoices" class="btn-secondary btn-lg">{{ t('categories.cancel') }}</RouterLink>
        </div>
      </section>
    </template>

    <!-- 3. Ask before the stock changes -->
    <AppDialog v-if="confirming" :title="t('note.confirmTitle', { shop: shopName })" @close="confirming = false">
      <p class="text-[14px] text-slate-600">
        {{ t('note.confirmText', { units: qty(units), ref: reference, supplier: supplierName }) }}
      </p>
      <ul class="mt-4 divide-y divide-[var(--hairline)] text-[14px]">
        <li v-for="line in lines.filter((l) => Number(l.qty) > 0)" :key="line.item_code" class="flex items-center gap-3 py-2">
          <span class="min-w-0 flex-1 truncate font-medium text-slate-900" dir="auto">{{ line.item_name }}</span>
          <span class="tabular-nums text-slate-500">{{ qty(stockNow(line)) }}</span>
          <span class="text-slate-400" aria-hidden="true">→</span>
          <span class="tabular-nums font-semibold text-slate-900">{{ qty(stockNow(line) + Number(line.qty)) }}</span>
          <span class="badge-ok tabular-nums">+{{ qty(Number(line.qty)) }}</span>
        </li>
      </ul>
      <p v-if="order" class="hint mt-3">{{ t('note.confirmOrder', { order }) }}</p>
      <div class="mt-6 flex flex-wrap gap-2">
        <button type="button" class="btn-primary btn-lg" autofocus :disabled="busy" @click="receive">
          {{ busy ? t('pos.saving') : t('note.yes') }}
        </button>
        <button type="button" class="btn-secondary btn-lg" :disabled="busy" @click="confirming = false">{{ t('note.notNow') }}</button>
      </div>
    </AppDialog>
  </div>
</template>
