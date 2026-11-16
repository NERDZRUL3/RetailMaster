<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { logout } from '@/session'

const { t } = useI18n()
const router = useRouter()

async function signOut() {
  await logout()
  await router.push('/login')
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-slate-50 px-4">
    <div class="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 text-center">
      <h1 class="text-xl font-semibold text-slate-900">{{ t('noAccess.title') }}</h1>
      <p class="mt-2 text-sm text-slate-600">{{ t('noAccess.body') }}</p>
      <button
        type="button"
        class="mt-5 rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
        @click="signOut"
      >
        {{ t('auth.signOut') }}
      </button>
    </div>
  </div>
</template>
