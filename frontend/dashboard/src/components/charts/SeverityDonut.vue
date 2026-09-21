<script setup>
import { computed } from 'vue'

// A donut ring of the severity mix. r=15.9155 makes the circumference ≈ 100, so
// stroke-dasharray reads directly as percentages; segments stack via dashoffset.
const props = defineProps({
  counts: { type: Object, default: () => ({}) },
})

const SEV = [
  ['critical', 'var(--severity-critical)'],
  ['high', 'var(--severity-high)'],
  ['medium', 'var(--severity-medium)'],
  ['low', 'var(--severity-low)'],
  ['info', 'var(--severity-info)'],
]

const model = computed(() => {
  const items = SEV.map(([k, color]) => ({ k, color, v: props.counts?.[k] || 0 }))
  const total = items.reduce((s, i) => s + i.v, 0)
  let acc = 0
  const segs = items
    .filter((i) => i.v > 0)
    .map((i) => {
      const len = (i.v / total) * 100
      const seg = { ...i, len, offset: acc }
      acc += len
      return seg
    })
  return { total, segs }
})
</script>

<template>
  <div class="cc-donut">
    <svg viewBox="0 0 42 42" class="cc-donut-svg" aria-hidden="true">
      <circle
        class="cc-donut-track"
        cx="21"
        cy="21"
        r="15.9155"
        fill="none"
        stroke-width="4.5"
        pathLength="100"
      />
      <circle
        v-for="s in model.segs"
        :key="s.k"
        cx="21"
        cy="21"
        r="15.9155"
        fill="none"
        :stroke="s.color"
        stroke-width="4.5"
        pathLength="100"
        :stroke-dasharray="`${Math.max(s.len - 0.6, 0.4)} ${100 - Math.max(s.len - 0.6, 0.4)}`"
        :stroke-dashoffset="-s.offset"
        transform="rotate(-90 21 21)"
        class="cc-donut-seg"
        :style="{ '--g': s.color }"
      />
    </svg>
    <div class="cc-donut-center">
      <span class="cc-donut-total">{{ model.total }}</span>
      <span class="cc-donut-cap">{{ model.total === 0 ? 'no findings' : 'findings' }}</span>
    </div>
  </div>
</template>

<style scoped>
.cc-donut {
  position: relative;
  display: grid;
  place-items: center;
  width: 100%;
  max-width: 190px;
  margin-inline: auto;
  aspect-ratio: 1 / 1;
}
.cc-donut-svg {
  width: 100%;
  height: 100%;
}
.cc-donut-track {
  stroke: var(--muted);
}
.cc-donut-seg {
  filter: drop-shadow(0 0 3px color-mix(in srgb, var(--g) 45%, transparent));
  transition: stroke-dasharray 600ms cubic-bezier(0.23, 1, 0.32, 1);
}
.cc-donut-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
}
.cc-donut-total {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, 'Cascadia Code', monospace;
  font-size: 1.9rem;
  font-weight: 700;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  color: var(--foreground);
}
.cc-donut-cap {
  font-size: 0.6rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted-foreground);
}
</style>
