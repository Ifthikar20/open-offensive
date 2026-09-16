<script setup>
import { onMounted, onBeforeUnmount } from 'vue'

// Auth pages are always light, regardless of the app theme (restored on leave).
let prev = null
onMounted(() => {
  const root = document.documentElement
  prev = root.getAttribute('data-theme')
  root.setAttribute('data-theme', 'light')
  root.style.colorScheme = 'light'
})
onBeforeUnmount(() => {
  const root = document.documentElement
  if (prev) {
    root.setAttribute('data-theme', prev)
    root.style.colorScheme = prev
  }
})
</script>

<template>
  <div class="auth-shell">
    <div class="w-full max-w-[420px]">
      <slot />
    </div>
    <p class="auth-foot">© 2026 OpenOffensive · invite-only</p>
  </div>
</template>

<style scoped>
.auth-shell {
  min-height: 100svh;
  display: grid;
  place-items: center;
  padding: 24px;
  position: relative;
  background:
    radial-gradient(1100px 560px at 50% -12%, rgba(114, 50, 224, 0.12), transparent 60%),
    var(--bg-root);
}
.auth-foot {
  position: absolute;
  bottom: 18px;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
