<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { ApiError } from '@/api'
import { branding } from '@/branding'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import ThemeSwitcher from '@/components/ThemeSwitcher.vue'
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
  <div class="flex min-h-screen flex-col px-5 py-6">
    <div class="flex justify-end gap-2">
      <ThemeSwitcher />
      <LanguageSwitcher />
    </div>

    <div class="mx-auto flex w-full max-w-[400px] flex-1 flex-col justify-center py-10">
      <div class="flex flex-col items-center text-center">
        <img
          v-if="branding.logo"
          :src="branding.logo"
          :alt="branding.app_name"
          class="h-24 w-24 rounded-full bg-white object-contain shadow-[0_8px_30px_rgb(0_0_0/0.12)]"
        />
        <p class="mt-4 text-[15px] font-medium text-slate-500">
          <bdi>{{ branding.app_name }}</bdi>
        </p>
        <h1 class="mt-1 text-[32px] leading-tight font-semibold tracking-tight text-slate-900">{{ t('auth.title') }}</h1>
        <p class="mt-2 text-[15px] text-slate-500">{{ t('auth.subtitle') }}</p>
      </div>

      <form class="card-pad animate-rise mt-8" @submit.prevent="submit">
        <label class="label" for="login-email">{{ t('auth.email') }}</label>
        <input
          id="login-email"
          v-model="email"
          type="text"
          autocapitalize="none"
          spellcheck="false"
          dir="ltr"
          required
          autocomplete="username"
          class="field"
        />

        <label class="label mt-4" for="login-password">{{ t('auth.password') }}</label>
        <input
          id="login-password"
          v-model="password"
          type="password"
          dir="ltr"
          required
          autocomplete="current-password"
          class="field"
        />

        <p v-if="errorKey" class="notice-error mt-4" role="alert">{{ t(errorKey) }}</p>

        <button type="submit" :disabled="busy" class="btn-primary btn-lg mt-6 w-full">
          {{ busy ? t('auth.signingIn') : t('auth.signIn') }}
        </button>
        <RouterLink to="/forgot" class="link mt-4 block text-center text-[14px]">{{ t('auth.forgot') }}</RouterLink>
      </form>
    </div>
  </div>
</template>
