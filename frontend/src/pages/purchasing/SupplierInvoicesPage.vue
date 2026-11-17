<script setup lang="ts">
// Supplier invoices: deliveries received from suppliers into the shops, with
// the supplier's invoice number and what is still owed.
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import { ApiError } from '@/api'
import { formatDay } from '@/dashboard'
import AppDialog from '@/components/AppDialog.vue'
import { deliveryNotesApi } from '@/deliveryNotes'
import { formatMoney, formatQty } from '@/inventory'
import { inDays, purchasingApi, type SupplierInvoice } from '@/purchasing'
import { newRequestId } from '@/receiving'
import { session } from '@/session'

const { t, locale } = useI18n()
const route = useRoute()
const shops = computed(() => session.context?.shops ?? [])
const canBuy = computed(() => !!session.context?.can_buy)

const shop = ref('')
const rows = ref<SupplierInvoice[]>([])
const loading = ref(false)
const error = ref('')
const entered = computed(() => {
  const params = {
    units: formatQty(Number(route.query.units) || 0, locale.value),
    shop: String(route.query.shop ?? ''),
  }
  if (typeof route.query.entered === 'string') return t('bill.entered', { ...params, bill: route.query.entered })
  if (typeof route.query.delivered === 'string') return t('note.received', { ...params, ref: route.query.delivered })
  return ''
})

// Entering the supplier's invoice for a delivery already received.
const invoicing = ref<SupplierInvoice | null>(null)
const billNo = ref('')
const billDate = ref(inDays(0))
const billBusy = ref(false)
const billError = ref('')
let billRequest = newRequestId()
function openInvoice(row: SupplierInvoice) {
  invoicing.value = row
  billNo.value = ''
  billDate.value = inDays(0)
  billError.value = ''
  billRequest = newRequestId()
}
async function saveInvoice() {
  if (!invoicing.value || !billNo.value.trim() || billBusy.value) return
  billBusy.value = true
  billError.value = ''
  try {
    const saved = await purchasingApi.invoiceReceipt(invoicing.value.receipt, billNo.value.trim(), billDate.value, billRequest)
    rows.value = rows.value.map((r) => (r.receipt === saved.receipt ? saved : r))
    invoicing.value = null
  } catch (err) {
    billError.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    billBusy.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = await purchasingApi.invoices(shop.value)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    loading.value = false
  }
}
watch(shop, load)
onMounted(load)

const day = (iso: string | null) => (iso ? formatDay(iso, locale.value, { day: 'numeric', month: 'short', year: 'numeric' }) : '—')
</script>

