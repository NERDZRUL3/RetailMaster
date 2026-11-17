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
    <h1 class="page-title">{{ t('owner.title') }}</h1>
    <p class="page-subtitle">{{ t('owner.subtitle') }}</p>

    <p class="notice-info mt-6">{{ t('owner.previewNote') }}</p>

    <section class="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
      <div v-for="tile in tiles" :key="tile" class="card-pad">
        <div class="text-[13px] font-medium text-slate-500">{{ t(tile) }}</div>
        <div class="mt-3 text-[34px] leading-none font-semibold tracking-tight text-slate-300" aria-hidden="true">—</div>
        <div class="mt-2 text-[12px] text-slate-400">{{ t('common.notConnected') }}</div>
      </div>
    </section>

    <section class="mt-12">
      <h2 class="section-title">{{ t('owner.shops') }}</h2>
      <div v-if="shops.length" class="mt-4 grid gap-4 sm:grid-cols-2">
        <ShopCard v-for="shop in shops" :key="shop.name" :shop="shop" />
      </div>
      <p v-else class="mt-3 text-[15px] text-slate-500">{{ t('owner.noShops') }}</p>
    </section>
  </div>
</template>
