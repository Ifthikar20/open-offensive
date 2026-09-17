<script setup>
defineProps({ collapsed: { type: Boolean, default: false } })
</script>

<template>
  <span class="flex items-center gap-2 font-semibold text-sidebar-foreground">
    <span
      class="flex aspect-square size-7 items-center justify-center rounded-md bg-sidebar-primary text-sidebar-primary-foreground"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" stroke-width="1.7" />
        <circle cx="12" cy="12" r="2.6" fill="currentColor" />
        <line x1="12" y1="2.5" x2="12" y2="6" stroke="currentColor" stroke-width="1.7" />
        <line x1="12" y1="18" x2="12" y2="21.5" stroke="currentColor" stroke-width="1.7" />
        <line x1="2.5" y1="12" x2="6" y2="12" stroke="currentColor" stroke-width="1.7" />
        <line x1="18" y1="12" x2="21.5" y2="12" stroke="currentColor" stroke-width="1.7" />
      </svg>
    </span>
    <span v-if="!collapsed" class="text-[0.95rem] tracking-tight">
      Open<span class="font-bold" style="color: var(--brand-accent)">Offensive</span>
    </span>
  </span>
</template>
