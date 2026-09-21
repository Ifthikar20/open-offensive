import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import authApi from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const ready = ref(false)

  const isAuthenticated = computed(() => !!user.value)

  // Prime the CSRF cookie, then resolve the current user (401/403 = anonymous).
  async function bootstrap() {
    try {
      await authApi.csrf()
      user.value = (await authApi.me()).data
    } catch {
      user.value = null
    } finally {
      ready.value = true
    }
  }

  async function login(username, password) {
    user.value = (await authApi.login(username, password)).data
  }
  async function register(payload) {
    user.value = (await authApi.register(payload)).data
  }
  async function logout() {
    try {
      await authApi.logout()
    } finally {
      user.value = null
    }
  }
  async function updateProfile(payload) {
    user.value = (await authApi.updateProfile(payload)).data
    return user.value
  }
  async function changePassword(payload) {
    await authApi.changePassword(payload)
  }

  return {
    user, ready, isAuthenticated,
    bootstrap, login, register, logout, updateProfile, changePassword,
  }
})
