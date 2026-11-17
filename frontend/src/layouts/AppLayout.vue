<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import BrandName from '@/components/BrandName.vue'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import ThemeSwitcher from '@/components/ThemeSwitcher.vue'
import { logout, session } from '@/session'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()

// Highlight the entry for its own page and its sub-pages (/products/<code>).
const isActive = (to: string) => route.path === to || route.path.startsWith(`${to}/`)

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
  <div class="min-h-screen">
    <header class="glass relative z-20 sm:sticky sm:top-0">
      <div class="mx-auto flex max-w-5xl flex-wrap items-center gap-x-5 gap-y-2 px-5 py-2.5">
        <RouterLink to="/" class="shrink-0" :aria-label="t('nav.home')">
          <BrandName class="text-[17px]" />
        </RouterLink>

        <nav class="order-last -mx-1 flex w-full gap-1 overflow-x-auto sm:order-none sm:w-auto" :aria-label="t('nav.main')">
          <RouterLink
            v-for="item in navigation"
            :key="item.to"
            :to="item.to"
            class="nav-link"
            :class="{ 'router-link-active': isActive(item.to) }"
            :aria-current="isActive(item.to) ? 'page' : undefined"
          >
            {{ item.label }}
          </RouterLink>
        </nav>

        <div class="ms-auto flex items-center gap-2">
          <ThemeSwitcher />
          <LanguageSwitcher />
          <div v-if="session.context" class="hidden ps-2 text-end leading-tight md:block">
            <div class="text-[13px] font-medium text-slate-900" dir="auto">{{ session.context.full_name }}</div>
            <div v-if="session.context.home" class="text-[12px] text-slate-500">
              {{ t(`roles.${session.context.home}`) }}
            </div>
          </div>
          <button type="button" class="btn-quiet py-1.5 text-[14px]" @click="signOut">
            {{ t('auth.signOut') }}
          </button>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-5xl px-5 pt-8 pb-16 sm:pt-12">
      <RouterView />
    </main>
  </div>
</template>
