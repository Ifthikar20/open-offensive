<script setup>
import { DialogContent, DialogOverlay, DialogPortal, DialogClose } from 'reka-ui'
import { X } from '@lucide/vue'
import { cn } from '@/lib/utils'
const props = defineProps({ class: { type: null, default: '' } })
</script>

<template>
  <DialogPortal>
    <DialogOverlay class="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm" />
    <DialogContent
      :class="
        cn(
          'fixed left-1/2 top-1/2 z-50 grid w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 gap-4 rounded-xl border border-border bg-card p-6 shadow-elevated focus:outline-none',
          props.class
        )
      "
    >
      <slot />
      <DialogClose
        class="absolute right-4 top-4 rounded-sm text-muted-foreground opacity-70 transition-opacity hover:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label="Close"
      >
        <X class="size-4" />
      </DialogClose>
    </DialogContent>
  </DialogPortal>
</template>
