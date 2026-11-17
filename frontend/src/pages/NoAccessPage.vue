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
  <div class="flex min-h-screen items-center justify-center px-5">
    <div class="card-pad animate-pop w-full max-w-sm text-center">
      <h1 class="section-title text-[22px]">{{ t('noAccess.title') }}</h1>
      <p class="mt-2 text-[15px] text-slate-500">{{ t('noAccess.body') }}</p>
      <button type="button" class="btn-secondary mt-6" @click="signOut">
        {{ t('auth.signOut') }}
      </button>
    </div>
  </div>
</template>
