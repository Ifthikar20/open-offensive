<script setup>
import { computed } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps({ status: { type: String, default: '' } })
const running = computed(() => props.status === 'queued' || props.status === 'running')
const tone = computed(
  () =>
    ({
      queued: 'text-warning',
      running: 'text-[color:var(--brand-accent)]',
      done: 'text-success',
      error: 'text-danger',
    })[props.status] || 'text-muted-foreground'
)
</script>

<template>
  <span
    :class="
      cn(
        'inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-0.5 text-[0.72rem] font-semibold capitalize',
        tone
      )
    "
  >
    <span :class="cn('size-1.5 rounded-full bg-current', running && 'animate-pulse')" />
    {{ status }}
  </span>
</template>
