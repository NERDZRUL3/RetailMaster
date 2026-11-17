<script setup lang="ts">
// Forgotten password: an email link (when the site can send email) or one of
// the owner's printed recovery codes.
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import { branding } from '@/branding'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import ThemeSwitcher from '@/components/ThemeSwitcher.vue'
import { recoveryApi } from '@/recovery'

const { t } = useI18n()

type Way = 'email' | 'code'
const emailAvailable = ref(false)
const way = ref<Way>('code')
onMounted(async () => {
  try {
    emailAvailable.value = (await recoveryApi.options()).email
    if (emailAvailable.value) way.value = 'email'
  } catch {
    // Codes still work without this.
  }
})

const account = ref('')
const code = ref('')
const password = ref('')
const confirm = ref('')
const busy = ref(false)
const error = ref('')
const done = ref<'email' | 'code' | null>(null)
const remaining = ref(0)

const mismatch = computed(() => !!confirm.value && password.value !== confirm.value)

function failure(err: unknown) {
  if (err instanceof ApiError && err.status === 429) return t('recover.tooMany')
  if (err instanceof ApiError && err.status >= 500) return t('auth.serverError')
  return err instanceof ApiError ? err.message : t('auth.serverError')
}

async function sendLink() {
  busy.value = true
  error.value = ''
  try {
    await recoveryApi.emailLink(account.value.trim())
    done.value = 'email'
  } catch (err) {
    error.value = failure(err)
  } finally {
    busy.value = false
  }
}

async function useCode() {
  if (mismatch.value) return
  busy.value = true
  error.value = ''
  try {
    const result = await recoveryApi.resetWithCode(account.value.trim(), code.value, password.value)
    remaining.value = result.remaining
    done.value = 'code'
    password.value = confirm.value = code.value = ''
  } catch (err) {
    error.value = failure(err)
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

    <div class="mx-auto flex w-full max-w-[420px] flex-1 flex-col justify-center py-10">
      <div class="flex flex-col items-center text-center">
        <p class="text-[15px] font-medium text-slate-500"><bdi>{{ branding.app_name }}</bdi></p>
        <h1 class="mt-1 text-[30px] leading-tight font-semibold tracking-tight text-slate-900">{{ t('recover.title') }}</h1>
        <p class="mt-2 text-[15px] text-slate-500">{{ t('recover.subtitle') }}</p>
      </div>

      <div class="card-pad animate-rise mt-8">
        <!-- Done -->
        <div v-if="done" class="text-center" role="status">
          <p class="notice-ok">{{ done === 'email' ? t('recover.emailSent') : t('recover.passwordSet') }}</p>
          <p v-if="done === 'code'" class="hint mt-3">{{ t('recover.codesLeft', { count: remaining }, remaining) }}</p>
          <RouterLink to="/login" class="btn-primary btn-lg mt-6 w-full">{{ t('recover.backToSignIn') }}</RouterLink>
        </div>

        <template v-else>
          <div v-if="emailAvailable" class="segmented mb-5 grid w-full grid-cols-2" role="group" :aria-label="t('recover.how')">
            <button type="button" class="segment h-9" :aria-pressed="way === 'email'" @click="way = 'email'">{{ t('recover.byEmail') }}</button>
            <button type="button" class="segment h-9" :aria-pressed="way === 'code'" @click="way = 'code'">{{ t('recover.byCode') }}</button>
          </div>

          <!-- Email link -->
          <form v-if="way === 'email'" @submit.prevent="sendLink">
            <p class="hint mb-4">{{ t('recover.emailHint') }}</p>
            <label class="label" for="recover-email">{{ t('recover.email') }}</label>
            <input id="recover-email" v-model="account" type="email" dir="ltr" required autocomplete="email" class="field" />
            <p v-if="error" class="notice-error mt-4" role="alert">{{ error }}</p>
            <button type="submit" :disabled="busy" class="btn-primary btn-lg mt-6 w-full">
              {{ busy ? t('recover.sending') : t('recover.sendLink') }}
            </button>
          </form>

          <!-- Recovery code -->
          <form v-else @submit.prevent="useCode">
            <p class="hint mb-4">{{ t('recover.codeHint') }}</p>
            <label class="label" for="recover-account">{{ t('auth.email') }}</label>
            <input
              id="recover-account"
              v-model="account"
              type="text"
              dir="ltr"
              required
              autocapitalize="none"
              spellcheck="false"
              autocomplete="username"
              class="field"
            />
            <label class="label mt-4" for="recover-code">{{ t('recover.code') }}</label>
            <input
              id="recover-code"
              v-model="code"
              type="text"
              dir="ltr"
              required
              autocapitalize="characters"
              spellcheck="false"
              autocomplete="one-time-code"
              placeholder="XXXX-XXXX-XXXX"
              class="field font-mono tracking-wider uppercase"
            />
            <label class="label mt-4" for="recover-password">{{ t('recover.newPassword') }}</label>
            <input id="recover-password" v-model="password" type="password" dir="ltr" required minlength="8" autocomplete="new-password" class="field" />
            <label class="label mt-4" for="recover-confirm">{{ t('recover.confirmPassword') }}</label>
            <input id="recover-confirm" v-model="confirm" type="password" dir="ltr" required autocomplete="new-password" class="field" />
            <p v-if="mismatch" class="mt-2 text-[13px] text-red-700">{{ t('recover.mismatch') }}</p>
            <p v-if="error" class="notice-error mt-4" role="alert">{{ error }}</p>
            <button type="submit" :disabled="busy || mismatch" class="btn-primary btn-lg mt-6 w-full">
              {{ busy ? t('recover.saving') : t('recover.setPassword') }}
            </button>
          </form>

          <RouterLink to="/login" class="link mt-5 block text-center text-[14px]">{{ t('recover.backToSignIn') }}</RouterLink>
        </template>
      </div>
    </div>
  </div>
</template>
