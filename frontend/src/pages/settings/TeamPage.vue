<script setup lang="ts">
// The owner's team page: everyone's account, role, shops and sign-in details.
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import AppDialog from '@/components/AppDialog.vue'
import { shopsApi } from '@/shops'
import { type Account, type AccountForm, generatePassword, SHOP_TIERS, type Team, TIERS, usersApi } from '@/users'

const { t, locale } = useI18n()
const team = ref<Team | null>(null)
const loading = ref(false)
const error = ref('')
const info = ref('')
const query = ref('')
const showOff = ref(false)

const form = ref<AccountForm | null>(null)
const formError = ref('')
const saving = ref(false)
const showPassword = ref(false)
const isNew = computed(() => !form.value?.name)
const editingMe = computed(() => !!team.value?.users.find((u) => u.name === form.value?.name)?.me)

async function load() {
  loading.value = true
  error.value = ''
  try {
    team.value = await usersApi.list()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    loading.value = false
  }
}
onMounted(load)

const shopName = (name: string) => team.value?.shops.find((s) => s.name === name)?.shop_name ?? name
const visible = computed(() => {
  const q = query.value.trim().toLowerCase()
  return (team.value?.users ?? []).filter(
    (u) =>
      (showOff.value || u.enabled) &&
      (!q || [u.full_name, u.email, u.username].some((v) => v.toLowerCase().includes(q))),
  )
})
const offCount = computed(() => (team.value?.users ?? []).filter((u) => !u.enabled).length)

function initials(account: Account) {
  return account.full_name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join('')
}
function lastSeen(iso: string | null) {
  return iso ? new Date(iso).toLocaleString(locale.value, { dateStyle: 'medium', timeStyle: 'short' }) : t('team.never')
}

function open(account?: Account) {
  formError.value = ''
  info.value = ''
  form.value = account
    ? {
        name: account.name,
        email: account.email,
        first_name: account.first_name,
        last_name: account.last_name,
        username: account.username,
        tier: account.tier ?? 'cashier',
        shops: [...account.shops],
        enabled: account.enabled,
        password: '',
      }
    : {
        email: '',
        first_name: '',
        last_name: '',
        username: '',
        tier: 'cashier',
        shops: team.value?.shops.length === 1 ? [team.value.shops[0].name] : [],
        enabled: 1,
        password: generatePassword(),
      }
  showPassword.value = !account
}

function newPassword() {
  if (!form.value) return
  form.value.password = generatePassword()
  showPassword.value = true
}

const copied = ref(false)
async function copyPassword() {
  if (!form.value?.password) return
  try {
    await navigator.clipboard.writeText(form.value.password)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    // clipboard blocked: the password is visible to copy by hand
  }
}

const needsShops = computed(() => !!form.value && SHOP_TIERS.includes(form.value.tier))
const formValid = computed(
  () =>
    !!form.value &&
    form.value.first_name.trim() !== '' &&
    form.value.email.trim() !== '' &&
    (!needsShops.value || form.value.shops.length > 0) &&
    (!isNew.value || form.value.password.length >= 8),
)

async function save() {
  if (!form.value || !formValid.value || saving.value) return
  saving.value = true
  formError.value = ''
  const creating = isNew.value
  try {
    const saved = await usersApi.save({ ...form.value, shops: needsShops.value ? form.value.shops : [] })
    info.value = creating ? t('team.created', { name: saved.full_name }) : t('team.saved', { name: saved.full_name })
    form.value = null
    await load()
  } catch (err) {
    formError.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    saving.value = false
  }
}

// First shop, made from inside the dialog (only shown when there is none).
const newShop = ref('')
const creatingShop = ref(false)
async function createShop() {
  if (!newShop.value.trim() || creatingShop.value || !team.value) return
  creatingShop.value = true
  formError.value = ''
  try {
    const shop = await shopsApi.create(newShop.value)
    team.value.shops = [...team.value.shops, { name: shop.name, shop_name: shop.shop_name }]
    form.value?.shops.push(shop.name)
    newShop.value = ''
  } catch (err) {
    formError.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    creatingShop.value = false
  }
}

const TIER_BADGE: Record<string, string> = {
  owner: 'badge-brand',
  partner: 'badge-neutral',
  manager: 'badge-ok',
  cashier: 'badge-neutral',
}
</script>

