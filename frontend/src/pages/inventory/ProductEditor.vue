<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { ApiError } from '@/api'
import { type FormOptions, formatQty, inventoryApi, type Product } from '@/inventory'

const props = defineProps<{ code?: string }>()
const { t, locale } = useI18n()
const router = useRouter()

const isNew = computed(() => !props.code)
const options = ref<FormOptions | null>(null)
const product = ref<Product | null>(null)
const loaded = ref(false)
const saving = ref(false)
const message = ref<{ kind: 'ok' | 'error'; text: string } | null>(null)
const newBarcode = ref('')

const form = reactive({
  item_code: '',
  item_name: '',
  item_group: '',
  stock_uom: '',
  brand: '',
  description: '',
  disabled: false,
  price: '' as string | number,
  barcodes: [] as string[],
  reorder: {} as Record<string, { level: string | number; qty: string | number }>,
})

const readOnly = computed(() => (isNew.value ? !options.value?.can_create : !options.value?.can_write))

function fill(p: Product) {
  product.value = p
  form.item_code = p.item_code
  form.item_name = p.item_name
  form.item_group = p.item_group
  form.stock_uom = p.stock_uom
  form.brand = p.brand ?? ''
  form.description = p.description ?? ''
  form.disabled = !!p.disabled
  form.price = p.price ?? ''
  form.barcodes = [...p.barcodes]
  for (const row of p.stock) {
    form.reorder[row.shop] = { level: row.reorder_level || '', qty: row.reorder_qty || '' }
  }
}

onMounted(async () => {
  try {
    options.value = await inventoryApi.options()
    for (const shop of options.value.shops) form.reorder[shop.name] = { level: '', qty: '' }
    if (props.code) {
      fill(await inventoryApi.get(props.code))
    } else {
      form.item_group = options.value.default_item_group ?? ''
      form.stock_uom = options.value.default_uom
    }
  } catch (err) {
    message.value = { kind: 'error', text: err instanceof ApiError ? err.message : String(err) }
  } finally {
    loaded.value = true
  }
})

function addBarcode() {
  const value = newBarcode.value.trim()
  if (value && !form.barcodes.includes(value)) form.barcodes.push(value)
  newBarcode.value = ''
}

function removeBarcode(value: string) {
  form.barcodes = form.barcodes.filter((b) => b !== value)
}

async function save() {
  addBarcode()
  saving.value = true
  message.value = null
  try {
    const saved = await inventoryApi.save({
      item_code: isNew.value ? form.item_code.trim() : props.code,
      item_name: form.item_name,
      item_group: form.item_group,
      stock_uom: form.stock_uom,
      brand: form.brand,
      description: form.description,
      disabled: form.disabled ? 1 : 0,
      price: form.price === '' ? null : Number(form.price),
      barcodes: form.barcodes,
      reorder: Object.entries(form.reorder).map(([shop, rule]) => ({
        shop,
        level: Number(rule.level) || 0,
        qty: Number(rule.qty) || 0,
      })),
    })
    fill(saved)
    message.value = { kind: 'ok', text: t('products.saved') }
    if (isNew.value) await router.replace(`/products/${encodeURIComponent(saved.item_code)}`)
  } catch (err) {
    message.value = { kind: 'error', text: err instanceof ApiError ? err.message : String(err) }
  } finally {
    saving.value = false
  }
}

function stockFor(shop: string) {
  return product.value?.stock.find((row) => row.shop === shop)
}
</script>

