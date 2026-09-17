<script setup>
import { cn } from '@/lib/utils'
const props = defineProps({ class: { type: null, default: '' } })
</script>

<template>
  <td :class="cn('p-4 align-middle', props.class)"><slot /></td>
</template>