<template>
  <div class="mx-auto max-w-4xl">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="page-title">{{ t('team.title') }}</h1>
        <p class="page-subtitle">{{ t('team.subtitle') }}</p>
      </div>
      <button type="button" class="btn-primary" :disabled="!team" @click="open()">+ {{ t('team.add') }}</button>
    </div>

    <p v-if="error" class="notice-error mt-6" role="alert">{{ error }}</p>
    <p v-if="info" class="notice-ok mt-6" role="status">{{ info }}</p>

    <div class="mt-6 flex flex-wrap items-center gap-3">
      <input v-model="query" type="search" dir="auto" class="field min-w-0 flex-1 bg-white text-[15px]" :placeholder="t('team.search')" :aria-label="t('team.search')" />
      <label v-if="offCount" class="flex items-center gap-2 text-[14px] text-slate-600">
        <input v-model="showOff" type="checkbox" class="h-4 w-4" />
        {{ t('team.showOff', { n: offCount }) }}
      </label>
    </div>

    <ul class="list stagger mt-4" :aria-busy="loading">
      <li v-for="u in visible" :key="u.name" class="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3.5" :class="u.enabled ? '' : 'opacity-60'">
        <span class="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-slate-100 text-[14px] font-semibold text-slate-700" aria-hidden="true">{{ initials(u) }}</span>
        <span class="min-w-0 flex-1">
          <span class="flex flex-wrap items-center gap-2">
            <span class="font-medium text-slate-900" dir="auto">{{ u.full_name }}</span>
            <span v-if="u.me" class="badge-neutral">{{ t('team.you') }}</span>
            <span v-if="!u.enabled" class="badge-warn">{{ t('team.off') }}</span>
          </span>
          <span class="block truncate text-[13px] text-slate-500" dir="ltr">
            {{ u.email }}<template v-if="u.username"> · @{{ u.username }}</template>
          </span>
          <span class="block text-[12px] text-slate-500">
            {{ u.shops.length ? u.shops.map(shopName).join(', ') : t('team.allShops') }} · {{ t('team.lastLogin', { when: lastSeen(u.last_login) }) }}
          </span>
        </span>
        <span v-if="u.tier" :class="TIER_BADGE[u.tier]">{{ t(`team.tiers.${u.tier}`) }}</span>
        <button type="button" class="btn-quiet px-2.5 py-1 text-[13px]" @click="open(u)">{{ t('team.edit') }}</button>
      </li>
    </ul>
    <p v-if="!loading && team && !visible.length" class="hint mt-6 text-center">{{ t('team.empty') }}</p>

    <AppDialog v-if="form" wide :title="isNew ? t('team.add') : t('team.editTitle')" @close="form = null">
      <p v-if="formError" class="notice-error mb-4" role="alert">{{ formError }}</p>

      <div class="grid gap-4 sm:grid-cols-2">
        <div>
          <label class="label" for="acc-first">{{ t('team.firstName') }}</label>
          <input id="acc-first" v-model="form.first_name" autofocus maxlength="100" dir="auto" class="field text-[15px]" />
        </div>
        <div>
          <label class="label" for="acc-last">{{ t('team.lastName') }}</label>
          <input id="acc-last" v-model="form.last_name" maxlength="100" dir="auto" class="field text-[15px]" />
        </div>
        <div>
          <label class="label" for="acc-email">{{ t('team.email') }}</label>
          <input id="acc-email" v-model="form.email" type="email" maxlength="140" dir="ltr" autocomplete="off" class="field text-[15px]" />
        </div>
        <div>
          <label class="label" for="acc-username">{{ t('team.username') }}</label>
          <input id="acc-username" v-model="form.username" maxlength="60" dir="ltr" autocomplete="off" autocapitalize="none" class="field text-[15px]" :placeholder="t('team.optional')" />
        </div>
      </div>
      <p class="hint mt-2">{{ team?.username_login ? t('team.signInHint') : t('team.signInEmailOnly') }}</p>

      <fieldset class="mt-5">
        <legend class="label">{{ t('team.role') }}</legend>
        <div class="grid gap-2 sm:grid-cols-2">
          <label
            v-for="tier in TIERS"
            :key="tier"
            class="flex cursor-pointer gap-3 rounded-xl border p-3"
            :class="form.tier === tier ? 'border-brand-600 bg-brand-tint' : 'border-[var(--hairline)]'"
          >
            <input v-model="form.tier" type="radio" name="tier" :value="tier" class="mt-1" :disabled="editingMe" />
            <span>
              <span class="block font-medium text-slate-900">{{ t(`team.tiers.${tier}`) }}</span>
              <span class="block text-[13px] text-slate-500">{{ t(`team.tierHelp.${tier}`) }}</span>
            </span>
          </label>
        </div>
        <p v-if="editingMe" class="hint mt-2">{{ t('team.ownRole') }}</p>
      </fieldset>

      <fieldset v-if="needsShops" class="mt-5">
        <legend class="label">{{ t('team.shops') }}</legend>
        <div v-if="team?.shops.length" class="flex flex-wrap gap-2">
          <label
            v-for="s in team.shops"
            :key="s.name"
            class="flex cursor-pointer items-center gap-2 rounded-full border px-3 py-1.5 text-[14px] transition-colors"
            :class="form.shops.includes(s.name) ? 'border-brand-600 bg-brand-tint text-brand-ink' : 'border-[var(--hairline)] text-slate-700'"
          >
            <input v-model="form.shops" type="checkbox" :value="s.name" class="check h-4 w-4" />
            <bdi>{{ s.shop_name }}</bdi>
          </label>
        </div>
        <!-- No shop exists yet: make the first one without leaving the dialog -->
        <div v-else class="rounded-xl bg-amber-50 p-3">
          <p class="text-[14px] text-amber-900">{{ t('team.noShopsYet') }}</p>
          <div class="mt-3 flex flex-wrap gap-2">
            <input
              v-model="newShop"
              maxlength="140"
              dir="auto"
              class="field min-w-0 flex-1 bg-white text-[15px]"
              :placeholder="t('shopSetup.namePlaceholder')"
              :aria-label="t('shopSetup.name')"
              @keydown.enter.prevent="createShop"
            />
            <button type="button" class="btn-primary" :disabled="!newShop.trim() || creatingShop" @click="createShop">
              {{ creatingShop ? t('shopSetup.creating') : t('shopSetup.add') }}
            </button>
          </div>
        </div>
        <p v-if="team?.shops.length && !form.shops.length" class="mt-2 text-[13px] text-red-600">{{ t('team.needShop') }}</p>
      </fieldset>

      <div class="mt-5">
        <label class="label" for="acc-password">{{ isNew ? t('team.password') : t('team.newPassword') }}</label>
        <div class="flex flex-wrap gap-2">
          <input
            id="acc-password"
            v-model="form.password"
            :type="showPassword ? 'text' : 'password'"
            dir="ltr"
            autocomplete="new-password"
            class="field min-w-0 flex-1 font-mono text-[15px]"
            :placeholder="isNew ? '' : t('team.keepPassword')"
          />
          <button type="button" class="btn-secondary px-3" @click="showPassword = !showPassword">{{ showPassword ? t('team.hide') : t('team.show') }}</button>
          <button type="button" class="btn-secondary px-3" @click="newPassword">{{ t('team.generate') }}</button>
          <button v-if="form.password" type="button" class="btn-secondary px-3" @click="copyPassword">{{ copied ? t('team.copied') : t('team.copy') }}</button>
        </div>
        <p class="hint mt-2">{{ isNew ? t('team.passwordHint') : t('team.passwordChangeHint') }}</p>
      </div>

      <label v-if="!isNew && !editingMe" class="mt-5 flex items-center gap-2 text-[15px] text-slate-700">
        <input v-model="form.enabled" type="checkbox" :true-value="1" :false-value="0" class="h-4 w-4" />
        {{ t('team.active') }}
      </label>
      <p v-if="!isNew && !form.enabled" class="hint mt-1">{{ t('team.offHint') }}</p>

      <div class="mt-6 grid grid-cols-[auto_1fr] gap-2">
        <button type="button" class="btn-secondary btn-lg" @click="form = null">{{ t('categories.cancel') }}</button>
        <button type="button" class="btn-primary btn-lg" :disabled="!formValid || saving" @click="save">
          {{ saving ? t('pos.saving') : isNew ? t('team.create') : t('categories.save') }}
        </button>
      </div>
    </AppDialog>
  </div>
</template>
