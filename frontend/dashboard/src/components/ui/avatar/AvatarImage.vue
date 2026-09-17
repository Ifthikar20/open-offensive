<script setup>
import { AvatarImage } from 'reka-ui'
const props = defineProps({ src: { type: String, default: '' }, alt: { type: String, default: '' } })
</script>

<template>
  <AvatarImage :src="props.src" :alt="props.alt" class="aspect-square size-full" />
</template>
