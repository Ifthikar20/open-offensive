import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

const THEME_KEY = 'oo-theme'
const VALID = ['light', 'dark', 'system']

function systemPrefersDark() {
  try {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
  } catch {
    return false
  }
}

export const useAppStore = defineStore('app', () => {
  const stored = (() => {
    try {
      const v = localStorage.getItem(THEME_KEY)
      return VALID.includes(v) ? v : 'light'
    } catch {
      return 'light'
    }
  })()

  const theme = ref(stored) // 'light' | 'dark' | 'system'
  const resolvedTheme = computed(() =>
    theme.value === 'system' ? (systemPrefersDark() ? 'dark' : 'light') : theme.value
  )
  const isDark = computed(() => resolvedTheme.value === 'dark')

  function applyTheme() {
    const mode = resolvedTheme.value
    const root = document.documentElement
    root.setAttribute('data-theme', mode)
    root.style.colorScheme = mode
  }
  function setTheme(pref) {
    if (!VALID.includes(pref)) return
    theme.value = pref
    try {
      localStorage.setItem(THEME_KEY, pref)
    } catch {
      /* private mode */
    }
    applyTheme()
  }
  function toggleTheme() {
    setTheme(resolvedTheme.value === 'dark' ? 'light' : 'dark')
  }

  // Re-apply on OS preference change while following 'system'.
  try {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      if (theme.value === 'system') applyTheme()
    })
  } catch {
    /* ignore */
  }

  applyTheme()

  return { theme, resolvedTheme, isDark, applyTheme, setTheme, toggleTheme }
})
