<script setup>
import { Separator } from 'reka-ui'
import { cn } from '@/lib/utils'
const props = defineProps({
  orientation: { type: String, default: 'horizontal' },
  decorative: { type: Boolean, default: true },
  class: { type: null, default: '' },
})
</script>

<template>
  <Separator
    :orientation="orientation"
    :decorative="decorative"
    :class="
      cn(
        'shrink-0 bg-border',
        orientation === 'vertical' ? 'h-full w-px' : 'h-px w-full',
        props.class
      )
    "
  />
</template>
