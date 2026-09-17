<script setup>
import { cn } from '@/lib/utils'
const props = defineProps({ class: { type: null, default: '' } })
</script>

<template>
  <ol :class="cn('flex flex-wrap items-center gap-1.5 break-words text-sm text-muted-foreground', props.class)">
    <slot />
  </ol>
</template>
