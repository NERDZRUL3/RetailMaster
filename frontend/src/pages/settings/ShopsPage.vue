<script setup lang="ts">
// The owner's shops (side menu → Shops): add a shop, switch one off or on.
import { useI18n } from 'vue-i18n'

import ShopsCard from '@/components/ShopsCard.vue'

const { t } = useI18n()
</script>

<template>
  <div class="mx-auto max-w-3xl">
    <h1 class="page-title">{{ t('nav.items.shops') }}</h1>
    <p class="page-subtitle">{{ t('shopSetup.pageSubtitle') }}</p>
    <div class="mt-6">
      <ShopsCard :heading="false" />
    </div>
  </div>
</template>
