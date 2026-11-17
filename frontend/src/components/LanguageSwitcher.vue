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
  <div v-if="branding.languages.length > 1" class="segmented" role="group" :aria-label="t('language.label')">
    <button
      v-for="code in branding.languages"
      :key="code"
      type="button"
      class="segment"
      :aria-pressed="locale === code"
      :title="t(`language.${code}`)"
      @click="chooseLocale(code)"
    >
      {{ shortNames[code] }}
    </button>
  </div>
</template>
