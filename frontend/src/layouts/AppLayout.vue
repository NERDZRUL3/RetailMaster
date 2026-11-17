<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import ThemeSwitcher from '@/components/ThemeSwitcher.vue'
import { branding } from '@/branding'
import { dashboardApi } from '@/dashboard'
import { logout, session } from '@/session'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()

// Outline icons (24px grid), one or more paths each.
const ICONS: Record<string, string[]> = {
  dashboard: ['M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z'],
  shop: ['M4 10v9h16v-9M3 10l2-5h14l2 5M3 10h18M9 19v-5h6v5'],
  pos: ['M4 4h16v10H4zM8 18h8M12 14v4M7 8h4'],
  products: ['M12 3 4 7v10l8 4 8-4V7l-8-4Z', 'm4 7 8 4 8-4M12 11v10'],
  categories: ['M4 5h7v14H4zM14 5h6v5h-6zM14 14h6v5h-6z'],
  receive: ['M3 7h11v9H3zM14 10h4l3 3v3h-7', 'M7 19.5h.01M17 19.5h.01M8.5 9.5 10 11l3-3'],
  inventory: ['M12 3 4 7.5v9L12 21l8-4.5v-9L12 3Z', 'm8.5 11 3.5 3 3.5-3'],
  orders: ['M3 4h2l2.4 11h10.2L20 7.5H6.2', 'M9 19.5h.01M17 19.5h.01'],
  suppliers: ['M4 19V8l8-4 8 4v11', 'M8 19v-6h8v6M8 13h8'],
  purchaseOrders: ['M7 3h7l5 5v13H7z', 'M14 3v5h5M10 13h6M10 17h6'],
  returns: ['M9 14 4 9l5-5', 'M4 9h10.5a5.5 5.5 0 0 1 0 11H11'],
  reports: ['M5 4h14v16H5z', 'M9 16v-4M12 16V8M15 16v-6'],
  settings: [
    'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
    'M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z',
  ],
}

interface NavItem {
  to: string
  key: string
  badge?: number
}

const home = computed(() => session.context?.home)
const managesStock = computed(() => home.value === 'owner' || home.value === 'manager')
const lowStock = ref(0)

// Each kind of user only gets the entries they can use.
const menu = computed<NavItem[]>(() => {
  const items: NavItem[] = []
  if (managesStock.value) items.push({ to: '/owner', key: 'dashboard' })
  if (session.context?.can_sell) items.push({ to: '/pos', key: 'pos' })
  if (home.value !== 'owner') items.push({ to: '/shop', key: 'shop' })
  if (managesStock.value) {
    items.push(
      { to: '/products', key: 'products', badge: lowStock.value },
      ...(session.context?.can_receive ? [{ to: '/receive', key: 'receive' }] : []),
      { to: '/categories', key: 'categories' },
      { to: '/inventory', key: 'inventory' },
      { to: '/orders', key: 'orders' },
      { to: '/suppliers', key: 'suppliers' },
      { to: '/purchase-orders', key: 'purchaseOrders' },
      { to: '/returns', key: 'returns' },
      { to: '/reports', key: 'reports' },
    )
  }
  if (session.context?.can_edit_settings) items.push({ to: '/settings', key: 'settings' })
  return items
})

const isActive = (to: string) => route.path === to || route.path.startsWith(`${to}/`)

const initials = computed(() =>
  (session.context?.full_name ?? '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase())
    .join(''),
)
const currency = ref('')

// Phone: the menu is a drawer. Everywhere: the account menu is a popover.
const menuOpen = ref(false)
const accountOpen = ref(false)
const accountBox = ref<HTMLElement | null>(null)
watch(
  () => route.fullPath,
  () => {
    menuOpen.value = false
    accountOpen.value = false
    refreshCounts()
  },
)

async function refreshCounts() {
  if (!managesStock.value) return
  try {
    const counts = await dashboardApi.counts()
    lowStock.value = counts.low_stock
    currency.value = counts.currency ?? ''
  } catch {
    lowStock.value = 0 // a convenience; never block the page
  }
}

const searchInput = ref<HTMLInputElement | null>(null)
const search = ref('')
async function submitSearch() {
  const q = search.value.trim()
  await router.push({ path: '/products', query: q ? { q } : {} })
  search.value = ''
  searchInput.value?.blur()
}

function onKey(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && searchInput.value) {
    event.preventDefault()
    searchInput.value.focus()
  }
  if (event.key === 'Escape') {
    accountOpen.value = false
    menuOpen.value = false
  }
}
function onClick(event: MouseEvent) {
  if (accountOpen.value && accountBox.value && !accountBox.value.contains(event.target as Node)) {
    accountOpen.value = false
  }
}
onMounted(() => {
  refreshCounts()
  window.addEventListener('keydown', onKey)
  document.addEventListener('click', onClick)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  document.removeEventListener('click', onClick)
})

