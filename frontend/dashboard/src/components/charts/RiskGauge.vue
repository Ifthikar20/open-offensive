<script setup>
import { computed } from 'vue'

// A 270° radial gauge for the risk index (0–100). Drawn with the pathLength=100
// trick: the track spans 75 units (= 270°) and the value arc is 0.75 * value.
// Rotating the strokes by 135° puts the gap at the bottom.
const props = defineProps({
  value: { type: Number, default: 0 },
  color: { type: String, default: 'var(--brand-accent)' },
  band: { type: String, default: '' },
  caption: { type: String, default: '' },
})

const arc = computed(() => 0.75 * Math.max(0, Math.min(100, props.value)))
</script>

<template>
  <div class="cc-gauge">
    <svg viewBox="0 0 120 120" class="cc-gauge-svg" aria-hidden="true">
      <circle
        class="cc-gauge-track"
        cx="60"
        cy="60"
        r="48"
        fill="none"
        stroke-width="11"
        pathLength="100"
        stroke-dasharray="75 25"
        stroke-linecap="round"
        transform="rotate(135 60 60)"
      />
      <circle
        class="cc-gauge-val"
        cx="60"
        cy="60"
        r="48"
        fill="none"
        :stroke="color"
        stroke-width="11"
        pathLength="100"
        :stroke-dasharray="`${arc} ${100 - arc}`"
        stroke-linecap="round"
        transform="rotate(135 60 60)"
        :style="{ '--g': color }"
      />
    </svg>
    <div class="cc-gauge-center">
      <span class="cc-gauge-val-num" :style="{ color }">{{ Math.round(value) }}</span>
      <span v-if="band" class="cc-gauge-band" :style="{ color }">{{ band }}</span>
      <span v-if="caption" class="cc-gauge-cap">{{ caption }}</span>
    </div>
  </div>
</template>

<style scoped>
.cc-gauge {
  position: relative;
  display: grid;
  place-items: center;
  width: 100%;
  max-width: 220px;
  margin-inline: auto;
  aspect-ratio: 1 / 1;
}
.cc-gauge-svg {
  width: 100%;
  height: 100%;
}
.cc-gauge-track {
  stroke: var(--muted);
}
.cc-gauge-val {
  filter: drop-shadow(0 0 6px color-mix(in srgb, var(--g) 55%, transparent));
  transition:
    stroke-dasharray 700ms cubic-bezier(0.23, 1, 0.32, 1),
    stroke 300ms ease;
}
.cc-gauge-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  text-align: center;
}
.cc-gauge-val-num {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, 'Cascadia Code', monospace;
  font-size: 2.75rem;
  font-weight: 700;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  text-shadow: 0 0 24px color-mix(in srgb, currentColor 35%, transparent);
}
.cc-gauge-band {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, 'Cascadia Code', monospace;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}
.cc-gauge-cap {
  margin-top: 2px;
  font-size: 0.65rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted-foreground);
}
</style>
