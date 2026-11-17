<script setup lang="ts">
// Enter a supplier's invoice for goods received into one shop: against an
// open purchase order (its rows at the order's cost) and/or any products at
// the cost on the invoice. Posts a Purchase Receipt (stock) and a Purchase
// Invoice (what is owed) in one go.
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import ProductPicker from '@/components/ProductPicker.vue'
import { formatMoney, formatQty, type Product } from '@/inventory'
import {
  inDays,
  type InvoiceDraft,
  type InvoiceLine,
  type Order,
  type OrderRow,
  purchasingApi,
  type Supplier,
} from '@/purchasing'
import { newRequestId } from '@/receiving'
import { session } from '@/session'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

const shops = computed(() => session.context?.shops ?? [])
const suppliers = ref<Supplier[]>([])
const openOrders = ref<OrderRow[]>([])
const order = ref<Order | null>(null)
const draft = ref<InvoiceDraft>({
  supplier: typeof route.query.supplier === 'string' ? route.query.supplier : '',
  shop: shops.value[0]?.name ?? '',
  order: typeof route.query.order === 'string' ? route.query.order : '',
  bill_no: '',
  bill_date: inDays(0),
  lines: [],
})
const loading = ref(false)
const busy = ref(false)
const error = ref('')
let requestId = newRequestId()

const currency = computed(() => order.value?.currency ?? null)
const money = (value: number) => formatMoney(value, currency.value, locale.value)
const qty = (value: number) => formatQty(value, locale.value)
const fail = (err: unknown) => (error.value = err instanceof ApiError ? err.message : String(err))

const supplierName = computed(() => suppliers.value.find((s) => s.name === draft.value.supplier)?.supplier_name ?? '')
const shopName = computed(() => shops.value.find((s) => s.name === draft.value.shop)?.shop_name ?? '')
const ordersForSupplier = computed(() => openOrders.value.filter((o) => o.supplier_name === supplierName.value))

const lineOk = (l: InvoiceLine) =>
  l.qty === '' || (Number(l.qty) >= 0 && (!l.row || Number(l.qty) <= (l.remaining ?? 0)) && (!!l.row || Number(l.rate) >= 0))
const units = computed(() => draft.value.lines.reduce((sum, l) => sum + (Number(l.qty) || 0), 0))
const total = computed(() => draft.value.lines.reduce((sum, l) => sum + (Number(l.qty) || 0) * (Number(l.rate) || 0), 0))
const valid = computed(
  () =>
    !!draft.value.supplier &&
    !!draft.value.shop &&
    !!draft.value.bill_no.trim() &&
    !!draft.value.bill_date &&
    units.value > 0 &&
    draft.value.lines.every(lineOk),
)

async function loadOrders() {
  if (!draft.value.shop) return
  try {
    openOrders.value = await purchasingApi.orders(draft.value.shop, 'open', '')
  } catch {
    openOrders.value = []
  }
}

async function useOrder(name: string) {
  // Lines of a previous order go; products added by hand stay.
  draft.value.lines = draft.value.lines.filter((l) => !l.row)
  order.value = null
  if (!name) return
  try {
    const o = await purchasingApi.order(name)
    order.value = o
    draft.value.supplier = o.supplier
    if (o.shop) draft.value.shop = o.shop
    draft.value.lines.unshift(
      ...o.lines
        .filter((l) => l.remaining > 0)
        .map((l) => ({ row: l.row, item_code: l.item_code, item_name: l.item_name, qty: l.remaining, rate: l.rate, remaining: l.remaining })),
    )
  } catch (err) {
    fail(err)
  }
}

onMounted(async () => {
  loading.value = true
  try {
    suppliers.value = (await purchasingApi.suppliers()).filter((s) => !s.disabled)
    if (draft.value.order) await useOrder(draft.value.order)
    await loadOrders()
  } catch (err) {
    fail(err)
  } finally {
    loading.value = false
  }
})
watch(
  () => draft.value.shop,
  (shop, old) => {
    if (shop === old) return
    if (order.value && order.value.shop !== shop) {
      draft.value.order = ''
      useOrder('')
    }
    loadOrders()
  },
)
watch(
  () => draft.value.supplier,
  () => {
    if (order.value && order.value.supplier !== draft.value.supplier) {
      draft.value.order = ''
      useOrder('')
    }
  },
)