async function signOut() {
  await logout()
  await router.push('/login')
}
</script>

<template>
  <div class="min-h-screen">
    <!-- Phone: dimmed background behind the open drawer -->
    <div v-if="menuOpen" class="fixed inset-0 z-30 bg-black/40 lg:hidden" aria-hidden="true" @click="menuOpen = false" />

    <!-- Side menu: locked to the side on desktop, a drawer on phones -->
    <aside
      id="app-menu"
      class="card fixed inset-y-3 start-3 z-40 flex w-[min(260px,calc(100vw-1.5rem))] flex-col p-4 transition duration-200 lg:inset-y-4 lg:start-4 lg:w-[260px] lg:translate-x-0 lg:opacity-100"
      :class="
        menuOpen
          ? 'translate-x-0 opacity-100'
          : 'pointer-events-none invisible -translate-x-3 opacity-0 rtl:translate-x-3 lg:pointer-events-auto lg:visible'
      "
      :aria-label="t('nav.main')"
    >
      <div class="flex items-center gap-3 px-1 pb-5">
        <img
          v-if="branding.logo"
          :src="branding.logo"
          alt=""
          class="h-11 w-11 shrink-0 rounded-xl bg-white object-contain"
        />
        <span v-else class="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-600 text-[18px] font-bold text-on-brand">
          {{ branding.app_name.slice(0, 1) }}
        </span>
        <span class="min-w-0 leading-tight">
          <span class="block truncate text-[17px] font-semibold text-slate-900"><bdi>{{ branding.app_name }}</bdi></span>
          <span class="block truncate text-[13px] text-slate-500">{{ t('nav.tagline') }}</span>
        </span>
        <button
          type="button"
          class="ms-auto grid h-9 w-9 shrink-0 place-items-center rounded-full text-slate-500 hover:bg-slate-100 lg:hidden"
          :aria-label="t('nav.closeMenu')"
          @click="menuOpen = false"
        >
          <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <path d="M6 6l12 12M18 6 6 18" />
          </svg>
        </button>
      </div>

      <nav class="-mx-1 flex-1 overflow-y-auto px-1">
        <ul class="space-y-1">
          <li v-for="item in menu" :key="item.to">
            <RouterLink :to="item.to" class="nav-item" :aria-current="isActive(item.to) ? 'page' : undefined">
              <svg viewBox="0 0 24 24" class="h-5 w-5 shrink-0" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path v-for="d in ICONS[item.key]" :key="d" :d="d" />
              </svg>
              <span class="flex-1">{{ t(`nav.items.${item.key}`) }}</span>
              <span
                v-if="item.badge"
                class="min-w-6 rounded-full bg-brand-600 px-1.5 py-0.5 text-center text-[12px] font-semibold text-on-brand"
                :title="t('nav.lowStockBadge', { count: item.badge }, item.badge)"
              >
                {{ item.badge > 99 ? '99+' : item.badge }}
              </span>
            </RouterLink>
          </li>
        </ul>
      </nav>

      <!-- Point of sale card -->
      <div v-if="session.context?.can_sell && route.path !== '/pos'" class="mt-4 rounded-xl bg-slate-50 p-4">
        <svg viewBox="0 0 24 24" class="h-6 w-6 text-brand-600" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M4 4h16v10H4zM8 18h8M12 14v4M7 8h4" />
        </svg>
        <div class="mt-2 text-[16px] font-semibold text-slate-900">{{ t('nav.pos.title') }}</div>
        <p class="mt-1 text-[13px] leading-snug text-slate-500">{{ t('nav.pos.body') }}</p>
        <RouterLink to="/pos" class="btn-primary mt-3 w-full justify-between rounded-xl px-4">
          {{ t('nav.pos.open') }}
          <svg viewBox="0 0 24 24" class="h-4 w-4 rtl:rotate-180" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <path d="M5 12h14M13 6l6 6-6 6" />
          </svg>
        </RouterLink>
      </div>
    </aside>

    <div class="lg:ps-[292px]">
      <!-- Top bar: stays at the top while the page scrolls -->
      <header class="sticky top-0 z-20 px-3 pt-3 pb-3 sm:px-5 lg:ps-0 lg:pe-4 lg:pt-4">
        <div class="glass card flex items-center gap-2 border-0 px-3 py-2.5 sm:gap-3 sm:px-4">
          <button
            type="button"
            class="grid h-10 w-10 shrink-0 place-items-center rounded-full text-slate-600 hover:bg-slate-100 lg:hidden"
            :aria-label="t('nav.openMenu')"
            :aria-expanded="menuOpen"
            aria-controls="app-menu"
            @click="menuOpen = true"
          >
            <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
              <path d="M4 7h16M4 12h16M4 17h16" />
            </svg>
          </button>

          <form v-if="managesStock" role="search" class="relative min-w-0 flex-1 sm:max-w-md" @submit.prevent="submitSearch">
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
              ref="searchInput"
              v-model="search"
              type="search"
              :placeholder="t('nav.searchProducts')"
              :aria-label="t('nav.searchProducts')"
              aria-keyshortcuts="Control+K Meta+K"
              class="field rounded-xl py-2.5 ps-11 pe-14 text-[15px]"
            />
            <kbd class="pointer-events-none absolute end-3 top-1/2 hidden -translate-y-1/2 rounded-md bg-white px-1.5 py-0.5 font-sans text-[12px] text-slate-500 ring-1 ring-[var(--hairline)] sm:block">
              Ctrl K
            </kbd>
          </form>
          <span v-else class="flex-1" />

          <div class="ms-auto flex items-center gap-2">
            <span
              v-if="currency"
              class="hidden h-10 items-center rounded-xl bg-slate-100 px-3.5 text-[14px] font-medium text-slate-700 sm:inline-flex"
              :title="t('nav.currency')"
            >
              {{ currency }}
            </span>
            <RouterLink
              v-if="managesStock"
              to="/products?low=1"
              class="relative grid h-10 w-10 place-items-center rounded-xl bg-slate-100 text-slate-700 hover:bg-slate-200"
              :aria-label="t('nav.notifications', { count: lowStock }, lowStock)"
            >
              <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M6 9a6 6 0 1 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9ZM10 20a2 2 0 0 0 4 0" />
              </svg>
              <span
                v-if="lowStock"
                class="absolute -end-1 -top-1 grid h-5 min-w-5 place-items-center rounded-full bg-brand-600 px-1 text-[11px] font-semibold text-on-brand"
              >
                {{ lowStock > 9 ? '9+' : lowStock }}
              </span>
            </RouterLink>
            <button
              type="button"
              disabled
              class="hidden h-10 w-10 place-items-center rounded-xl bg-slate-100 text-slate-700 opacity-60 sm:grid"
              :title="t('nav.messagesSoon')"
              :aria-label="t('nav.messagesSoon')"
            >
              <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true">
                <path d="M3.5 6h17v12h-17z" /><path d="m4 7 8 6 8-6" />
              </svg>
            </button>

            <!-- Account menu -->
            <div ref="accountBox" class="relative">
              <button
                type="button"
                class="flex items-center gap-2 rounded-full py-1 ps-1 pe-2 hover:bg-slate-100"
                :aria-expanded="accountOpen"
                aria-haspopup="menu"
                :aria-label="t('nav.account')"
                @click="accountOpen = !accountOpen"
              >
                <span class="grid h-9 w-9 place-items-center rounded-full bg-brand-600 text-[13px] font-semibold text-on-brand" aria-hidden="true">
                  {{ initials }}
                </span>
                <svg viewBox="0 0 24 24" class="h-4 w-4 text-slate-500" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
                  <path d="m6 9 6 6 6-6" />
                </svg>
              </button>
              <div
                v-if="accountOpen"
                class="card absolute end-0 top-full z-30 mt-2 w-72 p-4 shadow-xl"
                role="menu"
              >
                <div class="leading-tight">
                  <div class="text-[15px] font-semibold text-slate-900" dir="auto">{{ session.context?.full_name }}</div>
                  <div v-if="home" class="mt-0.5 text-[13px] text-slate-500">{{ t(`roles.${home}`) }}</div>
                </div>
                <div class="mt-4 space-y-3 border-t border-[var(--hairline)] pt-4">
                  <div class="flex items-center justify-between gap-3">
                    <span class="text-[13px] text-slate-500">{{ t('theme.label') }}</span>
                    <ThemeSwitcher />
                  </div>
                  <div v-if="branding.languages.length > 1" class="flex items-center justify-between gap-3">
                    <span class="text-[13px] text-slate-500">{{ t('language.label') }}</span>
                    <LanguageSwitcher />
                  </div>
                </div>
                <button
                  type="button"
                  role="menuitem"
                  class="mt-4 flex w-full items-center gap-3 rounded-xl bg-red-50 px-3.5 py-2.5 text-[15px] font-medium text-red-700 hover:brightness-95"
                  @click="signOut"
                >
                  <svg viewBox="0 0 24 24" class="h-5 w-5 rtl:rotate-180" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l5-5-5-5M15 12H4" />
                  </svg>
                  {{ t('auth.signOut') }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </header>

      <main class="px-3 pb-12 sm:px-5 lg:ps-0 lg:pe-4">
        <RouterView />
      </main>
    </div>
  </div>
</template>
