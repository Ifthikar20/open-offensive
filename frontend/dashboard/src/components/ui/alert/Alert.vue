<script setup>
import { computed } from 'vue'
import { cn } from '@/lib/utils'
const props = defineProps({
  variant: { type: String, default: 'default' },
  class: { type: null, default: '' },
})
const tone = computed(() =>
  props.variant === 'destructive'
    ? 'text-destructive bg-card [&>svg]:text-current'
    : 'bg-card text-card-foreground'
)
</script>

<template>
  <div
    role="alert"
    :class="
      cn(
        'relative grid w-full grid-cols-[0_1fr] items-start gap-y-0.5 rounded-lg border border-border px-4 py-3 text-sm shadow-sm has-[>svg]:grid-cols-[1rem_1fr] has-[>svg]:gap-x-3 [&>svg]:size-4 [&>svg]:translate-y-0.5 [&>svg]:text-current',
        tone,
        props.class
      )
    "
  >
    <slot />
  </div>
</template>
