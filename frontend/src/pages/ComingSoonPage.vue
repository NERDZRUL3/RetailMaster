<script setup lang="ts">
// Placeholder for menu sections that are not built yet.
import { useI18n } from 'vue-i18n'

defineProps<{ section: string }>()
const { t } = useI18n()
</script>

<template>
  <div class="card grid min-h-[60vh] place-items-center p-10 text-center">
    <div class="max-w-md">
      <span class="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-brand-tint text-brand-ink" aria-hidden="true">
        <svg viewBox="0 0 24 24" class="h-7 w-7" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round">
          <circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" />
        </svg>
      </span>
      <h1 class="page-title mt-5">{{ t(`nav.items.${section}`) }}</h1>
      <p class="mt-3 text-[15px] text-slate-500">{{ t('soon.body') }}</p>
      <RouterLink to="/" class="btn-secondary mt-6">{{ t('soon.back') }}</RouterLink>
    </div>
  </div>
</template>
