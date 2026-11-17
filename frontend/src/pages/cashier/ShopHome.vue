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
    <h1 class="page-title">
      {{ t('shop.greeting', { name: session.context?.full_name ?? '' }) }}
    </h1>

    <template v-if="shops.length">
      <h2 class="label mt-8">
        {{ shops.length === 1 ? t('shop.yourShop') : t('shop.yourShops') }}
      </h2>
      <div class="grid gap-4">
        <ShopCard v-for="shop in shops" :key="shop.name" :shop="shop" />
      </div>

      <RouterLink v-if="session.context?.can_sell" to="/pos" class="btn-primary btn-lg mt-8 w-full py-4">
        {{ t('shop.openPos') }}
      </RouterLink>
    </template>

    <p v-else class="notice-warn mt-8">{{ t('shop.noShop') }}</p>
  </div>
</template>
