<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import BrandName from '@/components/BrandName.vue'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import ThemeSwitcher from '@/components/ThemeSwitcher.vue'
import { logout, session } from '@/session'

const { t } = useI18n()
const router = useRouter()

// Each kind of user only gets the menu entries they can use.
const navigation = computed(() => {
  const items =
    session.context?.home === 'owner'
      ? [{ to: '/owner', label: t('nav.overview') }]
      : [{ to: '/shop', label: t('nav.myShop') }]
  if (session.context?.home === 'owner' || session.context?.home === 'manager') {
    items.push({ to: '/products', label: t('nav.products') })
  }
  if (session.context?.can_edit_settings) items.push({ to: '/settings', label: t('nav.settings') })
  return items
})

async function signOut() {
  await logout()
  await router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-slate-50 text-slate-900">
    <!-- Thin bar in the exact brand colour ties every page to the logo. -->
    <header class="sticky top-0 z-10 border-t-4 border-b border-t-brand border-b-slate-200 bg-white">
      <div class="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
        <BrandName class="text-lg" />

        <nav class="order-last flex w-full gap-1 sm:order-none sm:w-auto" :aria-label="t('nav.main')">
          <RouterLink
            v-for="item in navigation"
            :key="item.to"
            :to="item.to"
            class="rounded-md px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
            active-class="bg-brand-50 text-brand-ink"
          >
            {{ item.label }}
          </RouterLink>
        </nav>

        <div class="ms-auto flex items-center gap-3">
          <ThemeSwitcher />
          <LanguageSwitcher />
          <div v-if="session.context" class="hidden text-end leading-tight sm:block">
            <div class="text-sm font-medium" dir="auto">{{ session.context.full_name }}</div>
            <div v-if="session.context.home" class="text-xs text-slate-500">
              {{ t(`roles.${session.context.home}`) }}
            </div>
          </div>
          <button
            type="button"
            class="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
            @click="signOut"
          >
            {{ t('auth.signOut') }}
          </button>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-6xl px-4 py-6">
      <RouterView />
    </main>
  </div>
</template>
