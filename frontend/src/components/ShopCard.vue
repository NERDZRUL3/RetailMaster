<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { Shop } from '@/session'

defineProps<{ shop: Shop }>()
const { t } = useI18n()
</script>

<template>
  <article class="rounded-xl border border-slate-200 bg-white p-4">
    <!-- Shop and company names are data: <bdi> keeps their own text direction
         while the card stays aligned with the page (right in Arabic). -->
    <h3 class="text-base font-semibold text-slate-900">
      <bdi>{{ shop.shop_name }}</bdi>
    </h3>
    <p class="mt-1 text-sm text-slate-500">
      {{ t('common.company') }}:
      <bdi>{{ shop.company }}</bdi>
    </p>
  </article>
</template>