<template>
  <div class="mx-auto max-w-6xl">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="page-title">{{ t('bill.title') }}</h1>
        <p class="page-subtitle">{{ t('bill.subtitle') }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <select v-if="shops.length > 1" v-model="shop" class="field w-auto py-2.5 text-[15px]" :aria-label="t('stock.shop')">
          <option value="">{{ t('stock.allShops') }}</option>
          <option v-for="s in shops" :key="s.name" :value="s.name">{{ s.shop_name }}</option>
        </select>
        <RouterLink v-if="canBuy" to="/delivery-notes/new" class="btn-secondary">{{ t('note.readButton') }}</RouterLink>
        <RouterLink v-if="canBuy" to="/supplier-invoices/new" class="btn-primary">+ {{ t('bill.new') }}</RouterLink>
      </div>
    </div>

    <div v-if="entered" class="notice-ok animate-rise mt-6 flex flex-wrap items-center justify-between gap-2" role="status">
      <span>{{ entered }}</span>
      <RouterLink to="/inventory?tab=movements" class="font-medium underline">{{ t('bill.seeMovements') }}</RouterLink>
    </div>
    <p v-if="error" class="notice-error mt-4" role="alert">{{ error }}</p>

    <div class="card mt-6 overflow-x-auto" :aria-busy="loading">
      <div v-if="loading && !rows.length" class="space-y-2 p-4">
        <div v-for="n in 4" :key="n" class="skeleton h-10 rounded-xl" />
      </div>
      <table v-else class="w-full min-w-[600px] text-[14px]">
        <thead>
          <tr class="text-[12px] text-slate-500">
            <th class="px-4 py-3 text-start font-medium">{{ t('bill.col.invoice') }}</th>
            <th class="px-4 py-3 text-start font-medium">{{ t('po.col.supplier') }}</th>
            <th class="px-4 py-3 text-start font-medium">{{ t('bill.col.received') }}</th>
            <th class="px-4 py-3 text-start font-medium">{{ t('bill.col.order') }}</th>
            <th class="px-4 py-3 text-end font-medium">{{ t('po.col.total') }}</th>
          </tr>
        </thead>
        <tbody class="stagger">
          <tr v-for="row in rows" :key="row.receipt" class="border-t border-[var(--hairline)] hover:bg-[var(--row-hover)]">
            <td class="px-4 py-3">
              <span class="block font-medium text-slate-900" dir="auto">{{ row.bill_no || row.receipt }}</span>
              <span class="block text-[12px] text-slate-500">
                {{ row.invoice ? day(row.bill_date) : t('bill.noInvoice') }} · {{ row.receipt }}
              </span>
              <span class="mt-1 flex flex-wrap gap-x-3 text-[12px]">
                <a v-if="row.attachment" :href="deliveryNotesApi.downloadUrl(row.receipt)" class="text-brand-700 hover:underline">{{ t('note.file') }}</a>
                <button v-if="canBuy && !row.billed" type="button" class="font-medium text-brand-700 hover:underline" @click="openInvoice(row)">
                  {{ t('note.enterInvoice') }}
                </button>
              </span>
            </td>
            <td class="px-4 py-3 text-slate-900" dir="auto">{{ row.supplier_name }}</td>
            <td class="px-4 py-3 text-slate-600">
              {{ day(row.date) }} · {{ row.shop_name }}
              <span class="block text-[12px] text-slate-500">{{ t('bill.units', { units: formatQty(row.qty, locale) }) }} · {{ row.by }}</span>
            </td>
            <td class="px-4 py-3">
              <RouterLink v-for="o in row.orders" :key="o" :to="`/purchase-orders/${encodeURIComponent(o)}`" class="block text-brand-700 hover:underline">{{ o }}</RouterLink>
              <span v-if="!row.orders.length" class="text-slate-400">—</span>
            </td>
            <td class="px-4 py-3 text-end">
              <span class="block font-medium text-slate-900 tabular-nums">{{ formatMoney(row.total, row.currency, locale) }}</span>
              <span v-if="row.outstanding" class="block text-[12px] text-amber-600 tabular-nums">
                {{ t('bill.owed', { amount: formatMoney(row.outstanding, row.currency, locale) }) }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!loading && !rows.length" class="hint p-6 text-center">{{ t('bill.empty') }}</p>
    </div>

    <AppDialog v-if="invoicing" :title="t('note.invoiceTitle', { ref: invoicing.bill_no || invoicing.receipt })" @close="invoicing = null">
      <p class="text-[14px] text-slate-600">{{ t('note.invoiceText', { supplier: invoicing.supplier_name }) }}</p>
      <p v-if="billError" class="notice-error mt-3" role="alert">{{ billError }}</p>
      <label class="label mt-4" for="later-bill-no">{{ t('bill.number') }}</label>
      <input id="later-bill-no" v-model="billNo" maxlength="140" dir="auto" class="field text-[15px]" autofocus :placeholder="t('bill.numberPlaceholder')" @keydown.enter="saveInvoice" />
      <label class="label mt-3" for="later-bill-date">{{ t('bill.date') }}</label>
      <input id="later-bill-date" v-model="billDate" type="date" :max="inDays(0)" class="field text-[15px]" />
      <div class="mt-6 flex flex-wrap gap-2">
        <button type="button" class="btn-primary btn-lg" :disabled="!billNo.trim() || billBusy" @click="saveInvoice">
          {{ billBusy ? t('pos.saving') : t('note.saveInvoice') }}
        </button>
        <button type="button" class="btn-secondary btn-lg" @click="invoicing = null">{{ t('categories.cancel') }}</button>
      </div>
    </AppDialog>
  </div>
</template>
