<script setup lang="ts">
// Till receipt, sized for an 80 mm receipt printer. Shown only when printing
// (see .print-area in styles.css); rendered at the end of <body>.
import { useI18n } from 'vue-i18n'

import { branding } from '@/branding'
import { formatMoney, formatQty } from '@/inventory'
import { methodLabel, type Sale } from '@/pos'

const props = defineProps<{ sale: Sale }>()
const { t, locale } = useI18n()

const money = (value: number) => formatMoney(value, props.sale.currency, locale.value)
const when = () => new Date(props.sale.posted).toLocaleString(locale.value, { dateStyle: 'short', timeStyle: 'short' })
</script>

<template>
  <Teleport to="body">
    <div class="print-area receipt" dir="auto">
      <div class="receipt-center">
        <strong class="receipt-title">{{ branding.app_name }}</strong>
        <div>{{ sale.shop_name }}</div>
        <div>{{ when() }}</div>
        <div>{{ t('pos.receiptNo', { name: sale.name }) }}</div>
      </div>
      <hr />
      <table>
        <tbody>
          <template v-for="line in sale.lines" :key="line.item_code">
            <tr>
              <td colspan="2">{{ line.item_name }}</td>
            </tr>
            <tr>
              <td>{{ formatQty(line.qty, locale) }} × {{ money(line.rate) }}</td>
              <td class="receipt-end">{{ money(line.amount) }}</td>
            </tr>
          </template>
        </tbody>
      </table>
      <hr />
      <table>
        <tbody>
          <tr v-if="sale.taxes">
            <td>{{ t('pos.taxes') }}</td>
            <td class="receipt-end">{{ money(sale.taxes) }}</td>
          </tr>
          <tr class="receipt-total">
            <td>{{ t('pos.total') }}</td>
            <td class="receipt-end">{{ money(sale.total) }}</td>
          </tr>
          <tr v-for="payment in sale.payments" :key="payment.mode">
            <td>{{ methodLabel(payment.mode, t) }}</td>
            <td class="receipt-end">{{ money(payment.amount) }}</td>
          </tr>
          <tr v-if="sale.change">
            <td>{{ t('pos.change') }}</td>
            <td class="receipt-end">{{ money(sale.change) }}</td>
          </tr>
        </tbody>
      </table>
      <hr />
      <div class="receipt-center">
        <div>{{ t('pos.servedBy', { name: sale.cashier }) }}</div>
        <div>{{ t('pos.thanks') }}</div>
      </div>
    </div>
  </Teleport>
</template>
