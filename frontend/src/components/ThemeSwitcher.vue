<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { setTheme, theme, THEME_CHOICES } from '@/theme'

const { t } = useI18n()
</script>

<template>
  <div
    class="inline-flex rounded-lg border border-slate-200 bg-white p-0.5"
    role="group"
    :aria-label="t('theme.label')"
  >
    <button
      v-for="choice in THEME_CHOICES"
      :key="choice"
      type="button"
      class="grid h-8 w-8 place-items-center rounded-md"
      :class="theme.choice === choice ? 'bg-brand-600 text-on-brand' : 'text-slate-600 hover:bg-slate-100'"
      :aria-pressed="theme.choice === choice"
      :title="t(`theme.${choice}`)"
      @click="setTheme(choice)"
    >
      <span class="sr-only">{{ t(`theme.${choice}`) }}</span>
      <!-- Automatic: half-filled circle -->
      <svg v-if="choice === 'system'" viewBox="0 0 24 24" class="h-4 w-4" aria-hidden="true">
        <circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2" />
        <path d="M12 4a8 8 0 0 1 0 16Z" fill="currentColor" />
      </svg>
      <!-- Light: sun -->
      <svg
        v-else-if="choice === 'light'"
        viewBox="0 0 24 24"
        class="h-4 w-4"
        aria-hidden="true"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
      >
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </svg>
      <!-- Dark: moon -->
      <svg v-else viewBox="0 0 24 24" class="h-4 w-4" aria-hidden="true">
        <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" fill="currentColor" />
      </svg>
    </button>
  </div>
</template>
