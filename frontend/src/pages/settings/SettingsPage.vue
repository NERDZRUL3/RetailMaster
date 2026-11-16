<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api, ApiError } from '@/api'
import { applyBranding, type Branding, readableShade } from '@/branding'
import { applyLocale, type Locale, LOCALES, pickLocale } from '@/i18n'

interface SettingsPayload {
  app_name: string
  logo: string | null
  brand_color: string
  default_language: Locale
  enable_en: number
  enable_fr: number
  enable_ar: number
  branding: Branding
}

const API = 'retail_management.api.settings'
const { t, locale } = useI18n()

const loaded = ref(false)
const busy = ref<'save' | 'upload' | null>(null)
const message = ref<{ kind: 'ok' | 'error'; text: string } | null>(null)

const form = reactive({
  app_name: '',
  logo: null as string | null,
  brand_color: '#0f766e',
  default_language: 'en' as Locale,
  languages: { en: true, fr: true, ar: true } as Record<Locale, boolean>,
})

const strongPreview = computed(() => readableShade(form.brand_color))
const colorAdjusted = computed(() => strongPreview.value.toLowerCase() !== form.brand_color.toLowerCase())
const enabledLanguages = computed(() => LOCALES.filter((code) => form.languages[code]))

function load(payload: SettingsPayload) {
  form.app_name = payload.app_name
  form.logo = payload.branding.logo
  form.brand_color = payload.brand_color || payload.branding.brand_color
  form.default_language = payload.default_language
  form.languages = { en: !!payload.enable_en, fr: !!payload.enable_fr, ar: !!payload.enable_ar }
  // A site that never saved settings has nothing ticked: show all as on.
  if (!enabledLanguages.value.length) form.languages = { en: true, fr: true, ar: true }
  applyBranding(payload.branding)
  // If the language on screen was just switched off, move to an allowed one.
  if (!payload.branding.languages.includes(locale.value as Locale)) {
    applyLocale(pickLocale(payload.branding.languages, payload.branding.default_language))
  }
}

function fail(error: unknown) {
  const text = error instanceof ApiError ? error.message : String(error)
  message.value = { kind: 'error', text: t('settings.error', { message: text }) }
}

onMounted(async () => {
  try {
    load(await api.get<SettingsPayload>(`${API}.get_settings`))
  } catch (error) {
    fail(error)
  } finally {
    loaded.value = true
  }
})

async function save() {
  busy.value = 'save'
  message.value = null
  try {
    if (!form.languages[form.default_language]) form.default_language = enabledLanguages.value[0]
    load(
      await api.post<SettingsPayload>(`${API}.save_settings`, {
        app_name: form.app_name,
        brand_color: form.brand_color,
        default_language: form.default_language,
        enable_en: form.languages.en ? 1 : 0,
        enable_fr: form.languages.fr ? 1 : 0,
        enable_ar: form.languages.ar ? 1 : 0,
      }),
    )
    message.value = { kind: 'ok', text: t('settings.saved') }
  } catch (error) {
    fail(error)
  } finally {
    busy.value = null
  }
}

async function uploadLogo(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  busy.value = 'upload'
  message.value = null
  try {
    load(await api.upload<SettingsPayload>(`${API}.upload_logo`, file))
    message.value = { kind: 'ok', text: t('settings.saved') }
  } catch (error) {
    fail(error)
  } finally {
    busy.value = null
  }
}