<template>
  <div class="mx-auto max-w-3xl">
    <RouterLink to="/products" class="text-sm font-medium text-brand-700 hover:underline">
      {{ t('products.back') }}
    </RouterLink>
    <h1 class="mt-2 text-2xl font-semibold text-slate-900" dir="auto">
      {{ isNew ? t('products.new') : form.item_name || t('products.title') }}
    </h1>

    <p
      v-if="message"
      class="mt-4 rounded-lg px-4 py-3 text-sm"
      :class="message.kind === 'ok' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'"
      role="status"
    >
      {{ message.text }}
    </p>

    <form v-if="loaded && options" class="mt-6 space-y-6" @submit.prevent="save">
      <fieldset :disabled="readOnly || saving" class="space-y-6">
        <section class="rounded-xl border border-slate-200 bg-white p-5">
          <h2 class="text-lg font-semibold text-slate-900">{{ t('products.details') }}</h2>

          <label class="mt-4 block text-sm font-medium text-slate-700" for="p-name">{{ t('products.name') }}</label>
          <input id="p-name" v-model="form.item_name" required dir="auto" maxlength="140" class="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-base" />

          <div class="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label class="block text-sm font-medium text-slate-700" for="p-code">{{ t('products.code') }}</label>
              <input
                id="p-code"
                v-model="form.item_code"
                dir="ltr"
                :disabled="!isNew"
                :placeholder="t('products.codeAuto')"
                class="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-base disabled:bg-slate-50 disabled:text-slate-500"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-slate-700" for="p-price">
                {{ t('products.price') }}<template v-if="options.currency"> ({{ options.currency }})</template>
              </label>
              <input id="p-price" v-model="form.price" type="number" min="0" step="0.01" dir="ltr" class="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-base" />
            </div>
            <div>
              <label class="block text-sm font-medium text-slate-700" for="p-group">{{ t('products.category') }}</label>
              <select id="p-group" v-model="form.item_group" class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-base">
                <option v-for="g in options.item_groups" :key="g" :value="g">{{ g }}</option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium text-slate-700" for="p-uom">{{ t('products.unit') }}</label>
              <select id="p-uom" v-model="form.stock_uom" :disabled="!isNew" class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-base disabled:bg-slate-50">
                <option v-for="u in options.uoms" :key="u" :value="u">{{ u }}</option>
              </select>
            </div>
            <div v-if="options.brands.length">
              <label class="block text-sm font-medium text-slate-700" for="p-brand">{{ t('products.brand') }}</label>
              <select id="p-brand" v-model="form.brand" class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-base">
                <option value="">—</option>
                <option v-for="b in options.brands" :key="b" :value="b">{{ b }}</option>
              </select>
            </div>
          </div>

          <label class="mt-4 block text-sm font-medium text-slate-700" for="p-desc">{{ t('products.description') }}</label>
          <textarea id="p-desc" v-model="form.description" rows="2" dir="auto" class="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-base" />

          <label class="mt-4 inline-flex items-center gap-2 text-sm text-slate-700">
            <input v-model="form.disabled" type="checkbox" class="h-4 w-4 accent-brand-600" />
            {{ t('products.inactiveLabel') }}
          </label>
        </section>

        <section class="rounded-xl border border-slate-200 bg-white p-5">
          <h2 class="text-lg font-semibold text-slate-900">{{ t('products.barcodes') }}</h2>
          <p class="mt-1 text-xs text-slate-500">{{ t('products.barcodesHint') }}</p>
          <div class="mt-3 flex gap-2">
            <input
              v-model="newBarcode"
              dir="ltr"
              :placeholder="t('products.scanOrType')"
              :aria-label="t('products.scanOrType')"
              class="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2.5 font-mono text-base"
              @keydown.enter.prevent="addBarcode"
            />
            <button type="button" class="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100" @click="addBarcode">
              {{ t('products.add') }}
            </button>
          </div>
          <ul v-if="form.barcodes.length" class="mt-3 flex flex-wrap gap-2">
            <li v-for="b in form.barcodes" :key="b" class="inline-flex items-center gap-1 rounded-md bg-slate-100 py-1 ps-2 pe-1 font-mono text-sm" dir="ltr">
              {{ b }}
              <button type="button" class="rounded px-1 text-slate-500 hover:bg-slate-200 hover:text-red-700" :aria-label="t('products.removeBarcode', { code: b })" @click="removeBarcode(b)">×</button>
            </li>
          </ul>
        </section>

        <section class="rounded-xl border border-slate-200 bg-white p-5">
          <h2 class="text-lg font-semibold text-slate-900">{{ t('products.stockAndReorder') }}</h2>
          <p class="mt-1 text-xs text-slate-500">{{ t('products.reorderHint') }}</p>
          <div class="mt-3 space-y-3">
            <div v-for="shop in options.shops" :key="shop.name" class="grid items-end gap-3 rounded-lg border border-slate-100 p-3 sm:grid-cols-[1fr_auto_auto]">
              <div>
                <div class="font-medium text-slate-900"><bdi>{{ shop.shop_name }}</bdi></div>
                <div class="text-sm" :class="stockFor(shop.name)?.low ? 'font-medium text-amber-800' : 'text-slate-500'">
                  {{ t('products.inStock') }}: {{ formatQty(stockFor(shop.name)?.qty ?? 0, locale) }} {{ form.stock_uom }}
                  <template v-if="stockFor(shop.name)?.low"> · {{ t('products.low') }}</template>
                </div>
              </div>
              <label class="text-xs text-slate-600">
                {{ t('products.reorderLevel') }}
                <input v-model="form.reorder[shop.name].level" type="number" min="0" step="any" dir="ltr" class="mt-1 block w-28 rounded-lg border border-slate-300 px-2 py-2 text-base" />
              </label>
              <label class="text-xs text-slate-600">
                {{ t('products.reorderQty') }}
                <input v-model="form.reorder[shop.name].qty" type="number" min="0" step="any" dir="ltr" class="mt-1 block w-28 rounded-lg border border-slate-300 px-2 py-2 text-base" />
              </label>
            </div>
          </div>
          <p class="mt-3 text-xs text-slate-500">{{ t('products.stockNote') }}</p>
        </section>
      </fieldset>

      <div v-if="!readOnly" class="flex justify-end">
        <button type="submit" :disabled="saving" class="rounded-lg bg-brand-600 px-5 py-2.5 text-base font-semibold text-white hover:bg-brand-700 disabled:opacity-60">
          {{ saving ? t('products.saving') : t('products.save') }}
        </button>
      </div>
    </form>
  </div>
</template>
