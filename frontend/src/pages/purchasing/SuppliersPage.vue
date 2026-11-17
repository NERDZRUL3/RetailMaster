<script setup lang="ts">
// Suppliers: who the shops buy from, how to reach them, open orders.
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import AppDialog from '@/components/AppDialog.vue'
import { purchasingApi, type Supplier } from '@/purchasing'
import { session } from '@/session'

const { t } = useI18n()
const canEdit = computed(() => !!session.context?.can_buy)
const query = ref('')
const rows = ref<Supplier[]>([])
const loading = ref(false)
const error = ref('')
const editing = ref<Partial<Supplier> | null>(null)
const saving = ref(false)
const formError = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = await purchasingApi.suppliers(query.value.trim())
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    loading.value = false
  }
}
let timer: ReturnType<typeof setTimeout> | undefined
watch(query, () => {
  clearTimeout(timer)
  timer = setTimeout(load, 250)
})
onMounted(load)

function edit(supplier?: Supplier) {
  formError.value = ''
  editing.value = supplier ? { ...supplier } : { supplier_name: '', phone: '', email: '', notes: '', disabled: 0 }
}

async function save() {
  if (!editing.value || saving.value) return
  saving.value = true
  formError.value = ''
  try {
    await purchasingApi.saveSupplier(editing.value)
    editing.value = null
    await load()
  } catch (err) {
    formError.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-4xl">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="page-title">{{ t('suppliers.title') }}</h1>
        <p class="page-subtitle">{{ t('suppliers.subtitle') }}</p>
      </div>
      <button v-if="canEdit" type="button" class="btn-primary" @click="edit()">+ {{ t('suppliers.add') }}</button>
    </div>

    <input
      v-model="query"
      type="search"
      dir="auto"
      class="field mt-6 bg-white text-[15px]"
      :placeholder="t('suppliers.search')"
      :aria-label="t('suppliers.search')"
    />
    <p v-if="error" class="notice-error mt-4" role="alert">{{ error }}</p>

    <ul class="list stagger mt-4" :aria-busy="loading">
      <li v-for="s in rows" :key="s.name" class="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3.5">
        <span class="min-w-0 flex-1">
          <span class="block font-medium text-slate-900" :class="s.disabled ? 'line-through opacity-60' : ''" dir="auto">{{ s.supplier_name }}</span>
          <span class="block text-[13px] text-slate-500">
            <a v-if="s.phone" :href="`tel:${s.phone}`" class="hover:underline" dir="ltr">{{ s.phone }}</a>
            <template v-if="s.phone && s.email"> · </template>
            <a v-if="s.email" :href="`mailto:${s.email}`" class="hover:underline">{{ s.email }}</a>
          </span>
        </span>
        <RouterLink v-if="s.open_orders" :to="{ path: '/purchase-orders', query: { status: 'open', q: s.supplier_name } }" class="badge-brand">
          {{ t('suppliers.openOrders', { n: s.open_orders }, s.open_orders) }}
        </RouterLink>
        <RouterLink v-if="canEdit && !s.disabled" :to="{ path: '/purchase-orders/new', query: { supplier: s.name } }" class="btn-quiet px-2.5 py-1 text-[13px]">
          {{ t('suppliers.order') }}
        </RouterLink>
        <button v-if="canEdit" type="button" class="btn-quiet px-2.5 py-1 text-[13px]" @click="edit(s)">{{ t('suppliers.edit') }}</button>
      </li>
    </ul>
    <p v-if="!loading && !rows.length" class="hint mt-6 text-center">{{ t('suppliers.empty') }}</p>

    <AppDialog v-if="editing" :title="editing.name ? t('suppliers.editTitle') : t('suppliers.add')" @close="editing = null">
      <p v-if="formError" class="notice-error mb-3" role="alert">{{ formError }}</p>
      <label class="label" for="sup-name">{{ t('suppliers.name') }}</label>
      <input id="sup-name" v-model="editing.supplier_name" autofocus maxlength="140" dir="auto" class="field text-[15px]" />
      <div class="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <label class="label" for="sup-phone">{{ t('suppliers.phone') }}</label>
          <input id="sup-phone" v-model="editing.phone" type="tel" maxlength="40" dir="ltr" class="field text-[15px]" />
        </div>
        <div>
          <label class="label" for="sup-email">{{ t('suppliers.email') }}</label>
          <input id="sup-email" v-model="editing.email" type="email" maxlength="140" dir="ltr" class="field text-[15px]" />
        </div>
      </div>
      <label class="label mt-4" for="sup-notes">{{ t('suppliers.notes') }}</label>
      <textarea id="sup-notes" v-model="editing.notes" rows="3" maxlength="1000" dir="auto" class="field text-[15px]" :placeholder="t('suppliers.notesPlaceholder')" />
      <label v-if="editing.name" class="mt-4 flex items-center gap-2 text-[15px] text-slate-700">
        <input v-model="editing.disabled" type="checkbox" :true-value="1" :false-value="0" class="h-4 w-4" />
        {{ t('suppliers.disabled') }}
      </label>
      <div class="mt-6 grid grid-cols-[auto_1fr] gap-2">
        <button type="button" class="btn-secondary btn-lg" @click="editing = null">{{ t('categories.cancel') }}</button>
        <button type="button" class="btn-primary btn-lg" :disabled="saving || !editing.supplier_name?.trim()" @click="save">
          {{ saving ? t('pos.saving') : t('categories.save') }}
        </button>
      </div>
    </AppDialog>
  </div>
</template>
