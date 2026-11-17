<script setup lang="ts">
// Till session history: who opened the till when, takings and cash
// differences; open one for its X or Z report and print it.
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import AppDialog from '@/components/AppDialog.vue'
import TillReport from '@/components/TillReport.vue'
import { formatMoney } from '@/inventory'
import { posApi } from '@/pos'
import { session } from '@/session'
import { formatWhen, type SessionReport, type SessionRow, tillApi } from '@/till'

const { t, locale } = useI18n()
const shops = computed(() => session.context?.shops ?? [])
const shop = ref(shops.value[0]?.name ?? '')
const rows = ref<SessionRow[]>([])
const loading = ref(false)
const error = ref('')
const report = ref<SessionReport | null>(null)
const printReport = ref<SessionReport | null>(null)
const currency = ref<string | null>(null)

const money = (value: number) => formatMoney(value, currency.value, locale.value)
const signed = (value: number) => (value > 0 ? `+${money(value)}` : money(value))

async function load() {
  if (!shop.value) return
  loading.value = true
  error.value = ''
  try {
    const [list, tillInfo] = await Promise.all([tillApi.list(shop.value), posApi.till(shop.value)])
    rows.value = list
    currency.value = tillInfo.currency
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    loading.value = false
  }
}
watch(shop, load)
onMounted(load)

async function open(row: SessionRow) {
  try {
    report.value = await tillApi.report(row.name)
    currency.value = report.value.currency
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : String(err)
  }
}

async function print() {
  printReport.value = report.value
  await nextTick()
  window.print()
}
</script>

<template>
  <div class="mx-auto max-w-4xl">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="page-title">{{ t('till.history') }}</h1>
        <p class="page-subtitle">{{ t('till.historyHint') }}</p>
      </div>
      <div class="flex items-center gap-2">
        <RouterLink to="/pos" class="btn-secondary px-3.5 py-2 text-[14px]">{{ t('nav.items.pos') }}</RouterLink>
        <select v-if="shops.length > 1" v-model="shop" class="field w-auto rounded-xl bg-white py-2.5 text-[15px]" :aria-label="t('pos.shop')">
          <option v-for="s in shops" :key="s.name" :value="s.name">{{ s.shop_name }}</option>
        </select>
      </div>
    </div>

    <p v-if="error" class="notice-error mt-6" role="alert">{{ error }}</p>

    <div class="stagger mt-6 list" :aria-busy="loading">
      <button
        v-for="row in rows"
        :key="row.name"
        type="button"
        class="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3.5 text-start hover:bg-[var(--row-hover)]"
        @click="open(row)"
      >
        <span class="min-w-0 flex-1">
          <span class="block text-[15px] font-medium text-slate-900">{{ row.user_name }}</span>
          <span class="block text-[13px] text-slate-500">
            {{ formatWhen(row.opened, locale) }} → {{ row.closed ? formatWhen(row.closed, locale) : t('till.stillOpen') }}
          </span>
        </span>
        <span v-if="row.open" class="badge-warn">{{ t('till.openBadge') }}</span>
        <template v-else>
          <span class="text-[15px] font-medium text-slate-900 tabular-nums">{{ formatMoney(row.total ?? 0, currency, locale) }}</span>
          <span
            class="w-24 text-end text-[14px] font-semibold tabular-nums"
            :class="Math.abs(row.difference ?? 0) < 0.005 ? 'text-green-700' : (row.difference ?? 0) < 0 ? 'text-red-600' : 'text-amber-600'"
          >
            {{ Math.abs(row.difference ?? 0) < 0.005 ? t('till.balancedShort') : signed(row.difference ?? 0) }}
          </span>
        </template>
      </button>
    </div>
    <p v-if="!loading && !rows.length" class="hint mt-6 text-center">{{ t('till.noSessions') }}</p>

    <AppDialog v-if="report" wide :title="report.closed ? t('till.zReport') : t('till.xReport')" @close="report = null">
      <TillReport :report="report" />
      <div class="mt-6 flex justify-end">
        <button type="button" class="btn-secondary" @click="print">{{ t('till.printReport') }}</button>
      </div>
    </AppDialog>
    <TillReport v-if="printReport" :report="printReport" variant="print" />
  </div>
</template>
