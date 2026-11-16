<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import ShopCard from '@/components/ShopCard.vue'
import { session } from '@/session'

const { t } = useI18n()

const shops = computed(() => session.context?.shops ?? [])

// Placeholders until POS, cash and inventory data exist. They show no numbers
// on purpose: an invented figure on an owner dashboard would be worse than none.
const tiles = ['owner.salesToday', 'owner.cashRegisters', 'owner.lowStock', 'owner.invoicesToVerify']
</script>

<template>
  <div>
    <h1 class="text-2xl font-semibold text-slate-900">{{ t('owner.title') }}</h1>
    <p class="mt-1 text-sm text-slate-500">{{ t('owner.subtitle') }}</p>

    <p class="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      {{ t('owner.previewNote') }}
    </p>

    <section class="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
      <div v-for="tile in tiles" :key="tile" class="rounded-xl border border-slate-200 bg-white p-4">
        <div class="text-sm text-slate-500">{{ t(tile) }}</div>
        <div class="mt-2 text-2xl font-semibold text-slate-300" aria-hidden="true">—</div>
        <div class="mt-1 text-xs text-slate-400">{{ t('common.notConnected') }}</div>
      </div>
    </section>

    <section class="mt-8">
      <h2 class="text-lg font-semibold text-slate-900">{{ t('owner.shops') }}</h2>
      <div v-if="shops.length" class="mt-3 grid gap-3 sm:grid-cols-2">
        <ShopCard v-for="shop in shops" :key="shop.name" :shop="shop" />
      </div>
      <p v-else class="mt-3 text-sm text-slate-500">{{ t('owner.noShops') }}</p>
    </section>
  </div>
</template>
