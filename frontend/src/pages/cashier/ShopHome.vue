<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import ShopCard from '@/components/ShopCard.vue'
import { session } from '@/session'

const { t } = useI18n()

const shops = computed(() => session.context?.shops ?? [])
</script>

<template>
  <div class="mx-auto max-w-xl">
    <h1 class="text-2xl font-semibold text-slate-900">
      {{ t('shop.greeting', { name: session.context?.full_name ?? '' }) }}
    </h1>

    <template v-if="shops.length">
      <h2 class="mt-6 text-sm font-medium text-slate-500">
        {{ shops.length === 1 ? t('shop.yourShop') : t('shop.yourShops') }}
      </h2>
      <div class="mt-2 grid gap-3">
        <ShopCard v-for="shop in shops" :key="shop.name" :shop="shop" />
      </div>

      <button
        type="button"
        disabled
        class="mt-6 w-full rounded-xl bg-brand-600 px-4 py-4 text-lg font-semibold text-on-brand disabled:opacity-50"
      >
        {{ t('shop.openPos') }}
      </button>
      <p class="mt-2 text-center text-sm text-slate-500">{{ t('shop.posSoon') }}</p>
    </template>

    <p v-else class="mt-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      {{ t('shop.noShop') }}
    </p>
  </div>
</template>
