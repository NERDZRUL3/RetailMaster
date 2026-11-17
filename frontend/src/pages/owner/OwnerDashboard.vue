<script setup lang="ts">
// Dashboard layout. The figures are SAMPLE data from @/sample until each
// widget is connected to the API (retail_management.api.dashboard).
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import AreaChart from '@/components/charts/AreaChart.vue'
import ColumnChart from '@/components/charts/ColumnChart.vue'
import DonutChart from '@/components/charts/DonutChart.vue'
import { dashboardApi, formatCompact } from '@/dashboard'
import { formatMoney } from '@/inventory'
import { type OrderStatus, sample } from '@/sample'

const { t, locale } = useI18n()

const currency = ref<string | null>(null)
onMounted(async () => {
  try {
    currency.value = (await dashboardApi.counts()).currency
  } catch {
    currency.value = null
  }
})

const money = (value: number) => formatMoney(value, currency.value, locale.value)
const moneyShort = (value: number) =>
  formatMoney(value, currency.value, locale.value).replace(/[.,]00(?=\D*$)/, '')
const number = (value: number) => new Intl.NumberFormat(locale.value).format(value)
const percent = (value: number) => `${Math.abs(value).toLocaleString(locale.value)}%`
const axis = (value: number) => formatCompact(value, locale.value)

// Dates counted back from today, for the sample series.
const dayLabel = (daysAgo: number, options: Intl.DateTimeFormatOptions) => {
  const date = new Date()
  date.setDate(date.getDate() - daysAgo)
  return new Intl.DateTimeFormat(locale.value, options).format(date)
}

const ordersLine = computed(() =>
  sample.recentOrders.points.map((point, i, all) => ({
    label: dayLabel((all.length - 1 - i) * 3, { day: 'numeric', month: 'short' }),
    value: point.value,
  })),
)

const weekColumns = computed(() =>
  sample.revenue.week.map((pair, i) => {
    const date = new Date(2024, 0, 1 + i) // a Monday
    return {
      label: new Intl.DateTimeFormat(locale.value, { weekday: 'short' }).format(date),
      values: [pair[1], pair[0]] as [number, number],
    }
  }),
)

const orderColumns = computed(() =>
  sample.orders.map((pair, i, all) => ({
    label: dayLabel(all.length - 1 - i, { day: 'numeric', month: 'short' }),
    title: dayLabel(all.length - 1 - i, { day: 'numeric', month: 'long' }),
    values: [pair[0] - pair[1], pair[1]] as [number, number],
  })),
)

// Category colours: the brand, deep brand, warm greys, the soft tone.
const CATEGORY_COLORS = [
  { color: 'var(--color-brand-600)' },
  { color: 'color-mix(in srgb, var(--brand) 45%, #3b2417)' },
  { color: 'color-mix(in srgb, var(--brand) 22%, #6b6b6b)' },
  { color: 'var(--color-brand-200)', dark: true },
  { color: 'var(--color-slate-400)', dark: true },
  { color: 'var(--color-slate-300)', dark: true },
]
const slices = computed(() =>
  sample.categories.map((c, i) => ({ label: c.name, value: c.percent, ...CATEGORY_COLORS[i % CATEGORY_COLORS.length] })),
)

type Range = 'all' | 'weekly' | 'monthly'
const RANGES: Range[] = ['all', 'weekly', 'monthly']
const categoryRange = ref<Range>('monthly')
const hoursRange = ref<Range>('all')

const STATUS_STYLE: Record<OrderStatus, string> = {
  delivered: 'bg-green-500/12 text-green-700 dark:text-green-400',
  processing: 'bg-brand-tint text-brand-ink',
  shipped: 'bg-sky-500/12 text-sky-700 dark:text-sky-300',
  cancelled: 'bg-red-500/12 text-red-700 dark:text-red-400',
}
const ago = (hours: number) => new Intl.RelativeTimeFormat(locale.value, { numeric: 'auto' }).format(-hours, 'hour')

const maxHour = Math.max(...sample.hours.map((h) => h.percent))
</script>

