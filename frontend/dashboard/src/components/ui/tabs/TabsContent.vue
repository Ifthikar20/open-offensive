<script setup>
import { TabsContent } from 'reka-ui'
import { cn } from '@/lib/utils'
const props = defineProps({ value: { type: [String, Number], required: true }, class: { type: null, default: '' } })
</script>

<template>
  <TabsContent :value="value" :class="cn('mt-2 focus-visible:outline-none', props.class)">
    <slot />
  </TabsContent>
</template>
