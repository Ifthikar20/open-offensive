<script setup>
import { TooltipProvider } from 'reka-ui'
const props = defineProps({ delayDuration: { type: Number, default: 0 } })
</script>

<template>
  <TooltipProvider :delay-duration="props.delayDuration"><slot /></TooltipProvider>
</template>
