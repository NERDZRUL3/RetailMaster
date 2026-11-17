<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import BrandName from '@/components/BrandName.vue'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import ThemeSwitcher from '@/components/ThemeSwitcher.vue'
import { dashboardApi } from '@/dashboard'
import { logout, session } from '@/session'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()

type Icon = 'overview' | 'shop' | 'products' | 'settings'
interface NavItem {
  to: string
  label: string
  icon: Icon
  badge?: number
}

const home = computed(() => session.context?.home)
const managesStock = computed(() => home.value === 'owner' || home.value === 'manager')
const lowStock = ref(0)

// Each kind of user only gets the menu entries they can use.
const menu = computed<NavItem[]>(() => {
  const items: NavItem[] = []
  if (managesStock.value) items.push({ to: '/owner', label: t('nav.overview'), icon: 'overview' })
  if (home.value !== 'owner') items.push({ to: '/shop', label: t('nav.myShop'), icon: 'shop' })
  if (managesStock.value) {
    items.push({ to: '/products', label: t('nav.products'), icon: 'products', badge: lowStock.value })
  }
  return items
})
const general = computed<NavItem[]>(() =>
  session.context?.can_edit_settings ? [{ to: '/settings', label: t('nav.settings'), icon: 'settings' }] : [],
)

// Highlight the entry for its own page and its sub-pages (/products/<code>).
const isActive = (to: string) => route.path === to || route.path.startsWith(`${to}/`)

