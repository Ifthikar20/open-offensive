<script setup>
import { Primitive } from 'reka-ui'
import { cn } from '@/lib/utils'
const props = defineProps({
  as: { type: [String, Object], default: 'a' },
  asChild: { type: Boolean, default: false },
  class: { type: null, default: '' },
})
</script>

<template>
  <Primitive :as="as" :as-child="asChild" :class="cn('transition-colors hover:text-foreground', props.class)">
    <slot />
  </Primitive>
</template>
