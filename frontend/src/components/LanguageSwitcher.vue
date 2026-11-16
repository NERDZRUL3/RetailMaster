<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { branding } from '@/branding'
import type { Locale } from '@/i18n'
import { chooseLocale } from '@/session'

const { t, locale } = useI18n()

const shortNames: Record<Locale, string> = { en: 'EN', fr: 'FR', ar: 'ع' }
</script>

<template>
  <!-- Only the languages this site enabled; nothing to switch if there is just one. -->
  <div
    v-if="branding.languages.length > 1"
    class="inline-flex rounded-lg border border-slate-200 bg-white p-0.5"
    role="group"
    :aria-label="t('language.label')"
  >
    <button
      v-for="code in branding.languages"
      :key="code"
      type="button"
      class="min-w-9 rounded-md px-2 py-1 text-sm font-medium"
      :class="locale === code ? 'bg-brand-600 text-on-brand' : 'text-slate-600 hover:bg-slate-100'"
      :aria-pressed="locale === code"
      :title="t(`language.${code}`)"
      @click="chooseLocale(code)"
    >
      {{ shortNames[code] }}
    </button>
  </div>
</template>
