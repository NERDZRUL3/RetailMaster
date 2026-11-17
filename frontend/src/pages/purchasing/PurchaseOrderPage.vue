<script setup lang="ts">
// One purchase order: write a draft, place it, receive deliveries against it,
// print it for the supplier, cancel or close it.
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import { branding } from '@/branding'
import ProductPicker from '@/components/ProductPicker.vue'
import { formatDay } from '@/dashboard'
import { formatMoney, formatQty, type Product } from '@/inventory'
import { inDays, type Order, type OrderDraft, type OrderLine, purchasingApi, STATUS_BADGE, type Supplier } from '@/purchasing'
import { newRequestId } from '@/receiving'
import { session } from '@/session'

const props = defineProps<{ name?: string }>()
const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

const shops = computed(() => session.context?.shops ?? [])
const canBuy = computed(() => !!session.context?.can_buy)
const order = ref<Order | null>(null)
const suppliers = ref<Supplier[]>([])
const draft = ref<OrderDraft>({
  supplier: typeof route.query.supplier === 'string' ? route.query.supplier : '',
  shop: shops.value[0]?.name ?? '',
  expected: inDays(7),
  notes: '',
  lines: [],
})
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const info = ref('')
let requestId = newRequestId()

const editing = computed(() => canBuy.value && (!order.value || order.value.status === 'draft'))
const currency = computed(() => order.value?.currency ?? null)
const money = (value: number) => formatMoney(value, currency.value, locale.value)
const qty = (value: number) => formatQty(value, locale.value)
const day = (iso: string | null) => (iso ? formatDay(iso, locale.value, { day: 'numeric', month: 'long', year: 'numeric' }) : '—')
const fail = (err: unknown) => (error.value = err instanceof ApiError ? err.message : String(err))

const draftTotal = computed(() => draft.value.lines.reduce((sum, l) => sum + (Number(l.qty) || 0) * (Number(l.rate) || 0), 0))
const draftValid = computed(
  () =>
    !!draft.value.supplier &&
    !!draft.value.shop &&
    draft.value.lines.length > 0 &&
    draft.value.lines.every((l) => Number(l.qty) > 0 && Number(l.rate) >= 0),
)

