<script setup lang="ts">
import { branding } from '@/branding'

withDefaults(defineProps<{ logoClass?: string; showName?: boolean }>(), {
  logoClass: 'h-8 w-8 rounded-full bg-white',
  showName: true,
})
</script>

<template>
  <span class="inline-flex items-center gap-2.5 font-semibold text-brand-ink">
    <img v-if="branding.logo" :src="branding.logo" :alt="branding.app_name" :class="[logoClass, 'object-contain']" />
    <bdi v-if="showName || !branding.logo">{{ branding.app_name }}</bdi>
  </span>
</template>
