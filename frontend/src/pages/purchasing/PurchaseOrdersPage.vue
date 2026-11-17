<script setup lang="ts">
// Purchase orders: drafts, orders waiting for goods, received, cancelled.
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import { formatDay } from '@/dashboard'
import { formatMoney } from '@/inventory'
import { type OrderRow, purchasingApi, STATUS_BADGE } from '@/purchasing'
import { session } from '@/session'

const STATUSES = ['', 'draft', 'open', 'received', 'cancelled'] as const
type Filter = (typeof STATUSES)[number]

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const shops = computed(() => session.context?.shops ?? [])
const canBuy = computed(() => !!session.context?.can_buy)

const status = ref<Filter>(STATUSES.includes(route.query.status as Filter) ? (route.query.status as Filter) : '')
const query = ref(typeof route.query.q === 'string' ? route.query.q : '')
const shop = ref('')
const rows = ref<OrderRow[]>([])
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = await purchasingApi.orders(shop.value, status.value, query.value.trim())
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    loading.value = false
  }
}
let timer: ReturnType<typeof setTimeout> | undefined
watch(query, () => {
  clearTimeout(timer)
  timer = setTimeout(load, 250)
})
watch([status, shop], () => {
  router.replace({ query: { ...(status.value ? { status: status.value } : {}), ...(query.value ? { q: query.value } : {}) } })
  load()
})
onMounted(load)

const day = (iso: string | null) => (iso ? formatDay(iso, locale.value, { day: 'numeric', month: 'short', year: 'numeric' }) : '—')
</script>

<template>
  <div class="mx-auto max-w-6xl">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="page-title">{{ t('po.title') }}</h1>
        <p class="page-subtitle">{{ t('po.subtitle') }}</p>
      </div>
      <RouterLink v-if="canBuy" to="/purchase-orders/new" class="btn-primary">+ {{ t('po.new') }}</RouterLink>
    </div>

    <div class="card mt-6 p-3">
      <div class="flex flex-wrap items-center gap-2">
        <input v-model="query" type="search" dir="auto" class="field min-w-0 flex-1 py-2.5 text-[15px]" :placeholder="t('po.search')" :aria-label="t('po.search')" />
        <select v-if="shops.length > 1" v-model="shop" class="field w-auto py-2.5 text-[15px]" :aria-label="t('stock.shop')">
          <option value="">{{ t('stock.allShops') }}</option>
          <option v-for="s in shops" :key="s.name" :value="s.name">{{ s.shop_name }}</option>
        </select>
        <div class="max-w-full overflow-x-auto">
          <div class="segmented" role="group" :aria-label="t('po.statusFilter')">
            <button v-for="s in STATUSES" :key="s" type="button" class="segment whitespace-nowrap" :aria-pressed="status === s" @click="status = s">
              {{ t(`po.filter.${s || 'all'}`) }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <p v-if="error" class="notice-error mt-4" role="alert">{{ error }}</p>

    <div class="card mt-4 overflow-x-auto" :aria-busy="loading">
      <table class="w-full min-w-[720px] text-[14px]">
        <thead>
          <tr class="text-[12px] text-slate-500">
            <th class="px-4 py-3 text-start font-medium">{{ t('po.col.order') }}</th>
            <th class="px-4 py-3 text-start font-medium">{{ t('po.col.supplier') }}</th>
            <th class="px-4 py-3 text-start font-medium">{{ t('po.col.expected') }}</th>
            <th class="px-4 py-3 text-start font-medium">{{ t('po.col.status') }}</th>
            <th class="px-4 py-3 text-end font-medium">{{ t('po.col.total') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.name"
            class="cursor-pointer border-t border-[var(--hairline)] hover:bg-[var(--row-hover)]"
            @click="router.push(`/purchase-orders/${encodeURIComponent(row.name)}`)"
          >
            <td class="px-4 py-3">
              <RouterLink :to="`/purchase-orders/${encodeURIComponent(row.name)}`" class="font-medium text-slate-900 hover:underline" @click.stop>{{ row.name }}</RouterLink>
              <span class="block text-[12px] text-slate-500">{{ day(row.date) }} · {{ row.shop_name }}</span>
            </td>
            <td class="px-4 py-3 text-slate-900" dir="auto">{{ row.supplier_name }}</td>
            <td class="px-4 py-3" :class="row.late ? 'font-medium text-red-600' : 'text-slate-600'">
              {{ day(row.expected) }}
              <span v-if="row.late" class="block text-[12px]">{{ t('po.late') }}</span>
            </td>
            <td class="px-4 py-3">
              <span :class="STATUS_BADGE[row.status]">{{ t(`po.status.${row.status}`) }}</span>
              <span v-if="row.status === 'partly_received'" class="block text-[12px] text-slate-500">{{ Math.round(row.per_received) }} %</span>
            </td>
            <td class="px-4 py-3 text-end font-medium text-slate-900 tabular-nums">{{ formatMoney(row.total, row.currency, locale) }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!loading && !rows.length" class="hint p-6 text-center">{{ t('po.empty') }}</p>
    </div>
  </div>
</template>
