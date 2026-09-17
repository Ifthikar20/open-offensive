<script setup>
import { cn } from '@/lib/utils'
import { Sheet, SheetContent, SheetTitle, SheetDescription } from '../sheet'
import { useSidebar } from './utils.js'

const props = defineProps({
  side: { type: String, default: 'left' },
  variant: { type: String, default: 'inset' },
  collapsible: { type: String, default: 'icon' },
  class: { type: null, default: '' },
})

const { state, isMobile, openMobile, setOpenMobile } = useSidebar()
</script>

<template>
  <!-- Mobile: a left drawer -->
  <Sheet v-if="isMobile" :open="openMobile" @update:open="setOpenMobile">
    <SheetContent
      side="left"
      class="w-[18rem] bg-sidebar p-0 text-sidebar-foreground [&>button]:hidden"
    >
      <SheetTitle class="sr-only">Navigation</SheetTitle>
      <SheetDescription class="sr-only">Main navigation menu</SheetDescription>
      <div class="flex h-full w-full flex-col">
        <slot />
      </div>
    </SheetContent>
  </Sheet>

  <!-- Desktop: collapsible icon rail, inset variant -->
  <div
    v-else
    class="group peer hidden text-sidebar-foreground md:block"
    :data-state="state"
    :data-collapsible="state === 'collapsed' ? collapsible : ''"
    data-variant="inset"
    :data-side="side"
  >
    <div
      class="relative w-[var(--sidebar-width)] bg-transparent transition-[width] duration-200 ease-linear group-data-[collapsible=icon]:w-[calc(var(--sidebar-width-icon)_+_1rem)]"
    />
    <div
      :class="
        cn(
          'fixed inset-y-0 z-10 hidden h-svh w-[var(--sidebar-width)] transition-[left,right,width] duration-200 ease-linear md:flex left-0 p-2 group-data-[collapsible=icon]:w-[calc(var(--sidebar-width-icon)_+_1rem_+_2px)]',
          props.class
        )
      "
    >
      <div data-sidebar="sidebar" class="flex h-full w-full flex-col bg-sidebar">
        <slot />
      </div>
    </div>
  </div>
</template>
