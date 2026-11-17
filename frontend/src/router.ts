import { createRouter, createWebHistory } from 'vue-router'

import { type Home, homePath, loadSession, session } from './session'

declare module 'vue-router' {
  interface RouteMeta {
    /** Page is for signed-out visitors. */
    guest?: boolean
    /** Which kinds of user may open the page. Navigation only: data is protected on the server. */
    homes?: Home[]
    /** Only for users who may edit the site's settings. */
    settings?: boolean
    /** Only for users who may receive stock (owners, managers). */
    receive?: boolean
    /** Only for users who may sell at the till (owners, managers, cashiers). */
    sell?: boolean
    /** Only for the owner: team accounts. */
    team?: boolean
  }
}

export const router = createRouter({
  history: createWebHistory('/retail/'),
  routes: [
    { path: '/login', component: () => import('./pages/LoginPage.vue'), meta: { guest: true } },
    { path: '/forgot', component: () => import('./pages/ForgotPasswordPage.vue'), meta: { guest: true } },
    { path: '/no-access', component: () => import('./pages/NoAccessPage.vue') },
    {
      path: '/',
      component: () => import('./layouts/AppLayout.vue'),
      children: [
        { path: '', redirect: () => homePath(session.context?.home) },
        {
          path: 'owner',
          component: () => import('./pages/owner/OwnerDashboard.vue'),
          meta: { homes: ['owner', 'manager'] },
        },
        {
          path: 'shop',
          component: () => import('./pages/cashier/ShopHome.vue'),
          meta: { homes: ['manager', 'cashier'] },
        },
        {
          path: 'pos',
          component: () => import('./pages/pos/PosPage.vue'),
          meta: { sell: true },
        },
        {
          path: 'pos/sessions',
          component: () => import('./pages/pos/TillSessionsPage.vue'),
          meta: { sell: true },
        },
        {
          path: 'products',
          component: () => import('./pages/inventory/ProductsPage.vue'),
          meta: { homes: ['owner', 'manager'] },
        },
        {
          path: 'products/new',
          component: () => import('./pages/inventory/ProductEditor.vue'),
          meta: { homes: ['owner', 'manager'] },
        },
        {
          path: 'receive',
          component: () => import('./pages/inventory/ReceivePage.vue'),
          meta: { homes: ['owner', 'manager'], receive: true },
        },
        {
          path: 'products/:code',
          component: () => import('./pages/inventory/ProductEditor.vue'),
          props: true,
          meta: { homes: ['owner', 'manager'] },
        },
        {
          path: 'categories',
          component: () => import('./pages/inventory/CategoriesPage.vue'),
          meta: { homes: ['owner', 'manager'] },
        },
        {
          path: 'inventory',
          component: () => import('./pages/inventory/InventoryPage.vue'),
          meta: { homes: ['owner', 'manager'] },
        },
        {
          path: 'orders',
          component: () => import('./pages/ComingSoonPage.vue'),
          props: { section: 'orders' },
          meta: { homes: ['owner', 'manager'] },
        },
        {
          path: 'suppliers',
          component: () => import('./pages/purchasing/SuppliersPage.vue'),
          meta: { homes: ['owner', 'manager'] },
        },
        {
          path: 'purchase-orders',
          component: () => import('./pages/purchasing/PurchaseOrdersPage.vue'),
          meta: { homes: ['owner', 'manager'] },
        },
        {
          path: 'purchase-orders/new',
          component: () => import('./pages/purchasing/PurchaseOrderPage.vue'),
          meta: { homes: ['owner', 'manager'] },
        },
        {
          path: 'purchase-orders/:name',
          component: () => import('./pages/purchasing/PurchaseOrderPage.vue'),
          props: true,
          meta: { homes: ['owner', 'manager'] },
        },
        {
          path: 'returns',
          component: () => import('./pages/ComingSoonPage.vue'),
          props: { section: 'returns' },
          meta: { homes: ['owner', 'manager'] },
        },
        {
          path: 'reports',
          component: () => import('./pages/ComingSoonPage.vue'),
          props: { section: 'reports' },
          meta: { homes: ['owner', 'manager'] },
        },
        {
          path: 'team',
          component: () => import('./pages/settings/TeamPage.vue'),
          meta: { team: true },
        },
        {
          path: 'shops',
          component: () => import('./pages/settings/ShopsPage.vue'),
          meta: { team: true },
        },
        {
          path: 'settings',
          component: () => import('./pages/settings/SettingsPage.vue'),
          meta: { settings: true },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  if (!session.loaded) await loadSession()
  const context = session.context

  if (!context) return to.meta.guest ? true : '/login'
  if (to.meta.guest) return homePath(context.home)
  if (!context.home) return to.path === '/no-access' ? true : '/no-access'
  if (to.meta.homes && !to.meta.homes.includes(context.home)) return homePath(context.home)
  if (to.meta.settings && !context.can_edit_settings) return homePath(context.home)
  if (to.meta.receive && !context.can_receive) return homePath(context.home)
  if (to.meta.sell && !context.can_sell) return homePath(context.home)
  if (to.meta.team && !context.can_manage_users) return homePath(context.home)
  if (to.path === '/no-access') return homePath(context.home)
  return true
})
