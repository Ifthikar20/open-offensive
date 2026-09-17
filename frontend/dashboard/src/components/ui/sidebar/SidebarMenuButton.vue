<script setup>
import { Primitive } from 'reka-ui'
import { cn } from '@/lib/utils'
import { Tooltip, TooltipTrigger, TooltipContent } from '../tooltip'
import { sidebarMenuButtonVariants, useSidebar } from './utils.js'

const props = defineProps({
  as: { type: [String, Object], default: 'button' },
  asChild: { type: Boolean, default: false },
  isActive: { type: Boolean, default: false },
  variant: { type: String, default: 'default' },
  size: { type: String, default: 'default' },
  tooltip: { type: String, default: '' },
  class: { type: null, default: '' },
})

const { state, isMobile } = useSidebar()
</script>

<template>
  <Tooltip v-if="tooltip">
    <TooltipTrigger as-child>
      <Primitive
        :as="as"
        :as-child="asChild"
        :data-active="isActive"
        :class="cn(sidebarMenuButtonVariants({ variant, size }), props.class)"
      >
        <slot />
      </Primitive>
    </TooltipTrigger>
    <TooltipContent v-if="state === 'collapsed' && !isMobile" side="right">
      {{ tooltip }}
    </TooltipContent>
  </Tooltip>

  <Primitive
    v-else
    :as="as"
    :as-child="asChild"
    :data-active="isActive"
    :class="cn(sidebarMenuButtonVariants({ variant, size }), props.class)"
  >
    <slot />
  </Primitive>
</template>
