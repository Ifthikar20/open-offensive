<script setup>
import { ChevronRight } from '@lucide/vue'
import { cn } from '@/lib/utils'
const props = defineProps({ class: { type: null, default: '' } })
</script>

<template>
  <li role="presentation" aria-hidden="true" :class="cn('[&>svg]:size-3.5', props.class)">
    <slot><ChevronRight /></slot>
  </li>
</template>
