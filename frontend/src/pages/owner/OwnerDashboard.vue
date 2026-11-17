<script setup lang="ts">
// Dashboard: every widget reads retail_management.api.dashboard.get_dashboard,
// which only returns the shops this user may see.
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import AreaChart from '@/components/charts/AreaChart.vue'
import ColumnChart from '@/components/charts/ColumnChart.vue'
import DonutChart from '@/components/charts/DonutChart.vue'
import { type Dashboard, dashboardApi, formatCompact, formatDay, type Range, RANGES, timeAgo } from '@/dashboard'
import { formatMoney } from '@/inventory'

const { t, locale } = useI18n()

const shop = ref('')
const data = ref<Dashboard | null>(null)
const loading = ref(true)
const error = ref('')

let requestId = 0
async function load() {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const result = await dashboardApi.get(shop.value)
    if (id === requestId) data.value = result
  } catch (err) {
    if (id === requestId) error.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    if (id === requestId) loading.value = false
  }
}
watch(shop, load)
onMounted(load)

const currency = computed(() => data.value?.currency ?? null)
const money = (value: number) => formatMoney(value, currency.value, locale.value)
const moneyShort = (value: number) => money(value).replace(/[.,]00(?=\D*$)/, '')
const number = (value: number) => new Intl.NumberFormat(locale.value, { maximumFractionDigits: 1 }).format(value)
const axis = (value: number) => formatCompact(value, locale.value)

/** "↗ 12.6%" / "↘ 8.4%" with its colour; nothing when there is no comparison. */
function trend(change: number | null | undefined) {
  if (change === null || change === undefined) return null
  return {
    text: `${change >= 0 ? '↗' : '↘'} ${Math.abs(change).toLocaleString(locale.value)}%`,
    cls: change >= 0 ? 'text-green-700 dark:text-green-400' : 'text-brand-ink',
  }
}

const hasShop = computed(() => !!data.value?.sales)
const noSalesYet = computed(
  () => hasShop.value && !data.value!.recent?.length && !data.value!.sales!.value && !data.value!.revenue!.value,
)

// Sales: receipts per day over 30 days.
const salesLine = computed(() =>
  (data.value?.sales?.series ?? []).map((point) => ({
    label: formatDay(point.date, locale.value, { day: 'numeric', month: 'short' }),
    value: point.value,
  })),
)
const salesPeak = computed(() => {
  const series = data.value?.sales?.series ?? []
  let best = -1
  series.forEach((p, i) => {
    if (p.value > 0 && (best < 0 || p.value >= series[best].value)) best = i
  })
  return best
})

// Revenue: this week against last week, Monday to Sunday.
const weekColumns = computed(() =>
  (data.value?.revenue?.week ?? []).map((day, i) => ({
    label: new Intl.DateTimeFormat(locale.value, { weekday: 'short' }).format(new Date(2024, 0, 1 + i)),
    values: [day.last, day.this] as [number, number],
  })),
)

// Income per day split into cost of goods and (estimated) profit.
const orderColumns = computed(() =>
  (data.value?.orders ?? []).map((day) => {
    const profit = Math.max(0, day.profit)
    return {
      label: formatDay(day.date, locale.value, { day: 'numeric', month: 'short' }),
      title: formatDay(day.date, locale.value, { weekday: 'long', day: 'numeric', month: 'long' }),
      values: [Math.max(0, day.income - profit), profit] as [number, number],
    }
  }),
)
const lastOrderDay = computed(() => (data.value?.orders?.length ?? 0) - 1)

// Category colours: the brand, deep brand, warm greys, the soft tone.
const CATEGORY_COLORS = [
  { color: 'var(--color-brand-600)' },
  { color: 'color-mix(in srgb, var(--brand) 45%, #3b2417)' },
  { color: 'color-mix(in srgb, var(--brand) 22%, #6b6b6b)' },
  { color: 'var(--color-brand-200)', dark: true },
  { color: 'var(--color-slate-400)', dark: true },
  { color: 'var(--color-slate-300)', dark: true },
]
const categoryRange = ref<Range>('monthly')
const hoursRange = ref<Range>('monthly')
const slices = computed(() =>
  (data.value?.categories?.[categoryRange.value] ?? []).map((row, i) => ({
    label: row.name ?? t('dash.other'),
    value: row.value,
    ...CATEGORY_COLORS[i % CATEGORY_COLORS.length],
  })),
)
const hours = computed(() => data.value?.hours?.[hoursRange.value] ?? [])
const maxHour = computed(() => Math.max(1, ...hours.value.map((h) => h.percent)))
</script>

