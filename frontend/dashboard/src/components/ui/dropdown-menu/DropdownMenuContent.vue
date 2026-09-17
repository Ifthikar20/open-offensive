<script setup>
import { DropdownMenuContent, DropdownMenuPortal } from 'reka-ui'
import { cn } from '@/lib/utils'
const props = defineProps({
  sideOffset: { type: Number, default: 4 },
  align: { type: String, default: 'start' },
  side: { type: String, default: 'bottom' },
  class: { type: null, default: '' },
})
</script>

<template>
  <DropdownMenuPortal>
    <DropdownMenuContent
      :side-offset="sideOffset"
      :align="align"
      :side="side"
      :class="
        cn(
          'z-50 min-w-[8rem] overflow-hidden rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md',
          props.class
        )
      "
    >
      <slot />
    </DropdownMenuContent>
  </DropdownMenuPortal>
</template>