const initials = computed(() =>
  (session.context?.full_name ?? '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase())
    .join(''),
)

// Phone: the menu is a drawer.
const menuOpen = ref(false)
watch(
  () => route.fullPath,
  () => {
    menuOpen.value = false
    refreshCounts()
  },
)

async function refreshCounts() {
  if (!managesStock.value) return
  try {
    lowStock.value = (await dashboardApi.counts()).low_stock
  } catch {
    lowStock.value = 0 // the badge is a convenience; never block the page
  }
}
onMounted(refreshCounts)

const search = ref('')
async function submitSearch() {
  const q = search.value.trim()
  await router.push({ path: '/products', query: q ? { q } : {} })
  search.value = ''
}

async function signOut() {
  await logout()
  await router.push('/login')
}
</script>

<template>
  <div class="min-h-screen p-3 sm:p-5 lg:p-6">
    <!-- Top bar -->
    <header class="card flex items-center gap-3 px-3 py-2.5 sm:px-4">
      <button
        type="button"
        class="grid h-10 w-10 place-items-center rounded-full text-slate-600 hover:bg-slate-100 lg:hidden"
        :aria-label="t('nav.openMenu')"
        :aria-expanded="menuOpen"
        aria-controls="app-menu"
        @click="menuOpen = true"
      >
        <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
          <path d="M4 7h16M4 12h16M4 17h16" />
        </svg>
      </button>

      <RouterLink to="/" class="flex shrink-0 items-center rounded-full py-1 pe-3 ps-1 hover:bg-slate-50" :aria-label="t('nav.home')">
        <BrandName class="text-[17px]" logo-class="h-9 w-9 rounded-full bg-white" />
      </RouterLink>

      <form v-if="managesStock" role="search" class="relative ms-auto hidden w-full max-w-md md:block" @submit.prevent="submitSearch">
        <svg
          viewBox="0 0 24 24"
          class="pointer-events-none absolute start-4 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-slate-400"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          aria-hidden="true"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <input
          v-model="search"
          type="search"
          :placeholder="t('nav.searchProducts')"
          :aria-label="t('nav.searchProducts')"
          class="field rounded-full py-2.5 ps-11 text-[15px]"
        />
      </form>

      <div class="ms-auto flex items-center gap-2" :class="{ 'md:ms-3': managesStock }">
        <ThemeSwitcher class="hidden sm:inline-flex" />
        <LanguageSwitcher class="hidden sm:inline-flex" />
        <div v-if="session.context" class="flex items-center gap-2.5 rounded-full py-1 ps-1 pe-1 sm:pe-3">
          <span
            class="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand-600 text-[13px] font-semibold text-on-brand"
            aria-hidden="true"
          >
            {{ initials }}
          </span>
          <span class="hidden leading-tight sm:block">
            <span class="block text-[14px] font-medium text-slate-900" dir="auto">{{ session.context.full_name }}</span>
            <span v-if="home" class="block text-[12px] text-slate-500">{{ t(`roles.${home}`) }}</span>
          </span>
        </div>
      </div>
    </header>

    <div class="mt-5 flex items-start gap-6">
      <!-- Phone: dimmed background behind the open drawer -->
      <div v-if="menuOpen" class="fixed inset-0 z-30 bg-black/30 lg:hidden" aria-hidden="true" @click="menuOpen = false" />

      <!-- Sidebar (desktop) / drawer (phone) -->
      <aside
        id="app-menu"
        class="card fixed inset-y-3 start-3 z-40 flex w-[min(264px,calc(100vw-1.5rem))] flex-col p-4 transition duration-200 lg:sticky lg:top-6 lg:z-auto lg:h-[calc(100vh-8.5rem)] lg:min-h-[420px] lg:w-[264px] lg:shrink-0 lg:translate-x-0 lg:opacity-100"
        :class="
          menuOpen
            ? 'translate-x-0 opacity-100'
            : 'pointer-events-none invisible -translate-x-3 opacity-0 rtl:translate-x-3 lg:pointer-events-auto lg:visible'
        "
        :aria-label="t('nav.main')"
      >
        <div class="mb-3 flex items-center justify-between lg:hidden">
          <span class="ps-3 text-[13px] font-medium text-slate-500">{{ t('nav.menu') }}</span>
          <button
            type="button"
            class="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100"
            :aria-label="t('nav.closeMenu')"
            @click="menuOpen = false"
          >
            <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
              <path d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
        </div>

        <nav class="flex-1 overflow-y-auto">
          <template v-for="(group, g) in [{ title: t('nav.menu'), items: menu }, { title: t('nav.general'), items: general }]" :key="g">
            <template v-if="group.items.length">
              <div class="px-3 pb-2 text-[13px] font-medium text-slate-400" :class="g ? 'pt-6' : 'hidden pt-1 lg:block'">
                {{ group.title }}
              </div>
              <ul class="space-y-1">
                <li v-for="item in group.items" :key="item.to">
                  <RouterLink
                    :to="item.to"
                    class="flex items-center gap-3 rounded-2xl px-3.5 py-3 text-[15px] font-medium transition"
                    :class="isActive(item.to) ? 'bg-brand-600 text-on-brand shadow-sm' : 'text-slate-700 hover:bg-slate-100'"
                    :aria-current="isActive(item.to) ? 'page' : undefined"
                  >
                    <svg viewBox="0 0 24 24" class="h-5 w-5 shrink-0" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                      <template v-if="item.icon === 'overview'">
                        <rect x="3.5" y="3.5" width="7" height="7" rx="2" /><rect x="13.5" y="3.5" width="7" height="7" rx="2" />
                        <rect x="3.5" y="13.5" width="7" height="7" rx="2" /><rect x="13.5" y="13.5" width="7" height="7" rx="2" />
                      </template>
                      <path v-else-if="item.icon === 'shop'" d="M4 10v9h16v-9M3 10l2-5h14l2 5M3 10h18M9 19v-5h6v5" />
                      <template v-else-if="item.icon === 'products'">
                        <path d="M12 3 4 7v10l8 4 8-4V7l-8-4Z" /><path d="m4 7 8 4 8-4M12 11v10" />
                      </template>
                      <template v-else>
                        <circle cx="12" cy="12" r="3" />
                        <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z" />
                      </template>
                    </svg>
                    <span class="flex-1">{{ item.label }}</span>
                    <span
                      v-if="item.badge"
                      class="min-w-6 rounded-full px-1.5 py-0.5 text-center text-[12px] font-semibold"
                      :class="isActive(item.to) ? 'bg-white/25 text-on-brand' : 'bg-brand-600 text-on-brand'"
                      :title="t('nav.lowStockBadge', { count: item.badge }, item.badge)"
                    >
                      {{ item.badge > 99 ? '99+' : item.badge }}
                    </span>
                  </RouterLink>
                </li>
              </ul>
            </template>
          </template>
        </nav>

        <div class="mt-4 flex items-center justify-center gap-2 sm:hidden">
          <ThemeSwitcher />
          <LanguageSwitcher />
        </div>

        <button
          type="button"
          class="mt-4 flex w-full items-center gap-3 rounded-2xl bg-red-50 px-3.5 py-3 text-[15px] font-medium text-red-700 transition hover:brightness-95"
          @click="signOut"
        >
          <svg viewBox="0 0 24 24" class="h-5 w-5 rtl:rotate-180" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l5-5-5-5M15 12H4" />
          </svg>
          {{ t('auth.signOut') }}
        </button>
      </aside>

      <main class="min-w-0 flex-1 pb-12">
        <RouterView />
      </main>
    </div>
  </div>
</template>
