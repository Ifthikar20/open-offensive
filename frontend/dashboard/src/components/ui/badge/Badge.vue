<script setup>
import { cn } from '@/lib/utils'
import { badgeVariants } from './index.js'

const props = defineProps({
  variant: { type: String, default: 'default' },
  class: { type: null, default: '' },
})
</script>

<template>
  <span :class="cn(badgeVariants({ variant }), props.class)"><slot /></span>
</template>
