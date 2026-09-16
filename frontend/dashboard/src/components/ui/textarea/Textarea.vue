<script setup>
import { cn } from '@/lib/utils'
const model = defineModel({ type: String, default: '' })
const props = defineProps({ class: { type: null, default: '' } })
</script>

<template>
  <textarea
    v-model="model"
    :class="
      cn(
        'flex min-h-16 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
        props.class
      )
    "
  />
</template>
