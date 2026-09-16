<script setup>
import { cn } from '@/lib/utils'
import { Separator } from '../separator'
const props = defineProps({ class: { type: null, default: '' } })
</script>

<template>
  <Separator :class="cn('mx-2 w-auto bg-sidebar-border', props.class)" />
</template>
