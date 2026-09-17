<script setup>
import { useAppStore } from '@/stores/app'

// Instantiating the app store applies the persisted theme and keeps it in sync.
useAppStore()
</script>

<template>
  <router-view />
</template>
