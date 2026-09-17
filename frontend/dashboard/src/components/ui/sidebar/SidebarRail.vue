<script setup>
import { useSidebar } from './utils.js'
const { toggleSidebar } = useSidebar()
</script>

<template>
  <button
    type="button"
    aria-label="Toggle Sidebar"
    tabindex="-1"
    class="absolute inset-y-0 z-20 hidden w-4 -translate-x-1/2 cursor-w-resize transition-all ease-linear after:absolute after:inset-y-0 after:left-1/2 after:w-[2px] hover:after:bg-sidebar-border group-data-[side=left]:-right-4 sm:flex"
    @click="toggleSidebar"
  />
</template>