async function removeLogo() {
  busy.value = 'upload'
  message.value = null
  try {
    load(await api.post<SettingsPayload>(`${API}.remove_logo`))
  } catch (error) {
    fail(error)
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <div class="mx-auto max-w-3xl">
    <h1 class="text-2xl font-semibold text-slate-900">{{ t('settings.title') }}</h1>
    <p class="mt-1 text-sm text-slate-500">{{ t('settings.subtitle') }}</p>

    <p
      v-if="message"
      class="mt-4 rounded-lg px-4 py-3 text-sm"
      :class="message.kind === 'ok' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'"
      role="status"
    >
      {{ message.text }}
    </p>

    <form v-if="loaded" class="mt-6 space-y-6" @submit.prevent="save">
      <!-- Branding -->
      <section class="rounded-xl border border-slate-200 bg-white p-5">
        <h2 class="text-lg font-semibold text-slate-900">{{ t('settings.branding') }}</h2>

        <label class="mt-4 block text-sm font-medium text-slate-700" for="app-name">{{ t('settings.appName') }}</label>
        <input
          id="app-name"
          v-model="form.app_name"
          type="text"
          dir="auto"
          maxlength="140"
          class="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-base"
        />
        <p class="mt-1 text-xs text-slate-500">{{ t('settings.appNameHint') }}</p>

        <div class="mt-5 text-sm font-medium text-slate-700">{{ t('settings.logo') }}</div>
        <div class="mt-2 flex flex-wrap items-center gap-4">
          <div class="flex h-20 w-20 items-center justify-center rounded-full bg-slate-50 ring-1 ring-slate-200">
            <img v-if="form.logo" :src="form.logo" alt="" class="h-20 w-20 rounded-full object-contain" />
            <span v-else class="px-2 text-center text-xs text-slate-400">{{ t('settings.noLogo') }}</span>
          </div>
          <label
            class="cursor-pointer rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
            :class="{ 'pointer-events-none opacity-60': busy }"
          >
            {{ busy === 'upload' ? t('settings.uploading') : form.logo ? t('settings.replaceLogo') : t('settings.uploadLogo') }}
            <input type="file" accept="image/png,image/jpeg,image/webp" class="sr-only" @change="uploadLogo" />
          </label>
          <button
            v-if="form.logo"
            type="button"
            class="rounded-lg px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50"
            :disabled="!!busy"
            @click="removeLogo"
          >
            {{ t('settings.removeLogo') }}
          </button>
        </div>
        <p class="mt-2 text-xs text-slate-500">{{ t('settings.logoHint') }}</p>

        <label class="mt-5 block text-sm font-medium text-slate-700" for="brand-color">{{ t('settings.color') }}</label>
        <div class="mt-1 flex items-center gap-3">
          <input
            v-model="form.brand_color"
            type="color"
            class="h-11 w-14 cursor-pointer rounded-lg border border-slate-300 bg-white p-1"
            :aria-label="t('settings.color')"
          />
          <input
            id="brand-color"
            v-model="form.brand_color"
            type="text"
            dir="ltr"
            pattern="#[0-9a-fA-F]{6}"
            class="w-32 rounded-lg border border-slate-300 px-3 py-2.5 font-mono text-base"
          />
        </div>
        <p class="mt-1 text-xs text-slate-500">{{ t('settings.colorHint') }}</p>

        <!-- Live preview with the colours as they will be applied. -->
        <div class="mt-4 rounded-lg border border-slate-200 p-4" :style="{ borderTop: `4px solid ${form.brand_color}` }">
          <div class="text-xs font-medium uppercase tracking-wide text-slate-500">{{ t('settings.preview') }}</div>
          <div class="mt-3 flex flex-wrap items-center gap-3">
            <span class="inline-flex items-center gap-2 text-sm text-slate-600">
              <span class="h-5 w-5 rounded-full" :style="{ backgroundColor: form.brand_color }" />
              {{ t('settings.accent') }}
            </span>
            <span
              class="rounded-lg px-4 py-2 text-sm font-semibold text-white"
              :style="{ backgroundColor: strongPreview }"
            >
              {{ t('settings.button') }}
            </span>
            <span v-if="colorAdjusted" class="font-mono text-xs text-slate-500" dir="ltr">{{ strongPreview }}</span>
          </div>
        </div>
      </section>

      <!-- Languages -->
      <section class="rounded-xl border border-slate-200 bg-white p-5">
        <h2 class="text-lg font-semibold text-slate-900">{{ t('settings.languages') }}</h2>
        <p class="mt-1 text-xs text-slate-500">{{ t('settings.languagesHint') }}</p>
        <div class="mt-3 flex flex-wrap gap-4">
          <label v-for="code in LOCALES" :key="code" class="inline-flex items-center gap-2 text-sm text-slate-700">
            <input
              v-model="form.languages[code]"
              type="checkbox"
              class="h-4 w-4 accent-brand-600"
              :disabled="form.languages[code] && enabledLanguages.length === 1"
            />
            {{ t(`language.${code}`) }}
          </label>
        </div>

        <label class="mt-4 block text-sm font-medium text-slate-700" for="default-language">
          {{ t('settings.defaultLanguage') }}
        </label>
        <select
          id="default-language"
          v-model="form.default_language"
          class="mt-1 rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-base"
        >
          <option v-for="code in enabledLanguages" :key="code" :value="code">{{ t(`language.${code}`) }}</option>
        </select>
      </section>

      <div class="flex justify-end">
        <button
          type="submit"
          :disabled="!!busy"
          class="rounded-lg bg-brand-600 px-5 py-2.5 text-base font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
        >
          {{ busy === 'save' ? t('settings.saving') : t('settings.save') }}
        </button>
      </div>
    </form>
  </div>
</template>
