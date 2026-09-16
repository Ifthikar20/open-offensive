<script setup>
import { cn } from '@/lib/utils'
const props = defineProps({ class: { type: null, default: '' } })
</script>

<template>
  <span role="link" aria-disabled="true" aria-current="page" :class="cn('font-medium text-foreground', props.class)">
    <slot />
  </span>
</template>
