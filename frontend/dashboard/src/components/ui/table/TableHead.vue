<script setup>
import { cn } from '@/lib/utils'
const props = defineProps({ class: { type: null, default: '' } })
</script>

<template>
  <th :class="cn('h-10 px-4 text-left align-middle text-xs font-medium text-muted-foreground', props.class)"><slot /></th>
</template>