<template>
  <div>
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-[22px] font-semibold tracking-tight text-slate-900">{{ t('nav.items.dashboard') }}</h1>
      <select
        v-if="data && data.shops.length > 1"
        v-model="shop"
        class="field w-auto rounded-xl bg-white py-2 text-[14px]"
        :aria-label="t('products.shop')"
      >
        <option value="">{{ t('products.allShops') }}</option>
        <option v-for="s in data.shops" :key="s.name" :value="s.name">{{ s.shop_name }}</option>
      </select>
    </div>

    <p v-if="error" class="notice-error mb-4" role="alert">{{ error }}</p>
    <p v-else-if="data && !hasShop" class="notice-warn">{{ t('dash.noShop') }}</p>
    <p v-else-if="noSalesYet" class="notice-info mb-4">{{ t('dash.noSalesYet') }}</p>

    <div
      v-if="!data || hasShop"
      class="grid grid-cols-1 gap-4 transition-opacity md:grid-cols-2 xl:grid-cols-12"
      :class="{ 'opacity-50': loading }"
      :aria-busy="loading"
    >
      <!-- Sales (receipts, 30 days) -->
      <article class="card p-5 xl:col-span-3">
        <div class="flex items-start justify-between">
          <h2 class="text-[15px] text-slate-700">{{ t('dash.sales') }}</h2>
          <svg viewBox="0 0 24 24" class="h-5 w-5 text-slate-500" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
            <path d="m4 16 5-5 4 4 7-7M15 8h5v5" />
          </svg>
        </div>
        <div class="mt-2 flex flex-wrap items-baseline gap-x-2">
          <span class="text-[28px] font-semibold tracking-tight text-slate-900 tabular-nums">{{ number(data?.sales?.value ?? 0) }}</span>
          <span v-if="trend(data?.sales?.change)" class="text-[13px] font-medium whitespace-nowrap" :class="trend(data?.sales?.change)!.cls">
            {{ trend(data?.sales?.change)!.text }}
          </span>
        </div>
        <p class="text-[13px] text-slate-500">{{ t('dash.previous30', { value: number(data?.sales?.previous ?? 0) }) }}</p>
        <div class="mt-2">
          <AreaChart :points="salesLine" :highlight="salesPeak" :format="number" :label="t('dash.sales')" />
        </div>
      </article>

      <!-- Customers (highlighted) -->
      <article class="accent-card p-5 xl:col-span-3">
        <div class="flex items-start justify-between">
          <h2 class="text-[15px] font-medium text-slate-900">{{ t('dash.customers') }}</h2>
          <svg viewBox="0 0 24 24" class="h-5 w-5 text-slate-700" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
            <circle cx="9" cy="8" r="3.5" /><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M16 4.5a3.5 3.5 0 0 1 0 7M18 14c2 .7 3 2.8 3 6" />
          </svg>
        </div>
        <div class="mt-3 grid grid-cols-2 divide-x divide-[var(--hairline)] rtl:divide-x-reverse">
          <div class="pe-3">
            <div class="text-[12px] text-slate-700">{{ t('dash.currentCustomers') }}</div>
            <div class="mt-1 flex flex-wrap items-baseline gap-x-1.5">
              <span class="text-[24px] font-semibold text-slate-900 tabular-nums">{{ number(data?.customers?.current ?? 0) }}</span>
              <span v-if="trend(data?.customers?.current_change)" class="text-[12px] font-medium whitespace-nowrap" :class="trend(data?.customers?.current_change)!.cls">
                {{ trend(data?.customers?.current_change)!.text }}
              </span>
            </div>
            <div class="text-[12px] text-slate-600">{{ t('dash.vsPrevious30') }}</div>
          </div>
          <div class="ps-3">
            <div class="text-[12px] text-slate-700">{{ t('dash.newCustomers') }}</div>
            <div class="mt-1 flex flex-wrap items-baseline gap-x-1.5">
              <span class="text-[24px] font-semibold text-slate-900 tabular-nums">{{ number(data?.customers?.new ?? 0) }}</span>
              <span v-if="trend(data?.customers?.new_change)" class="text-[12px] font-medium whitespace-nowrap" :class="trend(data?.customers?.new_change)!.cls">
                {{ trend(data?.customers?.new_change)!.text }}
              </span>
            </div>
            <div class="text-[12px] text-slate-600">{{ t('dash.vsLastMonth') }}</div>
          </div>
        </div>
        <div class="mt-4 border-t border-[var(--hairline)] pt-3 text-[13px] text-slate-700">{{ t('dash.byShop') }}</div>
        <div class="mt-2 grid gap-2.5" :class="(data?.customers?.by_shop.length ?? 0) > 1 ? 'grid-cols-2' : 'grid-cols-1'">
          <div v-for="part in data?.customers?.by_shop ?? []" :key="part.shop_name" class="rounded-xl p-3" style="background: var(--accent-inner)">
            <div class="text-[20px] font-semibold text-slate-900 tabular-nums">{{ part.percent }}%</div>
            <div class="truncate text-[12px] text-slate-600"><bdi>{{ part.shop_name }}</bdi></div>
            <div class="mt-2 flex flex-wrap items-baseline gap-x-1.5">
              <span class="text-[16px] font-semibold text-slate-900 tabular-nums">{{ number(part.sales) }}</span>
              <span v-if="trend(part.change)" class="text-[11px] font-medium whitespace-nowrap" :class="trend(part.change)!.cls">
                {{ trend(part.change)!.text }}
              </span>
            </div>
            <div class="text-[11px] text-slate-600">{{ t('dash.receipts30') }}</div>
          </div>
        </div>
      </article>

      <!-- Revenue -->
      <article class="card p-5 xl:col-span-3">
        <div class="flex items-start justify-between">
          <h2 class="text-[15px] text-slate-700">{{ t('dash.revenueMonth') }}</h2>
          <svg viewBox="0 0 24 24" class="h-5 w-5 text-slate-500" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true">
            <path d="M4 8h16v12H4zM8 8V5h8v3M16 14h.01" />
          </svg>
        </div>
        <div class="mt-2 flex flex-wrap items-baseline gap-x-2">
          <span class="text-[28px] font-semibold tracking-tight text-slate-900 tabular-nums">{{ moneyShort(data?.revenue?.value ?? 0) }}</span>
          <span v-if="trend(data?.revenue?.change)" class="text-[13px] font-medium whitespace-nowrap" :class="trend(data?.revenue?.change)!.cls">
            {{ trend(data?.revenue?.change)!.text }}
          </span>
        </div>
        <p class="text-[13px] text-slate-500">{{ t('dash.lastMonth', { value: moneyShort(data?.revenue?.last_month ?? 0) }) }}</p>
        <p class="mt-3 text-[13px] text-slate-700">{{ t('dash.revenueWeek') }}</p>
        <ColumnChart
          class="mt-1"
          mode="pair"
          :columns="weekColumns"
          :series="[t('dash.lastWeek'), t('dash.thisWeek')]"
          :format="moneyShort"
          :format-axis="axis"
          :label="t('dash.revenueWeek')"
          :height="150"
          :thickness="0.62"
        />
        <div class="mt-1 flex justify-center gap-4 text-[12px] text-slate-600">
          <span class="inline-flex items-center gap-1.5"><span class="h-2 w-2 rounded-full bg-brand-600" />{{ t('dash.thisWeek') }}</span>
          <span class="inline-flex items-center gap-1.5"><span class="h-2 w-2 rounded-full bg-brand-200" />{{ t('dash.lastWeek') }}</span>
        </div>
      </article>

      <!-- Top categories -->
      <article class="card p-5 xl:col-span-3">
        <h2 class="text-[15px] text-slate-700">{{ t('dash.topCategories') }}</h2>
        <div class="mt-2 grid min-h-[170px] place-items-center">
          <DonutChart v-if="slices.length" :slices="slices" :label="t('dash.topCategories')" :size="170" />
          <p v-else class="text-[13px] text-slate-500">{{ t('dash.nothingYet') }}</p>
        </div>
        <ul class="mt-3 flex flex-wrap justify-center gap-x-3 gap-y-1">
          <li v-for="s in slices" :key="s.label" class="inline-flex items-center gap-1.5 text-[12px] text-slate-600">
            <span class="h-2 w-2 rounded-full" :style="{ background: s.color }" /><bdi>{{ s.label }}</bdi>
          </li>
        </ul>
        <div class="mt-3 grid grid-cols-3 rounded-xl bg-slate-100 p-1" role="group" :aria-label="t('dash.range')">
          <button
            v-for="r in RANGES"
            :key="r"
            type="button"
            class="rounded-lg py-1.5 text-[13px] transition"
            :class="categoryRange === r ? 'bg-brand-tint font-medium text-brand-ink ring-1 ring-brand' : 'text-slate-600 hover:text-slate-900'"
            :aria-pressed="categoryRange === r"
            @click="categoryRange = r"
          >
            {{ t(`dash.ranges.${r}`) }}
          </button>
        </div>
      </article>

      <!-- Income and profit per day -->
      <article class="card p-5 md:col-span-2 xl:col-span-9">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 class="section-title text-[17px]">{{ t('dash.incomeProfit') }}</h2>
            <p class="hint mt-0.5">{{ t('dash.profitHint') }}</p>
          </div>
          <div class="flex items-center gap-4 text-[13px] text-slate-600">
            <span class="inline-flex items-center gap-1.5"><span class="h-2.5 w-2.5 rounded-full bg-brand-200" />{{ t('dash.cost') }}</span>
            <span class="inline-flex items-center gap-1.5"><span class="h-2.5 w-2.5 rounded-full bg-brand-600" />{{ t('dash.profit') }}</span>
          </div>
        </div>
        <ColumnChart
          class="mt-4"
          :columns="orderColumns"
          :series="[t('dash.cost'), t('dash.profit')]"
          :total-label="t('dash.income')"
          :format="moneyShort"
          :format-axis="axis"
          :label="t('dash.incomeProfit')"
          :height="260"
          :initial="lastOrderDay"
        />
      </article>

      <!-- Sales by time of day -->
      <article class="card p-5 xl:col-span-3">
        <h2 class="text-[15px] text-slate-700">{{ t('dash.hours') }}</h2>
        <ul class="mt-5 space-y-3.5">
          <li v-for="h in hours" :key="h.label" class="grid grid-cols-[3.5rem_1fr_2.5rem] items-center gap-3 text-[13px]">
            <span class="text-slate-600 tabular-nums" dir="ltr">{{ h.label }}</span>
            <span class="h-3.5 rounded-sm bg-slate-100">
              <span class="block h-full rounded-sm bg-brand-200" :style="{ width: `${(h.percent / maxHour) * 100}%` }" />
            </span>
            <span class="text-end font-medium text-slate-900 tabular-nums">{{ h.percent }}%</span>
          </li>
        </ul>
        <div class="mt-5 grid grid-cols-3 rounded-xl bg-slate-100 p-1" role="group" :aria-label="t('dash.range')">
          <button
            v-for="r in RANGES"
            :key="r"
            type="button"
            class="rounded-lg py-1.5 text-[13px] transition"
            :class="hoursRange === r ? 'bg-brand-tint font-medium text-brand-ink ring-1 ring-brand' : 'text-slate-600 hover:text-slate-900'"
            :aria-pressed="hoursRange === r"
            @click="hoursRange = r"
          >
            {{ t(`dash.ranges.${r}`) }}
          </button>
        </div>
      </article>

      <!-- Best sellers -->
      <article class="card p-5 md:col-span-2 xl:col-span-7">
        <div class="flex items-center justify-between">
          <h2 class="section-title text-[17px]">{{ t('dash.productSales') }}</h2>
          <span class="hint">{{ t('dash.last30') }}</span>
        </div>
        <p v-if="!data?.products?.length" class="mt-4 text-[14px] text-slate-500">{{ t('dash.nothingYet') }}</p>
        <div v-else class="-mx-2 mt-3 overflow-x-auto">
          <table class="w-full min-w-[460px] text-[13px]">
            <thead>
              <tr class="text-[12px] text-slate-500">
                <th class="px-1.5 py-2 text-start font-normal">{{ t('dash.col.item') }}</th>
                <th class="px-1.5 py-2 text-end font-normal">{{ t('dash.col.stock') }}</th>
                <th class="px-1.5 py-2 text-end font-normal">{{ t('dash.col.listPrice') }}</th>
                <th class="px-1.5 py-2 text-end font-normal">{{ t('dash.col.sale') }}</th>
                <th class="px-1.5 py-2 text-end font-normal">{{ t('dash.col.avgPrice') }}</th>
                <th class="px-1.5 py-2 text-end font-normal">{{ t('dash.col.sold') }}</th>
                <th class="w-8"><span class="sr-only">{{ t('dash.col.open') }}</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in data.products" :key="p.item_code" class="border-t border-[var(--hairline)]">
                <td class="px-1.5 py-3">
                  <span class="flex items-center gap-3">
                    <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-500" aria-hidden="true">
                      <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round">
                        <path d="M12 3 4 7v10l8 4 8-4V7l-8-4Z" /><path d="m4 7 8 4 8-4M12 11v10" />
                      </svg>
                    </span>
                    <span class="font-medium text-slate-900" dir="auto">{{ p.name }}</span>
                  </span>
                </td>
                <td class="px-1.5 py-3 text-end text-slate-700 tabular-nums">{{ number(p.stock) }}</td>
                <td class="px-1.5 py-3 text-end tabular-nums" :class="p.discount > 0 ? 'text-slate-500 line-through' : 'text-slate-700'">
                  {{ money(p.list_price) }}
                </td>
                <td class="px-1.5 py-3 text-end font-medium tabular-nums" :class="p.discount > 0 ? 'text-green-700 dark:text-green-400' : 'text-slate-400'">
                  {{ p.discount > 0 ? `${p.discount.toLocaleString(locale)}%` : '—' }}
                </td>
                <td class="px-1.5 py-3 text-end font-medium text-slate-900 tabular-nums">{{ money(p.price) }}</td>
                <td class="px-1.5 py-3 text-end text-slate-700 tabular-nums">{{ number(p.sold) }}</td>
                <td class="px-1 py-3 text-center">
                  <RouterLink
                    :to="`/products/${encodeURIComponent(p.item_code)}`"
                    class="icon-btn mx-auto"
                    :aria-label="t('dash.openProduct', { name: p.name })"
                  >
                    <svg viewBox="0 0 24 24" class="h-4 w-4 rtl:rotate-180" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true">
                      <path d="m9 6 6 6-6 6" />
                    </svg>
                  </RouterLink>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <!-- Latest sales -->
      <article class="card p-5 md:col-span-2 xl:col-span-5">
        <h2 class="section-title text-[17px]">{{ t('dash.recentOrders') }}</h2>
        <p v-if="!data?.recent?.length" class="mt-4 text-[14px] text-slate-500">{{ t('dash.nothingYet') }}</p>
        <ul v-else class="mt-3">
          <li v-for="o in data.recent" :key="o.name" class="flex items-center gap-3 border-t border-[var(--hairline)] py-3 first:border-0">
            <span class="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-brand-tint text-brand-ink" aria-hidden="true">
              <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round">
                <path d="M5 8h14l-1 12H6L5 8Z" /><path d="M9 8V6a3 3 0 0 1 6 0v2M10 13h4" />
              </svg>
            </span>
            <span class="min-w-0 flex-1 leading-tight">
              <span class="block truncate text-[14px] font-medium text-slate-900" dir="ltr">{{ o.name }}</span>
              <span class="block truncate text-[13px] text-slate-500"><bdi>{{ o.customer }}</bdi> · <bdi>{{ o.shop_name }}</bdi></span>
            </span>
            <span class="shrink-0 text-[14px] font-medium text-slate-900 tabular-nums">{{ money(o.amount) }}</span>
            <span class="shrink-0 text-end leading-tight">
              <span
                class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium"
                :class="o.is_return ? 'bg-red-500/12 text-red-700 dark:text-red-400' : 'bg-green-500/12 text-green-700 dark:text-green-400'"
              >
                <span class="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />{{ o.is_return ? t('dash.return') : t('dash.sale') }}
              </span>
              <span class="mt-1 block text-[11px] text-slate-500">{{ timeAgo(o.posted, locale) }}</span>
            </span>
          </li>
        </ul>
      </article>
    </div>
  </div>
</template>
