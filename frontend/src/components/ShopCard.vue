<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { Shop } from '@/session'

defineProps<{ shop: Shop }>()
const { t } = useI18n()
</script>

<template>
  <article class="card-pad flex items-center gap-4">
    <span class="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-brand-50 text-brand-ink" aria-hidden="true">
      <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round">
        <path d="M4 10v9h16v-9M3 10l2-5h14l2 5M3 10h18M9 19v-5h6v5" />
      </svg>
    </span>
    <!-- Shop and company names are data: <bdi> keeps their own text direction
         while the card stays aligned with the page (right in Arabic). -->
    <div class="min-w-0">
      <h3 class="truncate text-[17px] font-semibold text-slate-900">
        <bdi>{{ shop.shop_name }}</bdi>
      </h3>
      <p class="mt-0.5 truncate text-[13px] text-slate-500">
        {{ t('common.company') }}:
        <bdi>{{ shop.company }}</bdi>
      </p>
    </div>
  </article>
</template>
