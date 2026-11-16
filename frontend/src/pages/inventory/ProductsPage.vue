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
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-semibold text-slate-900">{{ t('products.title') }}</h1>
        <p class="mt-1 text-sm text-slate-500">{{ t('products.subtitle') }}</p>
      </div>
      <RouterLink
        v-if="options?.can_create"
        to="/products/new"
        class="rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700"
      >
        {{ t('products.new') }}
      </RouterLink>
    </div>

    <div class="mt-5 flex flex-wrap items-center gap-3">
      <input
        ref="searchInput"
        v-model="query"
        type="search"
        :placeholder="t('products.searchPlaceholder')"
        :aria-label="t('products.searchPlaceholder')"
        class="min-w-0 flex-1 basis-64 rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-base"
        @keydown.enter.prevent="onEnter"
      />
      <select
        v-if="options && options.shops.length > 1"
        v-model="shop"
        class="rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm"
        :aria-label="t('products.shop')"
      >
        <option value="">{{ t('products.allShops') }}</option>
        <option v-for="s in options.shops" :key="s.name" :value="s.name">{{ s.shop_name }}</option>
      </select>
      <label class="inline-flex items-center gap-2 text-sm text-slate-700">
        <input v-model="lowOnly" type="checkbox" class="h-4 w-4 accent-brand-600" />
        {{ t('products.lowOnly') }}
      </label>
    </div>

    <p v-if="error" class="mt-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">{{ error }}</p>

    <div class="mt-4 overflow-hidden rounded-xl border border-slate-200 bg-white">
      <p v-if="!loading && !products.length" class="px-4 py-8 text-center text-sm text-slate-500">
        {{ query ? t('products.noMatch') : t('products.empty') }}
      </p>
      <ul v-else class="divide-y divide-slate-100" :aria-busy="loading">
        <li v-for="product in products" :key="product.item_code">
          <RouterLink
            :to="`/products/${encodeURIComponent(product.item_code)}`"
            class="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 hover:bg-slate-50"
          >
            <div class="min-w-0 flex-1 basis-48">
              <div class="flex items-center gap-2">
                <span class="truncate font-medium text-slate-900" dir="auto">{{ product.item_name }}</span>
                <span v-if="product.disabled" class="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
                  {{ t('products.inactive') }}
                </span>
                <span v-if="product.low" class="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-900">
                  {{ t('products.low') }}
                </span>
              </div>
              <div class="mt-0.5 truncate text-xs text-slate-500" dir="ltr">
                {{ product.item_code }}<template v-if="product.barcodes.length"> · {{ product.barcodes.join(', ') }}</template>
              </div>
            </div>
            <div class="text-sm font-medium text-slate-900">
              {{ formatMoney(product.price, product.currency || options?.currency || null, locale) }}
            </div>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="row in product.stock"
                :key="row.shop"
                class="rounded-md px-2 py-1 text-xs"
                :class="row.low ? 'bg-amber-50 text-amber-900' : 'bg-slate-100 text-slate-700'"
              >
                <bdi>{{ row.shop_name }}</bdi>: {{ formatQty(row.qty, locale) }} {{ product.stock_uom }}
              </span>
            </div>
          </RouterLink>
        </li>
      </ul>
    </div>
  </div>
</template>
