<script setup>
import { cn } from '@/lib/utils'
const props = defineProps({ class: { type: null, default: '' } })
</script>

<template>
  <main
    :class="cn('relative flex min-h-svh w-full min-w-0 flex-1 flex-col bg-background', props.class)"
  >
    <slot />
  </main>
</template>
