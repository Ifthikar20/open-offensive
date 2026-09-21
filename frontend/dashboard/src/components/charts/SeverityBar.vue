<script setup>
import { computed } from 'vue'

// Horizontal stacked severity bar. Reused in the risk panel, top-targets, and the
// recent-activity feed. Falls back to a muted track when there are no findings.
const props = defineProps({
  counts: { type: Object, default: () => ({}) },
  height: { type: Number, default: 8 },
})

const SEV = [
  ['critical', 'Critical', 'var(--severity-critical)'],
  ['high', 'High', 'var(--severity-high)'],
  ['medium', 'Medium', 'var(--severity-medium)'],
  ['low', 'Low', 'var(--severity-low)'],
  ['info', 'Info', 'var(--severity-info)'],
]

const model = computed(() => {
  const items = SEV.map(([k, label, color]) => ({ k, label, color, v: props.counts?.[k] || 0 }))
  const total = items.reduce((s, i) => s + i.v, 0)
  return { total, items: items.filter((i) => i.v > 0) }
})
</script>

<template>
  <div class="cc-bar" :style="{ height: height + 'px' }">
    <template v-if="model.total > 0">
      <span
        v-for="s in model.items"
        :key="s.k"
        class="cc-bar-seg"
        :style="{ width: (s.v / model.total) * 100 + '%', background: s.color }"
        :title="`${s.label}: ${s.v}`"
      />
    </template>
    <span v-else class="cc-bar-empty" />
  </div>
</template>

<style scoped>
.cc-bar {
  display: flex;
  width: 100%;
  gap: 1.5px;
  overflow: hidden;
  border-radius: 9999px;
  background: var(--muted);
}
.cc-bar-seg {
  display: block;
  height: 100%;
  min-width: 3px;
}
.cc-bar-empty {
  display: block;
  width: 100%;
  height: 100%;
  background: var(--muted);
}
</style>
