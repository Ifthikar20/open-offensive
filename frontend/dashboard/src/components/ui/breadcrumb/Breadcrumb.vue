<script setup>
const props = defineProps({ class: { type: null, default: '' } })
</script>

<template>
  <nav aria-label="breadcrumb" :class="props.class"><slot /></nav>
</template>
