<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import BarChart, { type Bar } from '@/components/BarChart.vue'
import {
  bucketLabel,
  bucketTitle,
  dashboardApi,
  formatCompact,
  formatDate,
  type KpiKey,
  type Overview,
  type Period,
  PERIODS,
} from '@/dashboard'
import { formatMoney } from '@/inventory'

const { t, locale } = useI18n()

const period = ref<Period>('7d')
const shop = ref('')
const data = ref<Overview | null>(null)
const loading = ref(false)
const error = ref('')

let requestId = 0
async function load() {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const result = await dashboardApi.overview(period.value, shop.value)
    if (id === requestId) data.value = result
  } catch (err) {
    if (id === requestId) error.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    if (id === requestId) loading.value = false
  }
}
watch([period, shop], load)
onMounted(load)

const money = (value: number) => formatMoney(value, data.value?.currency ?? null, locale.value)
const count = (value: number) => new Intl.NumberFormat(locale.value).format(value)
const axis = (value: number) => formatCompact(value, locale.value)

// Shop colours for the split chart: the brand, then neutrals.
const SHOP_COLORS = ['var(--color-brand-600)', 'var(--color-slate-900)', 'var(--color-slate-400)', 'var(--color-brand-100)']

interface KpiCard {
  key: KpiKey
  label: string
  format: (value: number) => string
  /** For returns, going up is bad news. */
  upIsBad?: boolean
}
const cards = computed<KpiCard[]>(() => [
  { key: 'revenue', label: t('overview.kpi.revenue'), format: money },
  { key: 'sales', label: t('overview.kpi.sales'), format: count },
  { key: 'average', label: t('overview.kpi.average'), format: money },
  { key: 'returns', label: t('overview.kpi.returns'), format: count, upIsBad: true },
])

const revenueBars = computed<Bar[]>(() =>
  (data.value?.series ?? []).map((bucket) => ({
    key: bucket.key,
    label: bucketLabel(bucket.key, period.value, locale.value),
    title: bucketTitle(bucket.key, data.value!.monthly, locale.value),
    segments: [{ value: bucket.total, color: 'var(--color-brand-600)' }],
  })),
)
const shopBars = computed<Bar[]>(() =>
  (data.value?.series ?? []).map((bucket) => ({
    key: bucket.key,
    label: bucketLabel(bucket.key, period.value, locale.value),
    title: bucketTitle(bucket.key, data.value!.monthly, locale.value),
    segments: (data.value?.shops ?? []).map((s, i) => ({
      value: bucket.by_shop[s.name] ?? 0,
      color: SHOP_COLORS[i % SHOP_COLORS.length],
      name: s.shop_name,
    })),
  })),
)
const labelEvery = computed(() => (period.value === '30d' ? 5 : 1))

const range = computed(() =>
  data.value ? `${formatDate(data.value.start, locale.value)} – ${formatDate(data.value.end, locale.value)}` : '',
)
const splitByShop = computed(() => (data.value?.shops.length ?? 0) > 1)
const hasSales = computed(() => (data.value?.series ?? []).some((bucket) => bucket.total !== 0))
</script>

