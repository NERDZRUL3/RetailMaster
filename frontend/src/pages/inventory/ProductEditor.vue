<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import { type FormOptions, formatQty, inventoryApi, type Product } from '@/inventory'

const props = defineProps<{ code?: string }>()
const { t, locale } = useI18n()
const router = useRouter()
const route = useRoute()
// Opened from receiving: ?barcode= to prefill, ?return= to go back after creating.
const returnTo = typeof route.query.return === 'string' && route.query.return.startsWith('/') ? route.query.return : ''

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
      if (typeof route.query.barcode === 'string' && route.query.barcode) form.barcodes = [route.query.barcode]
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
    if (isNew.value && returnTo) await router.push({ path: returnTo, query: { added: saved.item_code } })
    else if (isNew.value) await router.replace(`/products/${encodeURIComponent(saved.item_code)}`)
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
    <RouterLink to="/products" class="link inline-flex items-center gap-1 text-[15px]">
      <svg viewBox="0 0 24 24" class="h-4 w-4 rtl:rotate-180" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true">
        <path d="m15 6-6 6 6 6" />
      </svg>
      {{ t('products.back') }}
    </RouterLink>
    <h1 class="page-title mt-3" dir="auto">
      {{ isNew ? t('products.new') : form.item_name || t('products.title') }}
    </h1>

    <p
      v-if="message"
      class="mt-6"
      :class="message.kind === 'ok' ? 'notice-ok' : 'notice-error'"
      role="status"
    >
      {{ message.text }}
    </p>

    <form v-if="loaded && options" class="mt-8 space-y-6" @submit.prevent="save">
      <fieldset :disabled="readOnly || saving" class="space-y-6">
        <section class="card-pad">
          <h2 class="section-title">{{ t('products.details') }}</h2>

          <label class="label mt-5" for="p-name">{{ t('products.name') }}</label>
          <input id="p-name" v-model="form.item_name" required dir="auto" maxlength="140" class="field" />

          <div class="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label class="label" for="p-code">{{ t('products.code') }}</label>
              <input
                id="p-code"
                v-model="form.item_code"
                dir="ltr"
                :disabled="!isNew"
                :placeholder="t('products.codeAuto')"
                class="field"
              />
            </div>
            <div>
              <label class="label" for="p-price">
                {{ t('products.price') }}<template v-if="options.currency"> ({{ options.currency }})</template>
              </label>
              <input id="p-price" v-model="form.price" type="number" min="0" step="0.01" dir="ltr" class="field tabular-nums" />
            </div>
            <div>
              <label class="label" for="p-group">{{ t('products.category') }}</label>
              <select id="p-group" v-model="form.item_group" class="field">
                <option v-for="g in options.item_groups" :key="g" :value="g">{{ g }}</option>
              </select>
            </div>
            <div>
              <label class="label" for="p-uom">{{ t('products.unit') }}</label>
              <select id="p-uom" v-model="form.stock_uom" :disabled="!isNew" class="field">
                <option v-for="u in options.uoms" :key="u" :value="u">{{ u }}</option>
              </select>
            </div>
            <div v-if="options.brands.length">
              <label class="label" for="p-brand">{{ t('products.brand') }}</label>
              <select id="p-brand" v-model="form.brand" class="field">
                <option value="">—</option>
                <option v-for="b in options.brands" :key="b" :value="b">{{ b }}</option>
              </select>
            </div>
          </div>

          <label class="label mt-4" for="p-desc">{{ t('products.description') }}</label>
          <textarea id="p-desc" v-model="form.description" rows="2" dir="auto" class="field" />

          <label class="mt-5 inline-flex items-center gap-2.5 text-[15px] text-slate-700">
            <input v-model="form.disabled" type="checkbox" class="check" />
            {{ t('products.inactiveLabel') }}
          </label>
        </section>

        <section class="card-pad">
          <h2 class="section-title">{{ t('products.barcodes') }}</h2>
          <p class="hint mt-1">{{ t('products.barcodesHint') }}</p>
          <div class="mt-4 flex gap-2">
            <input
              v-model="newBarcode"
              dir="ltr"
              :placeholder="t('products.scanOrType')"
              :aria-label="t('products.scanOrType')"
              class="field min-w-0 flex-1 font-mono"
              @keydown.enter.prevent="addBarcode"
            />
            <button type="button" class="btn-secondary" @click="addBarcode">
              {{ t('products.add') }}
            </button>
          </div>
          <ul v-if="form.barcodes.length" class="mt-4 flex flex-wrap gap-2">
            <li
              v-for="b in form.barcodes"
              :key="b"
              class="inline-flex items-center gap-1 rounded-full bg-slate-100 py-1 ps-3.5 pe-1 font-mono text-[14px] text-slate-700"
              dir="ltr"
            >
              {{ b }}
              <button
                type="button"
                class="grid h-6 w-6 place-items-center rounded-full text-slate-400 transition hover:bg-slate-200 hover:text-red-700"
                :aria-label="t('products.removeBarcode', { code: b })"
                @click="removeBarcode(b)"
              >
                ×
              </button>
            </li>
          </ul>
        </section>

        <section class="card-pad">
          <h2 class="section-title">{{ t('products.stockAndReorder') }}</h2>
          <p class="hint mt-1">{{ t('products.reorderHint') }}</p>
          <div class="mt-4 space-y-3">
            <div
              v-for="shop in options.shops"
              :key="shop.name"
              class="grid items-end gap-4 rounded-2xl bg-slate-50 p-4 sm:grid-cols-[1fr_auto_auto]"
            >
              <div>
                <div class="text-[15px] font-semibold text-slate-900"><bdi>{{ shop.shop_name }}</bdi></div>
                <div class="mt-0.5 text-[13px]" :class="stockFor(shop.name)?.low ? 'font-medium text-amber-800' : 'text-slate-500'">
                  {{ t('products.inStock') }}: {{ formatQty(stockFor(shop.name)?.qty ?? 0, locale) }} {{ form.stock_uom }}
                  <template v-if="stockFor(shop.name)?.low"> · {{ t('products.low') }}</template>
                </div>
              </div>
              <label class="label mb-0">
                {{ t('products.reorderLevel') }}
                <input v-model="form.reorder[shop.name].level" type="number" min="0" step="any" dir="ltr" class="field mt-1.5 w-32 bg-white py-2.5 tabular-nums" />
              </label>
              <label class="label mb-0">
                {{ t('products.reorderQty') }}
                <input v-model="form.reorder[shop.name].qty" type="number" min="0" step="any" dir="ltr" class="field mt-1.5 w-32 bg-white py-2.5 tabular-nums" />
              </label>
            </div>
          </div>
          <p class="hint mt-4">{{ t('products.stockNote') }}</p>
        </section>
      </fieldset>

      <div v-if="!readOnly" class="flex justify-end">
        <button type="submit" :disabled="saving" class="btn-primary btn-lg">
          {{ saving ? t('products.saving') : t('products.save') }}
        </button>
      </div>
    </form>
  </div>
</template>
