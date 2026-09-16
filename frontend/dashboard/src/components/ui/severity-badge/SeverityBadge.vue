<script setup>
import { computed } from 'vue'
import { cn } from '@/lib/utils'
const props = defineProps({ severity: { type: String, default: 'info' }, class: { type: null, default: '' } })
const MAP = {
  critical: 'text-severity-critical bg-severity-critical/15',
  high: 'text-severity-high bg-severity-high/15',
  medium: 'text-severity-medium bg-severity-medium/15',
  low: 'text-severity-low bg-severity-low/15',
  info: 'text-severity-info bg-severity-info/15',
}
const tone = computed(() => MAP[props.severity] || MAP.info)
</script>

<template>
  <span
    :class="
      cn(
        'inline-flex items-center rounded-md px-2 py-0.5 text-[0.68rem] font-bold uppercase tracking-wide',
        tone,
        props.class
      )
    "
  >
    {{ severity }}
  </span>
</template>
