<script setup lang="ts">
// A till session's report: X report while open, Z report once closed.
// variant 'print' renders the 80 mm printout (see .print-area in styles.css).
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { branding } from '@/branding'
import { formatMoney } from '@/inventory'
import { methodLabel } from '@/pos'
import { formatWhen, type SessionReport } from '@/till'

const props = withDefaults(defineProps<{ report: SessionReport; variant?: 'screen' | 'print' }>(), { variant: 'screen' })
const { t, locale } = useI18n()

const money = (value: number | null) => (value === null ? '—' : formatMoney(value, props.report.currency, locale.value))
const signed = (value: number) => (value > 0 ? `+${money(value)}` : money(value))
const showExpected = computed(() => props.report.rows.some((row) => row.expected !== null))
const showCounted = computed(() => props.report.rows.some((row) => row.counted !== null))
const title = computed(() => (props.report.closed ? t('till.zReport') : t('till.xReport')))
const diffClass = (value: number | null) =>
  value === null || Math.abs(value) < 0.005 ? 'text-slate-900' : value < 0 ? 'text-red-600' : 'text-amber-600'
</script>

<template>
  <!-- On screen -->
  <div v-if="variant === 'screen'" class="space-y-5">
    <div class="text-[14px] text-slate-500">
      <div>{{ report.shop_name }} · {{ report.user_name }}</div>
      <div>
        {{ t('till.openedAt', { when: formatWhen(report.opened, locale) }) }}
        <template v-if="report.closed"> · {{ t('till.closedAt', { when: formatWhen(report.closed, locale) }) }}</template>
      </div>
    </div>

    <div class="grid grid-cols-3 gap-2">
      <div class="rounded-xl bg-slate-50 p-3">
        <div class="text-[12px] text-slate-500">{{ t('till.sales') }}</div>
        <div class="text-[20px] font-semibold text-slate-900 tabular-nums">{{ report.sales_count }}</div>
      </div>
      <div class="rounded-xl bg-slate-50 p-3">
        <div class="text-[12px] text-slate-500">{{ t('till.takings') }}</div>
        <div class="text-[20px] font-semibold text-slate-900 tabular-nums">{{ money(report.total) }}</div>
      </div>
      <div class="rounded-xl bg-slate-50 p-3">
        <div class="text-[12px] text-slate-500">{{ t('till.returns') }}</div>
        <div class="text-[20px] font-semibold text-slate-900 tabular-nums">{{ report.returns_count }}</div>
      </div>
    </div>

    <div class="overflow-x-auto">
      <table class="w-full text-[14px] tabular-nums">
        <thead>
          <tr class="text-start text-[12px] text-slate-500">
            <th class="py-1.5 text-start font-medium">{{ t('till.method') }}</th>
            <th class="py-1.5 text-end font-medium">{{ t('till.opening') }}</th>
            <th class="py-1.5 text-end font-medium">{{ t('till.salesAmount') }}</th>
            <th class="py-1.5 text-end font-medium">{{ t('till.inOut') }}</th>
            <th v-if="showExpected" class="py-1.5 text-end font-medium">{{ t('till.expected') }}</th>
            <th v-if="showCounted" class="py-1.5 text-end font-medium">{{ t('till.counted') }}</th>
            <th v-if="showCounted && showExpected" class="py-1.5 text-end font-medium">{{ t('till.difference') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in report.rows" :key="row.mode" class="border-t border-[var(--hairline)]">
            <td class="py-2 text-slate-900">{{ methodLabel(row.mode, t) }}</td>
            <td class="py-2 text-end">{{ money(row.opening) }}</td>
            <td class="py-2 text-end">{{ money(row.sales) }}</td>
            <td class="py-2 text-end">{{ row.cash ? signed(row.cash_in - row.cash_out) : '—' }}</td>
            <td v-if="showExpected" class="py-2 text-end">{{ money(row.expected) }}</td>
            <td v-if="showCounted" class="py-2 text-end">{{ money(row.counted) }}</td>
            <td v-if="showCounted && showExpected" class="py-2 text-end font-semibold" :class="diffClass(row.difference)">
              {{ row.difference === null ? '—' : signed(row.difference) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="!showExpected" class="hint">{{ t('till.blindHint') }}</p>

    <div v-if="report.movements.length">
      <h3 class="label">{{ t('till.movements') }}</h3>
      <ul class="space-y-1 text-[14px]">
        <li v-for="(m, i) in report.movements" :key="i" class="flex gap-3">
          <span class="shrink-0 text-slate-500 whitespace-nowrap tabular-nums">{{ new Date(m.time).toLocaleTimeString(locale, { timeStyle: 'short' }) }}</span>
          <span class="min-w-0 flex-1 truncate text-slate-700" dir="auto">{{ m.reason }} · {{ m.by }}</span>
          <span class="font-medium tabular-nums" :class="m.type === 'In' ? 'text-green-700' : 'text-red-600'">
            {{ m.type === 'In' ? '+' : '−' }}{{ money(m.amount) }}
          </span>
        </li>
      </ul>
    </div>

    <p v-if="report.note" class="rounded-xl bg-slate-50 p-3 text-[14px] text-slate-700" dir="auto">{{ report.note }}</p>
  </div>

  <!-- Printout -->
  <Teleport v-else to="body">
    <div class="print-area receipt" dir="auto">
      <div class="receipt-center">
        <strong class="receipt-title">{{ branding.app_name }}</strong>
        <div>{{ report.shop_name }}</div>
        <div><strong>{{ title }}</strong></div>
        <div>{{ report.user_name }}</div>
        <div>{{ t('till.openedAt', { when: formatWhen(report.opened, locale) }) }}</div>
        <div v-if="report.closed">{{ t('till.closedAt', { when: formatWhen(report.closed, locale) }) }}</div>
      </div>
      <hr />
      <table>
        <tbody>
          <tr><td>{{ t('till.sales') }}</td><td class="receipt-end">{{ report.sales_count }}</td></tr>
          <tr><td>{{ t('till.returns') }}</td><td class="receipt-end">{{ report.returns_count }} ({{ money(report.returns_total) }})</td></tr>
          <tr v-if="report.taxes"><td>{{ t('pos.taxes') }}</td><td class="receipt-end">{{ money(report.taxes) }}</td></tr>
          <tr class="receipt-total"><td>{{ t('till.takings') }}</td><td class="receipt-end">{{ money(report.total) }}</td></tr>
        </tbody>
      </table>
      <template v-for="row in report.rows" :key="row.mode">
        <hr />
        <table>
          <tbody>
            <tr class="receipt-total"><td colspan="2">{{ methodLabel(row.mode, t) }}</td></tr>
            <tr><td>{{ t('till.opening') }}</td><td class="receipt-end">{{ money(row.opening) }}</td></tr>
            <tr><td>{{ t('till.salesAmount') }}</td><td class="receipt-end">{{ money(row.sales) }}</td></tr>
            <template v-if="row.cash">
              <tr><td>{{ t('till.cashIn') }}</td><td class="receipt-end">{{ money(row.cash_in) }}</td></tr>
              <tr><td>{{ t('till.cashOut') }}</td><td class="receipt-end">{{ money(row.cash_out) }}</td></tr>
            </template>
            <tr v-if="row.expected !== null"><td>{{ t('till.expected') }}</td><td class="receipt-end">{{ money(row.expected) }}</td></tr>
            <tr v-if="row.counted !== null"><td>{{ t('till.counted') }}</td><td class="receipt-end">{{ money(row.counted) }}</td></tr>
            <tr v-if="row.difference !== null"><td>{{ t('till.difference') }}</td><td class="receipt-end">{{ signed(row.difference) }}</td></tr>
          </tbody>
        </table>
      </template>
      <template v-if="report.movements.length">
        <hr />
        <div>{{ t('till.movements') }}</div>
        <table>
          <tbody>
            <tr v-for="(m, i) in report.movements" :key="i">
              <td>{{ m.reason }}</td>
              <td class="receipt-end">{{ m.type === 'In' ? '+' : '-' }}{{ money(m.amount) }}</td>
            </tr>
          </tbody>
        </table>
      </template>
      <template v-if="report.note">
        <hr />
        <div>{{ report.note }}</div>
      </template>
      <hr />
      <div class="receipt-center">{{ report.name }}</div>
    </div>
  </Teleport>
</template>
