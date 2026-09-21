import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

// Wrap a protected page in the app shell (AppLayout) and require auth.
const protect = (path, name, component) => ({
  path,
  component: () => import('@/layouts/AppLayout.vue'),
  meta: { requiresAuth: true },
  children: [{ path: '', name, component }],
})

const routes = [
  { path: '/', redirect: { name: 'dashboard' } },

  // Auth world — invite-first. Each page wraps itself in AuthLayout.
  {
    path: '/access',
    name: 'access',
    meta: { guest: true },
    component: () => import('@/pages/auth/InviteRedeemPage.vue'),
  },
  {
    path: '/signin',
    name: 'signin',
    meta: { guest: true },
    component: () => import('@/pages/auth/SignInPage.vue'),
  },

  // Protected app
  protect('/dashboard', 'dashboard', () => import('@/pages/DashboardPage.vue')),
  protect('/scans/:id', 'scan-detail', () => import('@/pages/ScanDetailPage.vue')),
  protect('/history', 'scan-history', () => import('@/pages/ScanHistoryPage.vue')),
  protect('/settings', 'settings', () => import('@/pages/SettingsPage.vue')),
  protect('/profile', 'profile', () => import('@/pages/ProfilePage.vue')),

  { path: '/:pathMatch(.*)*', redirect: { name: 'dashboard' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

let restored = false
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!restored) {
    await auth.bootstrap()
    restored = true
  }
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'access', query: { redirect: to.fullPath } }
  }
  if (to.meta.guest && auth.isAuthenticated) {
    return { name: 'dashboard' }
  }
  return true
})

export default router
