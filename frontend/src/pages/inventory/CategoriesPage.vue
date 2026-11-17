<script setup lang="ts">
// Product groups and subgroups on their own page (same panel as in the
// product editor).
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import { categoriesApi, type CategoryTree } from '@/categories'
import CategoryManager from '@/components/CategoryManager.vue'

const { t } = useI18n()
const tree = ref<CategoryTree | null>(null)
const error = ref('')

async function load() {
  try {
    tree.value = await categoriesApi.get()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : String(err)
  }
}
onMounted(load)
</script>

<template>
  <div class="mx-auto max-w-3xl">
    <h1 class="page-title">{{ t('nav.items.categories') }}</h1>
    <p class="page-subtitle">{{ t('categories.pageHint') }}</p>
    <p v-if="error" class="notice-error mt-6" role="alert">{{ error }}</p>
    <div v-if="tree" class="card-pad mt-6">
      <CategoryManager :tree="tree" :closable="false" @changed="load" />
    </div>
  </div>
</template>
