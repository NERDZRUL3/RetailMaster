<script setup lang="ts">
// The owner's shops: add one by name (its stock location comes with it) and
// switch shops off or back on. Hidden for anyone who may not set up shops.
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import { type ShopRow, shopsApi } from '@/shops'

const { t } = useI18n()
withDefaults(defineProps<{ heading?: boolean }>(), { heading: true })

const shops = ref<ShopRow[] | null>(null)
const companies = ref<string[]>([])
const name = ref('')
const company = ref('')
const busy = ref(false)
const error = ref('')
const info = ref('')

onMounted(async () => {
  try {
    const setup = await shopsApi.setup()
    shops.value = setup.shops
    companies.value = setup.companies
    company.value = setup.companies[0] ?? ''
  } catch {
    shops.value = null
  }
})

const canAdd = computed(() => !!name.value.trim() && !!company.value && !busy.value)

async function add() {
  if (!canAdd.value) return
  busy.value = true
  error.value = info.value = ''
  try {
    const shop = await shopsApi.create(name.value, company.value)
    shops.value = [...(shops.value ?? []), shop].sort((a, b) => a.shop_name.localeCompare(b.shop_name))
    info.value = t('shopSetup.created', { name: shop.shop_name })
    name.value = ''
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    busy.value = false
  }
}

// Renaming one shop at a time, in place.
const renaming = ref<string | null>(null)
const renameTo = ref('')
function startRename(shop: ShopRow) {
  renaming.value = shop.name
  renameTo.value = shop.shop_name
  error.value = info.value = ''
}
async function saveRename(shop: ShopRow) {
  const next = renameTo.value.trim()
  if (!next || busy.value) return
  if (next === shop.shop_name) {
    renaming.value = null
    return
  }
  busy.value = true
  error.value = ''
  try {
    const updated = await shopsApi.rename(shop.name, next)
    Object.assign(shop, updated)
    shops.value?.sort((a, b) => a.shop_name.localeCompare(b.shop_name))
    info.value = t('shopSetup.renamed', { name: updated.shop_name })
    renaming.value = null
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    busy.value = false
  }
}

async function toggle(shop: ShopRow) {
  error.value = info.value = ''
  try {
    const updated = await shopsApi.setEnabled(shop.name, !shop.enabled)
    Object.assign(shop, updated)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : String(err)
  }
}
</script>

<template>
  <section v-if="shops" class="card-pad">
    <h2 v-if="heading" class="section-title">{{ t('shopSetup.title') }}</h2>
    <p class="hint" :class="{ 'mt-1': heading }">{{ t('shopSetup.hint') }}</p>

    <ul v-if="shops.length" class="list stagger mt-4">
      <li v-for="shop in shops" :key="shop.name" class="flex flex-wrap items-center gap-3 px-4 py-3" :class="shop.enabled ? '' : 'opacity-60'">
        <!-- Renaming this shop -->
        <form v-if="renaming === shop.name" class="flex min-w-0 flex-1 flex-wrap gap-2" @submit.prevent="saveRename(shop)">
          <input
            v-model="renameTo"
            maxlength="140"
            dir="auto"
            autofocus
            class="field min-w-0 flex-1 py-2 text-[15px]"
            :aria-label="t('shopSetup.name')"
            @keydown.esc.prevent="renaming = null"
          />
          <button type="submit" class="btn-primary px-4 py-2" :disabled="!renameTo.trim() || busy">{{ t('shopSetup.saveName') }}</button>
          <button type="button" class="btn-secondary px-4 py-2" @click="renaming = null">{{ t('recovery.cancel') }}</button>
        </form>
        <template v-else>
          <span class="min-w-0 flex-1">
            <span class="block font-medium text-slate-900"><bdi>{{ shop.shop_name }}</bdi></span>
            <span class="block truncate text-[13px] text-slate-500">
              <bdi>{{ shop.company }}</bdi><template v-if="shop.warehouse"> · <bdi>{{ shop.warehouse }}</bdi></template>
            </span>
          </span>
          <span v-if="!shop.enabled" class="badge-warn">{{ t('shopSetup.off') }}</span>
          <button type="button" class="btn-quiet px-2.5 py-1 text-[13px]" @click="startRename(shop)">{{ t('shopSetup.rename') }}</button>
          <button type="button" class="btn-quiet px-2.5 py-1 text-[13px]" @click="toggle(shop)">
            {{ shop.enabled ? t('shopSetup.switchOff') : t('shopSetup.switchOn') }}
          </button>
        </template>
      </li>
    </ul>
    <p v-else class="notice-warn mt-4">{{ t('shopSetup.none') }}</p>

    <p v-if="!companies.length" class="notice-warn mt-4">{{ t('shopSetup.noCompany') }}</p>
    <form v-else class="mt-5 flex flex-wrap items-end gap-3" @submit.prevent="add">
      <div class="min-w-48 flex-1">
        <label class="label" for="new-shop">{{ t('shopSetup.name') }}</label>
        <input id="new-shop" v-model="name" maxlength="140" dir="auto" class="field" :placeholder="t('shopSetup.namePlaceholder')" />
      </div>
      <div v-if="companies.length > 1">
        <label class="label" for="new-shop-company">{{ t('shopSetup.company') }}</label>
        <select id="new-shop-company" v-model="company" class="field w-auto min-w-48">
          <option v-for="c in companies" :key="c" :value="c">{{ c }}</option>
        </select>
      </div>
      <button type="submit" class="btn-primary" :disabled="!canAdd">{{ busy ? t('shopSetup.creating') : t('shopSetup.add') }}</button>
    </form>

    <p v-if="info" class="notice-ok mt-4" role="status">{{ info }}</p>
    <p v-if="error" class="notice-error mt-4" role="alert">{{ error }}</p>
  </section>
</template>
