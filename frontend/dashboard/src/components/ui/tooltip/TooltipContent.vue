<script setup>
import { TooltipContent, TooltipPortal } from 'reka-ui'
import { cn } from '@/lib/utils'
const props = defineProps({
  sideOffset: { type: Number, default: 4 },
  side: { type: String, default: 'top' },
  class: { type: null, default: '' },
})
</script>

<template>
  <TooltipPortal>
    <TooltipContent
      :side="side"
      :side-offset="sideOffset"
      :class="
        cn(
          'z-50 overflow-hidden rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground',
          props.class
        )
      "
    >
      <slot />
    </TooltipContent>
  </TooltipPortal>
</template>