function fromOrder(o: Order) {
  order.value = o
  draft.value = {
    name: o.name,
    supplier: o.supplier,
    shop: o.shop ?? '',
    expected: o.expected ?? inDays(7),
    notes: o.notes,
    lines: o.lines.map((l) => ({ item_code: l.item_code, item_name: l.item_name, qty: l.qty, rate: l.rate })),
  }
  receiveQty.value = Object.fromEntries(o.lines.map((l) => [l.row, l.remaining]))
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [list] = await Promise.all([
      canBuy.value ? purchasingApi.suppliers() : Promise.resolve([] as Supplier[]),
      props.name ? purchasingApi.order(props.name).then(fromOrder) : Promise.resolve(),
    ])
    suppliers.value = list.filter((s) => !s.disabled || s.name === draft.value.supplier)
  } catch (err) {
    fail(err)
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(
  () => props.name,
  (name, old) => {
    if (name !== old) load()
  },
)

async function addProduct(product: Product) {
  info.value = ''
  const existing = draft.value.lines.find((l) => l.item_code === product.item_code)
  if (existing) {
    existing.qty = (Number(existing.qty) || 0) + 1
    return
  }
  const line: OrderLine = { item_code: product.item_code, item_name: product.item_name, qty: 1, rate: '' }
  draft.value.lines.unshift(line)
  try {
    const costs = await purchasingApi.costs([product.item_code], draft.value.supplier)
    const found = draft.value.lines.find((l) => l.item_code === product.item_code)
    if (found && found.rate === '' && costs[product.item_code]) found.rate = costs[product.item_code]
  } catch {
    // the cost is only a suggestion
  }
}

async function saveDraft(place: boolean) {
  if (!draftValid.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const saved = await purchasingApi.save(draft.value, place, requestId)
    requestId = newRequestId()
    fromOrder(saved)
    info.value = place ? t('po.placed', { name: saved.name }) : t('po.saved')
    if (!props.name) router.replace(`/purchase-orders/${encodeURIComponent(saved.name)}`)
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

async function act(kind: 'submit' | 'cancel' | 'close' | 'remove') {
  if (!order.value || busy.value) return
  const confirmKey = { submit: '', cancel: 'po.confirmCancel', close: 'po.confirmClose', remove: 'po.confirmDelete' }[kind]
  if (confirmKey && !window.confirm(t(confirmKey))) return
  busy.value = true
  error.value = ''
  try {
    if (kind === 'remove') {
      await purchasingApi.remove(order.value.name)
      router.push('/purchase-orders')
      return
    }
    fromOrder(await purchasingApi[kind](order.value.name))
    info.value = t(`po.done.${kind}`)
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

// Receiving a delivery
const receiving = ref(false)
const receiveQty = ref<Record<string, number | ''>>({})
const receiveRef = ref('')
let receiveRequest = newRequestId()
const canReceive = computed(() => canBuy.value && ['ordered', 'partly_received'].includes(order.value?.status ?? ''))
const receiveUnits = computed(() => Object.values(receiveQty.value).reduce<number>((sum, v) => sum + (Number(v) || 0), 0))
const receiveValid = computed(
  () =>
    receiveUnits.value > 0 &&
    (order.value?.lines ?? []).every((l) => {
      const v = Number(receiveQty.value[l.row]) || 0
      return v >= 0 && v <= l.remaining
    }),
)
async function receive() {
  if (!order.value || !receiveValid.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const lines = Object.entries(receiveQty.value)
      .map(([row, v]) => ({ row, qty: Number(v) || 0 }))
      .filter((l) => l.qty > 0)
    const units = receiveUnits.value
    fromOrder(await purchasingApi.receive(order.value.name, lines, receiveRef.value, receiveRequest))
    receiveRequest = newRequestId()
    receiveRef.value = ''
    receiving.value = false
    info.value = t('po.receivedDone', { units: qty(units), shop: order.value?.shop_name ?? '' })
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

function print() {
  window.print()
}
const supplierRow = computed(() => suppliers.value.find((s) => s.name === order.value?.supplier))
</script>

<template>
  <div class="mx-auto max-w-5xl">
    <RouterLink to="/purchase-orders" class="btn-quiet -ms-3 px-3 py-1.5 text-[14px]">← {{ t('po.title') }}</RouterLink>

    <div class="mt-2 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="page-title">{{ order ? order.name : t('po.new') }}</h1>
        <p v-if="order" class="page-subtitle">
          <span :class="STATUS_BADGE[order.status]">{{ t(`po.status.${order.status}`) }}</span>
          <span class="ms-2">{{ order.supplier_name }} · {{ order.shop_name }}</span>
        </p>
      </div>
      <div v-if="order && !editing" class="flex flex-wrap gap-2">
        <button v-if="canReceive" type="button" class="btn-primary" @click="receiving = !receiving">{{ t('po.receive') }}</button>
        <button type="button" class="btn-secondary" @click="print">{{ t('po.print') }}</button>
        <button v-if="canBuy && order.status === 'ordered'" type="button" class="btn-quiet text-red-600" :disabled="busy" @click="act('cancel')">{{ t('po.cancel') }}</button>
        <button v-if="canBuy && order.status === 'partly_received'" type="button" class="btn-quiet" :disabled="busy" @click="act('close')">{{ t('po.close') }}</button>
      </div>
    </div>

    <p v-if="error" class="notice-error mt-6" role="alert">{{ error }}</p>
    <p v-if="info" class="notice-ok mt-6" role="status">{{ info }}</p>

    <!-- Write or change a draft -->
    <template v-if="editing && !loading">
      <section class="card-pad mt-6 grid gap-4 sm:grid-cols-2">
        <div>
          <label class="label" for="po-supplier">{{ t('po.supplier') }}</label>
          <select id="po-supplier" v-model="draft.supplier" class="field text-[15px]">
            <option value="" disabled>{{ t('po.chooseSupplier') }}</option>
            <option v-for="s in suppliers" :key="s.name" :value="s.name">{{ s.supplier_name }}</option>
          </select>
          <RouterLink to="/suppliers" class="hint mt-1 inline-block hover:underline">{{ t('po.manageSuppliers') }}</RouterLink>
        </div>
        <div>
          <label class="label" for="po-shop">{{ t('po.deliverTo') }}</label>
          <select id="po-shop" v-model="draft.shop" class="field text-[15px]">
            <option v-for="s in shops" :key="s.name" :value="s.name">{{ s.shop_name }}</option>
          </select>
        </div>
        <div>
          <label class="label" for="po-expected">{{ t('po.expected') }}</label>
          <input id="po-expected" v-model="draft.expected" type="date" :min="inDays(0)" class="field text-[15px]" />
        </div>
        <div>
          <label class="label" for="po-notes">{{ t('po.notes') }}</label>
          <input id="po-notes" v-model="draft.notes" maxlength="1000" dir="auto" class="field text-[15px]" :placeholder="t('po.notesPlaceholder')" />
        </div>
        <div class="sm:col-span-2">
          <ProductPicker :shop="draft.shop" input-id="po-scan" :label="t('po.addProducts')" @pick="addProduct" />
        </div>
      </section>

      <section class="card-pad mt-6">
        <p v-if="!draft.lines.length" class="hint">{{ t('po.noLines') }}</p>
        <div v-else class="-mx-2 overflow-x-auto">
          <table class="w-full min-w-[560px] text-[14px]">
            <thead>
              <tr class="text-[12px] text-slate-500">
                <th class="px-2 py-2 text-start font-medium">{{ t('po.col.product') }}</th>
                <th class="px-2 py-2 text-center font-medium">{{ t('po.col.qty') }}</th>
                <th class="px-2 py-2 text-end font-medium">{{ t('po.col.cost') }}</th>
                <th class="px-2 py-2 text-end font-medium">{{ t('po.col.amount') }}</th>
                <th class="w-10"><span class="sr-only">{{ t('stock.removeLine', { name: '' }) }}</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="line in draft.lines" :key="line.item_code" class="border-t border-[var(--hairline)]">
                <td class="px-2 py-2.5 font-medium text-slate-900" dir="auto">{{ line.item_name }}</td>
                <td class="px-2 py-2.5 text-center">
                  <input v-model.number="line.qty" type="number" min="1" step="any" class="field mx-auto w-20 px-2 py-2 text-center tabular-nums" :aria-label="t('stock.qtyFor', { name: line.item_name })" />
                </td>
                <td class="px-2 py-2.5 text-end">
                  <input v-model.number="line.rate" type="number" min="0" step="0.01" class="field ms-auto w-28 px-3 py-2 text-end tabular-nums" :aria-label="t('po.costFor', { name: line.item_name })" />
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
          <span class="text-[15px] text-slate-500">{{ t('po.total') }}</span>
          <span class="text-[26px] font-semibold text-slate-900 tabular-nums">{{ money(draftTotal) }}</span>
        </div>
        <div class="mt-5 flex flex-wrap gap-2">
          <button type="button" class="btn-primary btn-lg" :disabled="!draftValid || busy" @click="saveDraft(true)">{{ t('po.place') }}</button>
          <button type="button" class="btn-secondary btn-lg" :disabled="!draftValid || busy" @click="saveDraft(false)">{{ t('po.saveDraft') }}</button>
          <button v-if="order" type="button" class="btn-quiet btn-lg text-red-600" :disabled="busy" @click="act('remove')">{{ t('po.delete') }}</button>
        </div>
        <p class="hint mt-3">{{ t('po.placeHint') }}</p>
      </section>
    </template>

    <!-- A placed order -->
    <template v-else-if="order">
      <section class="mt-6 grid gap-3 sm:grid-cols-4">
        <div class="card p-4">
          <div class="text-[13px] text-slate-500">{{ t('po.ordered') }}</div>
          <div class="mt-1 font-medium text-slate-900">{{ day(order.date) }}</div>
        </div>
        <div class="card p-4">
          <div class="text-[13px] text-slate-500">{{ t('po.expected') }}</div>
          <div class="mt-1 font-medium text-slate-900">{{ day(order.expected) }}</div>
        </div>
        <div class="card p-4">
          <div class="text-[13px] text-slate-500">{{ t('po.received') }}</div>
          <div class="mt-1 font-medium text-slate-900">{{ Math.round(order.per_received) }} %</div>
          <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div class="h-full rounded-full bg-brand-600" :style="{ width: `${Math.min(order.per_received, 100)}%` }" />
          </div>
        </div>
        <div class="card p-4">
          <div class="text-[13px] text-slate-500">{{ t('po.total') }}</div>
          <div class="mt-1 text-[20px] font-semibold text-slate-900 tabular-nums">{{ money(order.total) }}</div>
        </div>
      </section>

      <!-- Receive a delivery -->
      <section v-if="receiving && canReceive" class="card-pad mt-6 ring-2 ring-brand-200">
        <h2 class="text-[18px] font-semibold text-slate-900">{{ t('po.receiveTitle') }}</h2>
        <p class="hint mt-1">{{ t('po.receiveHint', { shop: order.shop_name }) }}</p>
        <ul class="mt-4 space-y-2">
          <li v-for="line in order.lines.filter((l) => l.remaining > 0)" :key="line.row" class="flex flex-wrap items-center gap-3 border-b border-[var(--hairline)] pb-2">
            <span class="min-w-0 flex-1">
              <span class="block font-medium text-slate-900" dir="auto">{{ line.item_name }}</span>
              <span class="block text-[12px] text-slate-500">{{ t('po.stillExpected', { qty: qty(line.remaining) }) }}</span>
            </span>
            <input
              v-model.number="receiveQty[line.row]"
              type="number"
              min="0"
              :max="line.remaining"
              step="any"
              class="field w-24 py-2 text-center tabular-nums"
              :class="Number(receiveQty[line.row]) > line.remaining ? 'ring-2 ring-red-500' : ''"
              :aria-label="t('stock.qtyFor', { name: line.item_name })"
            />
          </li>
        </ul>
        <label class="label mt-4" for="po-receive-ref">{{ t('po.deliveryNote') }}</label>
        <input id="po-receive-ref" v-model="receiveRef" maxlength="140" class="field text-[15px]" :placeholder="t('po.deliveryNotePlaceholder')" />
        <div class="mt-5 flex flex-wrap gap-2">
          <button type="button" class="btn-primary btn-lg" :disabled="!receiveValid || busy" @click="receive">
            {{ busy ? t('pos.saving') : t('po.receiveConfirm', { units: qty(receiveUnits) }) }}
          </button>
          <button type="button" class="btn-secondary btn-lg" @click="receiving = false">{{ t('categories.cancel') }}</button>
        </div>
      </section>

      <section class="card mt-6 overflow-x-auto">
        <table class="w-full min-w-[620px] text-[14px]">
          <thead>
            <tr class="text-[12px] text-slate-500">
              <th class="px-4 py-3 text-start font-medium">{{ t('po.col.product') }}</th>
              <th class="px-4 py-3 text-end font-medium">{{ t('po.col.ordered') }}</th>
              <th class="px-4 py-3 text-end font-medium">{{ t('po.col.received') }}</th>
              <th class="px-4 py-3 text-end font-medium">{{ t('po.col.cost') }}</th>
              <th class="px-4 py-3 text-end font-medium">{{ t('po.col.amount') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="line in order.lines" :key="line.row" class="border-t border-[var(--hairline)]">
              <td class="px-4 py-3 font-medium text-slate-900" dir="auto">{{ line.item_name }}</td>
              <td class="px-4 py-3 text-end tabular-nums">{{ qty(line.qty) }}</td>
              <td class="px-4 py-3 text-end tabular-nums" :class="line.remaining > 0 ? 'text-amber-600' : 'text-green-700'">{{ qty(line.received) }}</td>
              <td class="px-4 py-3 text-end text-slate-600 tabular-nums">{{ money(line.rate) }}</td>
              <td class="px-4 py-3 text-end font-medium tabular-nums">{{ money(line.amount) }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <p v-if="order.notes" class="card mt-6 p-4 text-[14px] text-slate-700" dir="auto">{{ order.notes }}</p>

      <div v-if="order.receipts.length" class="mt-6">
        <h2 class="label">{{ t('po.deliveries') }}</h2>
        <ul class="list">
          <li v-for="r in order.receipts" :key="r.name" class="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-[14px]">
            <span class="text-slate-500">{{ day(r.date) }}</span>
            <span class="min-w-0 flex-1 text-slate-900">{{ r.reference || r.name }}</span>
            <span class="text-[12px] text-slate-500">{{ r.name }} · {{ r.by }}</span>
          </li>
        </ul>
      </div>

      <!-- Printout for the supplier (A4) -->
      <Teleport to="body">
        <div class="print-area print-a4" dir="auto">
          <div class="a4-head">
            <div>
              <div class="a4-brand">{{ branding.app_name }}</div>
              <div>{{ order.company }}</div>
              <div>{{ t('po.deliverTo') }}: {{ order.shop_name }}</div>
            </div>
            <div class="a4-meta">
              <div class="a4-title">{{ t('po.printTitle') }}</div>
              <div>{{ order.name }}</div>
              <div>{{ t('po.ordered') }}: {{ day(order.date) }}</div>
              <div>{{ t('po.expected') }}: {{ day(order.expected) }}</div>
            </div>
          </div>
          <div class="a4-to">
            <div class="a4-label">{{ t('po.supplier') }}</div>
            <div class="a4-strong">{{ order.supplier_name }}</div>
            <div v-if="supplierRow?.phone">{{ supplierRow.phone }}</div>
            <div v-if="supplierRow?.email">{{ supplierRow.email }}</div>
          </div>
          <table class="a4-table">
            <thead>
              <tr>
                <th>{{ t('po.col.product') }}</th>
                <th class="a4-num">{{ t('po.col.qty') }}</th>
                <th class="a4-num">{{ t('po.col.cost') }}</th>
                <th class="a4-num">{{ t('po.col.amount') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="line in order.lines" :key="line.row">
                <td>{{ line.item_name }}<div class="a4-code">{{ line.item_code }}</div></td>
                <td class="a4-num">{{ qty(line.qty) }} {{ line.uom }}</td>
                <td class="a4-num">{{ money(line.rate) }}</td>
                <td class="a4-num">{{ money(line.amount) }}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td colspan="3" class="a4-num a4-strong">{{ t('po.total') }}</td>
                <td class="a4-num a4-strong">{{ money(order.total) }}</td>
              </tr>
            </tfoot>
          </table>
          <p v-if="order.notes" class="a4-notes">{{ order.notes }}</p>
        </div>
      </Teleport>
    </template>
  </div>
</template>
