<script setup>
import { ChevronsLeft, ChevronsRight } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { Button } from '../button'
import { useSidebar } from './utils.js'
const props = defineProps({ class: { type: null, default: '' } })
const { toggleSidebar, state } = useSidebar()
</script>

<template>
  <Button
    variant="ghost"
    size="icon"
    :class="cn('size-7', props.class)"
    :aria-label="state === 'expanded' ? 'Collapse sidebar' : 'Expand sidebar'"
    @click="toggleSidebar"
  >
    <ChevronsLeft v-if="state === 'expanded'" />
    <ChevronsRight v-else />
  </Button>
</template>
