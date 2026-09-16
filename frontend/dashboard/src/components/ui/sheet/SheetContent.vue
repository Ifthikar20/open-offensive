<script setup>
import { computed } from 'vue'
import { DialogContent, DialogOverlay, DialogPortal } from 'reka-ui'
import { cn } from '@/lib/utils'
const props = defineProps({ side: { type: String, default: 'right' }, class: { type: null, default: '' } })
const sideClasses = computed(
  () =>
    ({
      left: 'inset-y-0 left-0 h-full w-3/4 border-r sm:max-w-sm',
      right: 'inset-y-0 right-0 h-full w-3/4 border-l sm:max-w-sm',
    })[props.side] || ''
)
</script>

<template>
  <DialogPortal>
    <DialogOverlay class="fixed inset-0 z-50 bg-black/50" />
    <DialogContent
      :class="
        cn('fixed z-50 flex flex-col gap-4 bg-background p-6 shadow-lg focus:outline-none', sideClasses, props.class)
      "
    >
      <slot />
    </DialogContent>
  </DialogPortal>
</template>