<template>
  <div>
    <h1 class="sr-only">{{ t('nav.items.dashboard') }}</h1>
    <p class="mb-4 inline-flex items-center gap-2 rounded-full bg-amber-500/12 px-3 py-1 text-[12px] font-medium text-amber-800 dark:text-amber-300">
      <span class="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {{ t('dash.sample') }}
    </p>

    <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-12">
      <!-- Orders (line) -->
      <article class="card p-5 xl:col-span-3">
        <div class="flex items-start justify-between">
          <h2 class="text-[15px] text-slate-700">{{ t('dash.orders') }}</h2>
          <svg viewBox="0 0 24 24" class="h-5 w-5 text-slate-500" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
            <path d="m4 16 5-5 4 4 7-7M15 8h5v5" />
          </svg>
        </div>
        <div class="mt-2 flex items-baseline gap-2">
          <span class="text-[28px] font-semibold tracking-tight text-slate-900 tabular-nums">{{ moneyShort(sample.recentOrders.value) }}</span>
          <span class="text-[13px] font-medium text-brand-ink">↘ {{ percent(sample.recentOrders.change) }}</span>
        </div>
        <p class="text-[13px] text-slate-500">{{ t('dash.lastMonth', { value: moneyShort(sample.recentOrders.lastMonth) }) }}</p>
        <div class="mt-2">
          <AreaChart :points="ordersLine" :highlight="sample.recentOrders.highlight" :format="moneyShort" :label="t('dash.orders')" />
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
              <span class="text-[24px] font-semibold text-slate-900 tabular-nums">{{ number(sample.customers.current) }}</span>
              <span class="text-[12px] font-medium whitespace-nowrap text-green-700 dark:text-green-400">↗ {{ percent(sample.customers.currentChange) }}</span>
            </div>
            <div class="text-[12px] text-slate-600">{{ t('dash.vsLastMonth') }}</div>
          </div>
          <div class="ps-3">
            <div class="text-[12px] text-slate-700">{{ t('dash.newCustomers') }}</div>
            <div class="mt-1 flex flex-wrap items-baseline gap-x-1.5">
              <span class="text-[24px] font-semibold text-slate-900 tabular-nums">{{ number(sample.customers.fresh) }}</span>
              <span class="text-[12px] font-medium whitespace-nowrap text-green-700 dark:text-green-400">↗ {{ percent(sample.customers.freshChange) }}</span>
            </div>
            <div class="text-[12px] text-slate-600">{{ t('dash.vsLastMonth') }}</div>
          </div>
        </div>
        <div class="mt-4 border-t border-[var(--hairline)] pt-3 text-[13px] text-slate-700">{{ t('dash.byShop') }}</div>
        <div class="mt-2 grid grid-cols-2 gap-2.5">
          <div v-for="part in sample.customers.split" :key="part.label" class="rounded-xl p-3" style="background: var(--accent-inner)">
            <div class="text-[20px] font-semibold text-slate-900 tabular-nums">{{ part.percent }}%</div>
            <div class="text-[12px] text-slate-600">{{ part.label }}</div>
            <div class="mt-2 flex flex-wrap items-baseline gap-x-1.5">
              <span class="text-[16px] font-semibold text-slate-900 tabular-nums">{{ number(part.value) }}</span>
              <span class="text-[11px] font-medium whitespace-nowrap text-green-700 dark:text-green-400">↗ {{ percent(part.change) }}</span>
            </div>
            <div class="text-[11px] text-slate-600">{{ t('dash.vsLastMonth') }}</div>
          </div>
        </div>
      </article>

      <!-- Revenue (mini columns) -->
      <article class="card p-5 xl:col-span-3">
        <div class="flex items-start justify-between">
          <h2 class="text-[15px] text-slate-700">{{ t('dash.revenue') }}</h2>
          <svg viewBox="0 0 24 24" class="h-5 w-5 text-slate-500" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true">
            <path d="M4 8h16v12H4zM8 8V5h8v3M16 14h.01" />
          </svg>
        </div>
        <div class="mt-2 flex items-baseline gap-2">
          <span class="text-[28px] font-semibold tracking-tight text-slate-900 tabular-nums">{{ moneyShort(sample.revenue.value) }}</span>
          <span class="text-[13px] font-medium text-green-700 dark:text-green-400">↗ {{ percent(sample.revenue.change) }}</span>
        </div>
        <p class="text-[13px] text-slate-500">{{ t('dash.lastMonth', { value: moneyShort(sample.revenue.lastMonth) }) }}</p>
        <p class="mt-3 text-[13px] text-slate-700">{{ t('dash.revenueWeek') }}</p>
        <ColumnChart
          class="mt-1"
          :columns="weekColumns"
          :series="[t('dash.lastWeek'), t('dash.thisWeek')]"
          :format="moneyShort"
          :format-axis="axis"
          :label="t('dash.revenueWeek')"
          :height="150"
          :thickness="0.5"
        />
        <div class="mt-1 flex justify-center gap-4 text-[12px] text-slate-600">
          <span class="inline-flex items-center gap-1.5"><span class="h-2 w-2 rounded-full bg-brand-600" />{{ t('dash.thisWeek') }}</span>
          <span class="inline-flex items-center gap-1.5"><span class="h-2 w-2 rounded-full bg-brand-200" />{{ t('dash.lastWeek') }}</span>
        </div>
      </article>

      <!-- Top categories (donut) -->
      <article class="card p-5 xl:col-span-3">
        <div class="flex items-start justify-between">
          <h2 class="text-[15px] text-slate-700">{{ t('dash.topCategories') }}</h2>
          <button type="button" disabled class="icon-btn -me-1.5 -mt-1.5" :title="t('dash.filtersSoon')" :aria-label="t('dash.filtersSoon')">
            <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
              <path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" />
            </svg>
          </button>
        </div>
        <div class="mt-2">
          <DonutChart :slices="slices" :label="t('dash.topCategories')" :size="170" />
        </div>
        <ul class="mt-3 flex flex-wrap justify-center gap-x-3 gap-y-1">
          <li v-for="s in slices" :key="s.label" class="inline-flex items-center gap-1.5 text-[12px] text-slate-600">
            <span class="h-2 w-2 rounded-full" :style="{ background: s.color }" />{{ s.label }}
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

      <!-- Orders per day (stacked columns) -->
      <article class="card p-5 md:col-span-2 xl:col-span-9">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h2 class="section-title text-[17px]">{{ t('dash.totalOrders') }}</h2>
          <div class="flex items-center gap-4 text-[13px] text-slate-600">
            <span class="inline-flex items-center gap-1.5"><span class="h-2.5 w-2.5 rounded-full bg-brand-200" />{{ t('dash.income') }}</span>
            <span class="inline-flex items-center gap-1.5"><span class="h-2.5 w-2.5 rounded-full bg-brand-600" />{{ t('dash.profit') }}</span>
            <button type="button" disabled class="icon-btn" :title="t('dash.filtersSoon')" :aria-label="t('dash.filtersSoon')">
              <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
                <path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" />
              </svg>
            </button>
          </div>
        </div>
        <ColumnChart
          class="mt-4"
          :columns="orderColumns"
          :series="[t('dash.income'), t('dash.profit')]"
          :total-label="t('dash.total')"
          :format="moneyShort"
          :format-axis="axis"
          :label="t('dash.totalOrders')"
          :height="260"
          :initial="6"
        />
      </article>

      <!-- Sales by time of day (horizontal bars) -->
      <article class="card p-5 xl:col-span-3">
        <div class="flex items-start justify-between">
          <h2 class="text-[15px] text-slate-700">{{ t('dash.hours') }}</h2>
          <button type="button" disabled class="icon-btn -me-1.5 -mt-1.5" :title="t('dash.filtersSoon')" :aria-label="t('dash.filtersSoon')">
            <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
              <path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" />
            </svg>
          </button>
        </div>
        <ul class="mt-5 space-y-3.5">
          <li v-for="h in sample.hours" :key="h.label" class="grid grid-cols-[3.5rem_1fr_2.5rem] items-center gap-3 text-[13px]">
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

      <!-- Product sales (table) -->
      <article class="card p-5 md:col-span-2 xl:col-span-7">
        <div class="flex items-center justify-between">
          <h2 class="section-title text-[17px]">{{ t('dash.productSales') }}</h2>
          <button type="button" disabled class="icon-btn" :title="t('dash.filtersSoon')" :aria-label="t('dash.filtersSoon')">
            <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
              <path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" />
            </svg>
          </button>
        </div>
        <div class="-mx-2 mt-3 overflow-x-auto">
          <table class="w-full min-w-[460px] text-[13px]">
            <thead>
              <tr class="text-[12px] text-slate-500">
                <th class="px-1.5 py-2 text-start font-normal">{{ t('dash.col.item') }}</th>
                <th class="px-1.5 py-2 text-end font-normal">{{ t('dash.col.stock') }}</th>
                <th class="px-1.5 py-2 text-end font-normal">{{ t('dash.col.oldPrice') }}</th>
                <th class="px-1.5 py-2 text-end font-normal">{{ t('dash.col.sale') }}</th>
                <th class="px-1.5 py-2 text-end font-normal">{{ t('dash.col.newPrice') }}</th>
                <th class="px-1.5 py-2 text-end font-normal">{{ t('dash.col.sold') }}</th>
                <th class="w-8"><span class="sr-only">{{ t('dash.col.actions') }}</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in sample.products" :key="p.name" class="border-t border-[var(--hairline)]">
                <td class="px-1.5 py-3">
                  <span class="flex items-center gap-3">
                    <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-500" aria-hidden="true">
                      <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round">
                        <path d="M12 3 4 7v10l8 4 8-4V7l-8-4Z" /><path d="m4 7 8 4 8-4M12 11v10" />
                      </svg>
                    </span>
                    <span class="font-medium text-slate-900">{{ p.name }}</span>
                  </span>
                </td>
                <td class="px-1.5 py-3 text-end text-slate-700 tabular-nums">{{ number(p.stock) }}</td>
                <td class="px-1.5 py-3 text-end text-slate-500 line-through tabular-nums">{{ money(p.oldPrice) }}</td>
                <td class="px-1.5 py-3 text-end font-medium text-green-700 tabular-nums dark:text-green-400">{{ p.sale }}%</td>
                <td class="px-1.5 py-3 text-end font-medium text-slate-900 tabular-nums">{{ money(p.oldPrice * (1 - p.sale / 100)) }}</td>
                <td class="px-1.5 py-3 text-end text-slate-700 tabular-nums">{{ number(p.sold) }}</td>
                <td class="px-1 py-3 text-center">
                  <button type="button" disabled class="icon-btn mx-auto" :aria-label="t('dash.col.actions')">
                    <svg viewBox="0 0 24 24" class="h-5 w-5" fill="currentColor" aria-hidden="true">
                      <circle cx="12" cy="5.5" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="12" cy="18.5" r="1.6" />
                    </svg>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <!-- Recent orders (list) -->
      <article class="card p-5 md:col-span-2 xl:col-span-5">
        <div class="flex items-center justify-between">
          <h2 class="section-title text-[17px]">{{ t('dash.recentOrders') }}</h2>
          <button type="button" disabled class="icon-btn" :title="t('dash.filtersSoon')" :aria-label="t('dash.filtersSoon')">
            <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
              <path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" />
            </svg>
          </button>
        </div>
        <ul class="mt-3">
          <li v-for="o in sample.recent" :key="o.id" class="flex items-center gap-3 border-t border-[var(--hairline)] py-3 first:border-0">
            <span class="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-brand-tint text-brand-ink" aria-hidden="true">
              <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round">
                <path d="M5 8h14l-1 12H6L5 8Z" /><path d="M9 8V6a3 3 0 0 1 6 0v2M10 13h4" />
              </svg>
            </span>
            <span class="min-w-0 flex-1 leading-tight">
              <span class="block truncate text-[14px] font-medium text-slate-900" dir="ltr">#{{ o.id }}</span>
              <span class="block truncate text-[13px] text-slate-500">{{ o.customer }}</span>
            </span>
            <span class="shrink-0 text-[14px] font-medium text-slate-900 tabular-nums">{{ money(o.amount) }}</span>
            <span class="shrink-0 text-end leading-tight">
              <span class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium" :class="STATUS_STYLE[o.status]">
                <span class="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />{{ t(`dash.status.${o.status}`) }}
              </span>
              <span class="mt-1 block text-[11px] text-slate-500">{{ ago(o.hoursAgo) }}</span>
            </span>
          </li>
        </ul>
      </article>
    </div>
  </div>
</template>
