<script setup>
import { useRouter } from 'vue-router'
import { cn } from '@/lib/utils'
import { Button } from './button'
const props = defineProps({
  title: { type: String, required: true },
  body: { type: String, default: '' },
  ctaLabel: { type: String, default: '' },
  ctaTo: { type: [String, Object], default: null },
  variant: { type: String, default: 'card' },
  class: { type: null, default: '' },
})
const router = useRouter()
function go() {
  if (props.ctaTo) router.push(props.ctaTo)
}
</script>

<template>
  <div
    :class="
      cn(
        'flex flex-col items-center justify-center gap-2 px-6 py-10 text-center',
        variant === 'panel' && 'rounded-2xl border border-dashed border-border bg-card',
        props.class
      )
    "
  >
    <p class="text-sm font-semibold text-foreground">{{ title }}</p>
    <p v-if="body" class="max-w-md text-[12px] leading-relaxed text-muted-foreground">{{ body }}</p>
    <slot />
    <Button v-if="ctaLabel" size="sm" class="mt-1" @click="go">{{ ctaLabel }}</Button>
  </div>
</template>
