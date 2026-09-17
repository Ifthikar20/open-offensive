<script setup>
import { ref, computed, provide, onMounted, onUnmounted } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { cn } from '@/lib/utils'
import { TooltipProvider } from '../tooltip'
import {
  SIDEBAR_INJECTION_KEY,
  SIDEBAR_WIDTH,
  SIDEBAR_WIDTH_ICON,
  SIDEBAR_COOKIE_NAME,
  SIDEBAR_COOKIE_MAX_AGE,
  SIDEBAR_KEYBOARD_SHORTCUT,
} from './utils.js'

const props = defineProps({
  defaultOpen: { type: Boolean, default: true },
  class: { type: null, default: '' },
})

const open = ref(props.defaultOpen)
const openMobile = ref(false)
const isMobile = useMediaQuery('(max-width: 767px)')

function setOpen(value) {
  open.value = value
  try {
    document.cookie = `${SIDEBAR_COOKIE_NAME}=${value}; path=/; max-age=${SIDEBAR_COOKIE_MAX_AGE}`
  } catch {
    /* private mode — the choice just won't persist */
  }
}
function setOpenMobile(value) {
  openMobile.value = value
}
function toggleSidebar() {
  isMobile.value ? setOpenMobile(!openMobile.value) : setOpen(!open.value)
}

const state = computed(() => (open.value ? 'expanded' : 'collapsed'))

function readCookie() {
  try {
    const m = document.cookie.match(new RegExp('(?:^|; )' + SIDEBAR_COOKIE_NAME + '=([^;]+)'))
    if (m) return m[1] === 'true'
  } catch {
    /* ignore */
  }
  return props.defaultOpen
}
function onKey(e) {
  if (e.key === SIDEBAR_KEYBOARD_SHORTCUT && (e.metaKey || e.ctrlKey)) {
    e.preventDefault()
    toggleSidebar()
  }
}
onMounted(() => {
  open.value = readCookie()
  window.addEventListener('keydown', onKey)
})
onUnmounted(() => window.removeEventListener('keydown', onKey))

provide(SIDEBAR_INJECTION_KEY, {
  state,
  open,
  setOpen,
  isMobile,
  openMobile,
  setOpenMobile,
  toggleSidebar,
})
</script>

<template>
  <TooltipProvider :delay-duration="0">
    <div
      :style="{ '--sidebar-width': SIDEBAR_WIDTH, '--sidebar-width-icon': SIDEBAR_WIDTH_ICON }"
      :class="
        cn(
          'group/sidebar-wrapper flex min-h-svh w-full has-[[data-variant=inset]]:bg-sidebar',
          props.class
        )
      "
    >
      <slot />
    </div>
  </TooltipProvider>
</template>
