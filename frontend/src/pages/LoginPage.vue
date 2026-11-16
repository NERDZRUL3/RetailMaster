<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { ApiError } from '@/api'
import { branding } from '@/branding'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import { homePath, login } from '@/session'

const { t } = useI18n()
const router = useRouter()

const email = ref('')
const password = ref('')
const busy = ref(false)
const errorKey = ref<string | null>(null)

async function submit() {
  busy.value = true
  errorKey.value = null
  try {
    const context = await login(email.value.trim(), password.value)
    await router.push(homePath(context?.home))
  } catch (error) {
    const rejected = error instanceof ApiError && (error.status === 401 || error.status === 403)
    errorKey.value = rejected ? 'auth.wrongCredentials' : 'auth.serverError'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="flex min-h-screen flex-col items-center justify-center bg-slate-50 px-4 py-8">
    <div class="w-full max-w-sm">
      <div class="mb-4 flex justify-end">
        <LanguageSwitcher />
      </div>

      <div class="mb-6 flex flex-col items-center text-center">
        <img
          v-if="branding.logo"
          :src="branding.logo"
          :alt="branding.app_name"
          class="h-28 w-28 rounded-full bg-white object-contain shadow-sm ring-1 ring-slate-200"
        />
        <p class="mt-3 text-xl font-semibold text-brand-700">
          <bdi>{{ branding.app_name }}</bdi>
        </p>
      </div>

      <form class="rounded-xl border border-t-4 border-slate-200 border-t-brand bg-white p-6 shadow-sm" @submit.prevent="submit">
        <h1 class="text-xl font-semibold text-slate-900">{{ t('auth.title') }}</h1>
        <p class="mt-1 text-sm text-slate-500">{{ t('auth.subtitle') }}</p>

        <label class="mt-5 block text-sm font-medium text-slate-700" for="login-email">{{ t('auth.email') }}</label>
        <input
          id="login-email"
          v-model="email"
          type="email"
          dir="ltr"
          required
          autocomplete="username"
          class="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-base text-slate-900"
        />

        <label class="mt-4 block text-sm font-medium text-slate-700" for="login-password">
          {{ t('auth.password') }}
        </label>
        <input
          id="login-password"
          v-model="password"
          type="password"
          dir="ltr"
          required
          autocomplete="current-password"
          class="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-base text-slate-900"
        />

        <p v-if="errorKey" class="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
          {{ t(errorKey) }}
        </p>

        <button
          type="submit"
          :disabled="busy"
          class="mt-5 w-full rounded-lg bg-brand-600 px-4 py-2.5 text-base font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
        >
          {{ busy ? t('auth.signingIn') : t('auth.signIn') }}
        </button>
      </form>
    </div>
  </div>
</template>
