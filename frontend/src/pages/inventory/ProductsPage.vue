<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { ApiError } from '@/api'
import { type FormOptions, formatMoney, formatQty, inventoryApi, type Product } from '@/inventory'

const { t, locale } = useI18n()
const router = useRouter()

const options = ref<FormOptions | null>(null)
const products = ref<Product[]>([])
const query = ref('')
const shop = ref('')
const lowOnly = ref(false)
const loading = ref(false)
const error = ref('')
const searchInput = ref<HTMLInputElement | null>(null)

let requestId = 0
let timer: ReturnType<typeof setTimeout> | undefined

async function search() {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const result = await inventoryApi.search(query.value, shop.value, lowOnly.value)
    if (id === requestId) products.value = result
  } catch (err) {
    if (id === requestId) error.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    if (id === requestId) loading.value = false
  }
}

// Typing searches after a short pause; a scanner ends with Enter.
watch(query, () => {
  clearTimeout(timer)
  timer = setTimeout(search, 300)
})
watch([shop, lowOnly], search)

async function onEnter() {
  clearTimeout(timer)
  await search()
  // An exact barcode or code match opens the product straight away.
  const code = query.value.trim()
  const exact = products.value.find((p) => p.item_code === code || p.barcodes.includes(code))
  if (exact) await router.push(`/products/${encodeURIComponent(exact.item_code)}`)
}

onMounted(async () => {
  searchInput.value?.focus()
  try {
    options.value = await inventoryApi.options()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : String(err)
  }
  await search()
})
</script>

<template>
  <div>
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="page-title">{{ t('products.title') }}</h1>
        <p class="page-subtitle">{{ t('products.subtitle') }}</p>
      </div>
      <RouterLink v-if="options?.can_create" to="/products/new" class="btn-primary">
        <span aria-hidden="true" class="text-[18px] leading-none">+</span>
        {{ t('products.new') }}
      </RouterLink>
    </div>

    <div class="mt-8 flex flex-wrap items-center gap-3">
      <div class="relative min-w-0 flex-1 basis-64">
        <svg
          viewBox="0 0 24 24"
          class="pointer-events-none absolute start-4 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-slate-400"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          aria-hidden="true"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <input
          ref="searchInput"
          v-model="query"
          type="search"
          :placeholder="t('products.searchPlaceholder')"
          :aria-label="t('products.searchPlaceholder')"
          class="field ps-11"
          @keydown.enter.prevent="onEnter"
        />
      </div>
      <select
        v-if="options && options.shops.length > 1"
        v-model="shop"
        class="field w-auto text-[15px]"
        :aria-label="t('products.shop')"
      >
        <option value="">{{ t('products.allShops') }}</option>
        <option v-for="s in options.shops" :key="s.name" :value="s.name">{{ s.shop_name }}</option>
      </select>
      <label class="inline-flex items-center gap-2 px-1 text-[15px] text-slate-700">
        <input v-model="lowOnly" type="checkbox" class="check" />
        {{ t('products.lowOnly') }}
      </label>
    </div>

    <p v-if="error" class="notice-error mt-4" role="alert">{{ error }}</p>

    <div class="list mt-6" :aria-busy="loading">
      <p v-if="!loading && !products.length" class="px-6 py-14 text-center text-[15px] text-slate-500">
        {{ query ? t('products.noMatch') : t('products.empty') }}
      </p>
      <template v-else>
        <RouterLink
          v-for="product in products"
          :key="product.item_code"
          :to="`/products/${encodeURIComponent(product.item_code)}`"
          class="row flex flex-wrap items-center gap-x-5 gap-y-2 px-5 py-4 sm:px-6"
        >
          <div class="min-w-0 flex-1 basis-48">
            <div class="flex items-center gap-2">
              <span class="truncate text-[17px] font-medium text-slate-900" dir="auto">{{ product.item_name }}</span>
              <span v-if="product.disabled" class="badge-neutral">{{ t('products.inactive') }}</span>
              <span v-if="product.low" class="badge-warn">{{ t('products.low') }}</span>
            </div>
            <div class="mt-0.5 truncate text-[13px] text-slate-500" dir="ltr">
              {{ product.item_code }}<template v-if="product.barcodes.length"> · {{ product.barcodes.join(', ') }}</template>
            </div>
          </div>
          <div class="flex flex-wrap gap-1.5">
            <span v-for="row in product.stock" :key="row.shop" :class="row.low ? 'badge-warn' : 'badge-neutral'">
              <bdi>{{ row.shop_name }}</bdi>&nbsp;·&nbsp;{{ formatQty(row.qty, locale) }} {{ product.stock_uom }}
            </span>
          </div>
          <div class="min-w-20 text-end text-[17px] font-semibold text-slate-900 tabular-nums">
            {{ formatMoney(product.price, product.currency || options?.currency || null, locale) }}
          </div>
          <svg viewBox="0 0 24 24" class="h-4 w-4 text-slate-300 rtl:rotate-180" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true">
            <path d="m9 6 6 6-6 6" />
          </svg>
        </RouterLink>
      </template>
    </div>
  </div>
</template>