<template>
  <div>
    <!-- Heading, shop and period -->
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="page-title">{{ t('overview.title') }}</h1>
        <p class="page-subtitle">{{ range || t('overview.subtitle') }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <select
          v-if="data && data.shops.length > 1"
          v-model="shop"
          class="field w-auto rounded-full bg-white py-2.5 text-[15px] shadow-sm"
          :aria-label="t('products.shop')"
        >
          <option value="">{{ t('products.allShops') }}</option>
          <option v-for="s in data.shops" :key="s.name" :value="s.name">{{ s.shop_name }}</option>
        </select>
        <div class="segmented bg-white shadow-sm" role="group" :aria-label="t('overview.period')">
          <button
            v-for="p in PERIODS"
            :key="p"
            type="button"
            class="segment h-9 px-4 text-[14px]"
            :aria-pressed="period === p"
            @click="period = p"
          >
            {{ t(`overview.periods.${p}`) }}
          </button>
        </div>
      </div>
    </div>

    <p v-if="error" class="notice-error mt-6" role="alert">{{ error }}</p>

    <div class="transition-opacity" :class="{ 'opacity-60': loading }" :aria-busy="loading">
      <!-- Key figures -->
      <section class="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <article v-for="card in cards" :key="card.key" class="card-pad">
          <div class="flex items-start justify-between gap-3">
            <h2 class="text-[15px] text-slate-500">{{ card.label }}</h2>
            <span class="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-slate-100 text-slate-700" aria-hidden="true">
              <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <template v-if="card.key === 'revenue'">
                  <circle cx="12" cy="12" r="8.5" /><path d="M14.5 9.2c-.5-.8-1.4-1.2-2.5-1.2-1.5 0-2.6.8-2.6 2s1 1.7 2.6 2c1.6.3 2.7.8 2.7 2s-1.2 2-2.7 2c-1.2 0-2.2-.5-2.7-1.3M12 6.5v1.5M12 16v1.5" />
                </template>
                <template v-else-if="card.key === 'sales'">
                  <path d="M3 4h2l2.4 11h10.2L20 7.5H6.2" /><circle cx="9" cy="19.5" r="1.3" /><circle cx="17" cy="19.5" r="1.3" />
                </template>
                <template v-else-if="card.key === 'average'">
                  <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" />
                </template>
                <template v-else>
                  <path d="M9 14 4 9l5-5" /><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11" />
                </template>
              </svg>
            </span>
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
            <span class="min-w-0 text-[clamp(24px,2.1vw,36px)] leading-none font-semibold tracking-tight break-words text-slate-900 tabular-nums">
              {{ data?.kpis[card.key] ? card.format(data.kpis[card.key]!.value) : '—' }}
            </span>
            <span
              v-if="data?.kpis[card.key]?.change != null"
              class="badge gap-0.5 tabular-nums"
              :class="
                (data.kpis[card.key]!.change! >= 0) !== !!card.upIsBad
                  ? 'bg-green-50 text-green-800'
                  : 'bg-red-50 text-red-800'
              "
            >
              <span aria-hidden="true">{{ data.kpis[card.key]!.change! >= 0 ? '↑' : '↓' }}</span>
              <span class="sr-only">{{ data.kpis[card.key]!.change! >= 0 ? t('overview.up') : t('overview.down') }}</span>
              {{ Math.abs(data.kpis[card.key]!.change!).toLocaleString(locale) }}%
            </span>
          </div>
          <p class="hint mt-4">
            {{ t('overview.previous') }}:
            <span class="font-medium text-slate-700 tabular-nums">
              {{ data?.kpis[card.key] ? card.format(data.kpis[card.key]!.previous) : '—' }}
            </span>
          </p>
        </article>
      </section>

      <p v-if="data && !hasSales && !loading" class="notice-info mt-6">{{ t('overview.noSales') }}</p>

      <!-- Charts -->
      <section class="mt-6 grid grid-cols-1 gap-6" :class="{ 'xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]': splitByShop }">
        <article class="card-pad">
          <div class="flex flex-wrap items-baseline justify-between gap-2">
            <h2 class="section-title">{{ t('overview.revenueChart') }}</h2>
            <span v-if="data?.kpis.revenue" class="text-[15px] font-semibold text-slate-900 tabular-nums">
              {{ money(data.kpis.revenue.value) }}
            </span>
          </div>
          <p class="hint mt-1">{{ t(`overview.revenueHint.${period}`) }}</p>
          <div class="mt-4">
            <BarChart
              :bars="revenueBars"
              :format-value="money"
              :format-axis="axis"
              :label-every="labelEvery"
              :label="t('overview.revenueChart')"
            />
          </div>
        </article>

        <!-- Only useful when there is more than one shop to compare. -->
        <article v-if="splitByShop" class="card-pad">
          <h2 class="section-title">{{ t('overview.byShopChart') }}</h2>
          <p class="hint mt-1">{{ t('overview.byShopHint') }}</p>
          <ul class="mt-3 flex flex-wrap gap-x-4 gap-y-1">
            <li v-for="(s, i) in data?.shops ?? []" :key="s.name" class="inline-flex items-center gap-2 text-[13px] text-slate-600">
              <span class="h-2.5 w-2.5 rounded-full" :style="{ backgroundColor: SHOP_COLORS[i % SHOP_COLORS.length] }" />
              <bdi>{{ s.shop_name }}</bdi>
            </li>
          </ul>
          <div class="mt-2">
            <BarChart
              :bars="shopBars"
              :format-value="money"
              :format-axis="axis"
              :striped="false"
              :height="260"
              :label-every="period === '7d' ? 1 : period === '12m' ? 2 : 6"
              :label="t('overview.byShopChart')"
            />
          </div>
        </article>
      </section>

      <!-- Latest sales -->
      <section class="card-pad mt-6">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h2 class="section-title">{{ t('overview.recent') }}</h2>
          <RouterLink v-if="data && data.low_stock" to="/products?low=1" class="badge-warn px-3 py-1 text-[13px]">
            {{ t('overview.lowStock', { count: data.low_stock }, data.low_stock) }}
          </RouterLink>
        </div>

        <p v-if="data && !data.recent.length" class="mt-4 text-[15px] text-slate-500">{{ t('overview.noRecent') }}</p>
        <div v-else class="-mx-2 mt-4 overflow-x-auto">
          <table class="w-full min-w-[640px] text-start text-[15px]">
            <thead>
              <tr class="text-[13px] text-slate-500">
                <th class="rounded-s-xl bg-slate-50 px-3 py-3 text-start font-medium">{{ t('overview.col.invoice') }}</th>
                <th class="bg-slate-50 px-3 py-3 text-start font-medium">{{ t('overview.col.date') }}</th>
                <th class="bg-slate-50 px-3 py-3 text-start font-medium">{{ t('overview.col.shop') }}</th>
                <th class="bg-slate-50 px-3 py-3 text-start font-medium">{{ t('overview.col.customer') }}</th>
                <th class="bg-slate-50 px-3 py-3 text-start font-medium">{{ t('overview.col.type') }}</th>
                <th class="bg-slate-50 px-3 py-3 text-end font-medium">{{ t('overview.col.items') }}</th>
                <th class="rounded-e-xl bg-slate-50 px-3 py-3 text-end font-medium">{{ t('overview.col.total') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in data?.recent ?? []" :key="row.name" class="border-b border-[var(--hairline)] last:border-0">
                <td class="px-3 py-4 font-medium text-slate-900" dir="ltr">{{ row.name }}</td>
                <td class="px-3 py-4 whitespace-nowrap text-slate-700">{{ formatDate(row.date, locale) }}</td>
                <td class="px-3 py-4 text-slate-700"><bdi>{{ row.shop_name }}</bdi></td>
                <td class="px-3 py-4 text-slate-700"><bdi>{{ row.customer }}</bdi></td>
                <td class="px-3 py-4">
                  <span :class="row.is_return ? 'badge bg-red-50 text-red-800' : 'badge bg-green-50 text-green-800'">
                    {{ row.is_return ? t('overview.return') : t('overview.sale') }}
                  </span>
                </td>
                <td class="px-3 py-4 text-end text-slate-700 tabular-nums">{{ count(Math.abs(row.items)) }}</td>
                <td class="px-3 py-4 text-end font-semibold text-slate-900 tabular-nums">{{ money(row.total) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>