async function addProduct(product: Product) {
  const existing = draft.value.lines.find((l) => !l.row && l.item_code === product.item_code)
  if (existing) {
    existing.qty = (Number(existing.qty) || 0) + 1
    return
  }
  draft.value.lines.push({ item_code: product.item_code, item_name: product.item_name, qty: 1, rate: '' })
  try {
    const costs = await purchasingApi.costs([product.item_code], draft.value.supplier)
    const found = draft.value.lines.find((l) => !l.row && l.item_code === product.item_code)
    if (found && found.rate === '' && costs[product.item_code]) found.rate = costs[product.item_code]
  } catch {
    // the cost is only a suggestion
  }
}

async function save() {
  if (!valid.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const saved = await purchasingApi.enterInvoice({ ...draft.value, bill_no: draft.value.bill_no.trim() }, requestId)
    requestId = newRequestId()
    router.push({ path: '/supplier-invoices', query: { entered: saved.bill_no, units: String(units.value), shop: saved.shop_name } })
  } catch (err) {
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
      <h1 class="page-title">{{ t('bill.new') }}</h1>
      <p class="page-subtitle">{{ t('bill.newSubtitle') }}</p>
    </div>

    <p v-if="error" class="notice-error mt-6" role="alert">{{ error }}</p>

    <div v-if="loading" class="mt-6 grid gap-4 sm:grid-cols-2">
      <div class="skeleton h-20 rounded-2xl" />
      <div class="skeleton h-20 rounded-2xl" />
    </div>

    <template v-else>
      <section class="card-pad animate-rise mt-6 grid gap-4 sm:grid-cols-2">
        <div>
          <label class="label" for="bill-supplier">{{ t('po.supplier') }}</label>
          <select id="bill-supplier" v-model="draft.supplier" class="field text-[15px]" :disabled="!!order">
            <option value="" disabled>{{ t('po.chooseSupplier') }}</option>
            <option v-for="s in suppliers" :key="s.name" :value="s.name">{{ s.supplier_name }}</option>
          </select>
          <RouterLink to="/suppliers" class="hint mt-1 inline-block hover:underline">{{ t('po.manageSuppliers') }}</RouterLink>
        </div>
        <div>
          <label class="label" for="bill-shop">{{ t('bill.shop') }}</label>
          <select id="bill-shop" v-model="draft.shop" class="field text-[15px]">
            <option v-for="s in shops" :key="s.name" :value="s.name">{{ s.shop_name }}</option>
          </select>
        </div>
        <div>
          <label class="label" for="bill-no">{{ t('bill.number') }}</label>
          <input id="bill-no" v-model="draft.bill_no" maxlength="140" dir="auto" class="field text-[15px]" :placeholder="t('bill.numberPlaceholder')" />
        </div>
        <div>
          <label class="label" for="bill-date">{{ t('bill.date') }}</label>
          <input id="bill-date" v-model="draft.bill_date" type="date" :max="inDays(0)" class="field text-[15px]" />
        </div>
        <div class="sm:col-span-2">
          <label class="label" for="bill-order">{{ t('bill.order') }}</label>
          <select id="bill-order" v-model="draft.order" class="field text-[15px]" :disabled="!draft.supplier" @change="useOrder(draft.order)">
            <option value="">{{ t('bill.noOrder') }}</option>
            <option v-if="order && !ordersForSupplier.some((o) => o.name === order?.name)" :value="order.name">{{ order.name }}</option>
            <option v-for="o in ordersForSupplier" :key="o.name" :value="o.name">
              {{ o.name }} · {{ t(`po.status.${o.status}`) }} · {{ formatMoney(o.total, o.currency, locale) }}
            </option>
          </select>
          <p class="hint mt-1">{{ order ? t('bill.orderHint') : t('bill.noOrderHint') }}</p>
        </div>
        <div class="sm:col-span-2">
          <ProductPicker :shop="draft.shop" input-id="bill-scan" :label="t('bill.addProducts')" @pick="addProduct" />
        </div>
      </section>

      <section class="card-pad mt-6">
        <p v-if="!draft.lines.length" class="hint">{{ t('bill.noLines') }}</p>
        <div v-else class="-mx-2 overflow-x-auto">
          <table class="w-full min-w-[600px] text-[14px]">
            <thead>
              <tr class="text-[12px] text-slate-500">
                <th class="px-2 py-2 text-start font-medium">{{ t('po.col.product') }}</th>
                <th class="px-2 py-2 text-center font-medium">{{ t('bill.col.received') }}</th>
                <th class="px-2 py-2 text-end font-medium">{{ t('po.col.cost') }}</th>
                <th class="px-2 py-2 text-end font-medium">{{ t('po.col.amount') }}</th>
                <th class="w-10"><span class="sr-only">{{ t('stock.removeLine', { name: '' }) }}</span></th>
              </tr>
            </thead>
            <tbody class="stagger">
              <tr v-for="(line, i) in draft.lines" :key="line.row ?? `free-${line.item_code}-${i}`" class="border-t border-[var(--hairline)]">
                <td class="px-2 py-2.5">
                  <span class="block font-medium text-slate-900" dir="auto">{{ line.item_name }}</span>
                  <span v-if="line.row" class="block text-[12px] text-slate-500">{{ t('bill.fromOrder', { qty: qty(line.remaining ?? 0) }) }}</span>
                </td>
                <td class="px-2 py-2.5 text-center">
                  <input
                    v-model.number="line.qty"
                    type="number"
                    min="0"
                    :max="line.row ? line.remaining : undefined"
                    step="any"
                    class="field mx-auto w-24 px-2 py-2 text-center tabular-nums"
                    :class="lineOk(line) ? '' : 'ring-2 ring-red-500'"
                    :aria-label="t('stock.qtyFor', { name: line.item_name })"
                  />
                </td>
                <td class="px-2 py-2.5 text-end">
                  <span v-if="line.row" class="tabular-nums text-slate-600" :title="t('bill.orderCost')">{{ money(Number(line.rate) || 0) }}</span>
                  <input
                    v-else
                    v-model.number="line.rate"
                    type="number"
                    min="0"
                    step="0.01"
                    class="field ms-auto w-28 px-3 py-2 text-end tabular-nums"
                    :aria-label="t('po.costFor', { name: line.item_name })"
                  />
                </td>
                <td class="px-2 py-2.5 text-end font-medium tabular-nums">{{ money((Number(line.qty) || 0) * (Number(line.rate) || 0)) }}</td>
                <td class="px-1 py-2.5 text-center">
                  <button type="button" class="icon-btn" :aria-label="t('stock.removeLine', { name: line.item_name })" @click="draft.lines = draft.lines.filter((l) => l !== line)">✕</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="mt-4 flex items-baseline justify-between border-t border-[var(--hairline)] pt-4">
          <span class="text-[15px] text-slate-500">{{ t('bill.total') }}</span>
          <span class="text-[26px] font-semibold text-slate-900 tabular-nums">{{ money(total) }}</span>
        </div>
        <div class="mt-5 flex flex-wrap gap-2">
          <button type="button" class="btn-primary btn-lg" :disabled="!valid || busy" @click="save">
            {{ busy ? t('pos.saving') : t('bill.save', { units: qty(units), shop: shopName }) }}
          </button>
          <RouterLink to="/supplier-invoices" class="btn-secondary btn-lg">{{ t('categories.cancel') }}</RouterLink>
        </div>
        <p class="hint mt-3">{{ t('bill.saveHint') }}</p>
      </section>
    </template>
  </div>
</template>
