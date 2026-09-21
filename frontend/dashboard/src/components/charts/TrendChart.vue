<script setup>
import { computed } from 'vue'

// Findings-per-run area/line chart. Paths + gridlines stretch to fill the panel
// (preserveAspectRatio=none, non-scaling strokes stay crisp); all text and the
// end marker are HTML overlays positioned by percentage so nothing distorts.
const props = defineProps({
  points: { type: Array, default: () => [] }, // numbers, oldest → newest
  labels: { type: Array, default: () => [] }, // parallel date strings (optional)
  color: { type: String, default: 'var(--brand-accent)' },
})

const W = 600
const H = 200
const PT = 16
const PB = 8
const gid = 'tr-' + Math.random().toString(36).slice(2, 9)

const geo = computed(() => {
  const p = props.points.filter((v) => typeof v === 'number')
  if (!p.length) return null
  const max = Math.max(...p, 1)
  const n = p.length
  const x = (i) => (n === 1 ? W / 2 : (i / (n - 1)) * W)
  const y = (v) => PT + (1 - v / max) * (H - PT - PB)
  const pts = p.map((v, i) => [x(i), y(v)])
  const line = pts.map((c, i) => (i ? 'L' : 'M') + c[0].toFixed(1) + ' ' + c[1].toFixed(1)).join(' ')
  const area = `${line} L ${pts[pts.length - 1][0].toFixed(1)} ${H} L ${pts[0][0].toFixed(1)} ${H} Z`
  const last = pts[pts.length - 1]
  const grid = [0, 0.5, 1].map((f) => ({
    y: (PT + f * (H - PT - PB)).toFixed(1),
    v: Math.round(max * (1 - f)),
  }))
  return {
    line,
    area,
    max,
    grid,
    lastVal: p[p.length - 1],
    lastPct: { x: (last[0] / W) * 100, y: (last[1] / H) * 100 },
  }
})
</script>

<template>
  <div class="cc-trend">
    <template v-if="geo">
      <svg
        :viewBox="`0 0 ${W} ${H}`"
        preserveAspectRatio="none"
        class="cc-trend-svg"
        aria-hidden="true"
      >
        <defs>
          <linearGradient :id="gid" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" :stop-color="color" stop-opacity="0.32" />
            <stop offset="1" :stop-color="color" stop-opacity="0" />
          </linearGradient>
        </defs>
        <line
          v-for="g in geo.grid"
          :key="g.y"
          x1="0"
          :y1="g.y"
          :x2="W"
          :y2="g.y"
          class="cc-trend-grid"
          vector-effect="non-scaling-stroke"
        />
        <path :d="geo.area" :fill="`url(#${gid})`" />
        <path
          :d="geo.line"
          fill="none"
          :stroke="color"
          stroke-width="2"
          stroke-linejoin="round"
          stroke-linecap="round"
          vector-effect="non-scaling-stroke"
          class="cc-trend-line"
          :style="{ '--g': color }"
        />
      </svg>

      <!-- y-axis labels -->
      <span
        v-for="g in geo.grid"
        :key="'l' + g.y"
        class="cc-trend-ylabel"
        :style="{ top: (g.y / H) * 100 + '%' }"
        >{{ g.v }}</span
      >

      <!-- end marker -->
      <span
        class="cc-trend-dot"
        :style="{ left: geo.lastPct.x + '%', top: geo.lastPct.y + '%', '--g': color }"
      />

      <!-- x-axis first / last -->
      <div v-if="labels.length" class="cc-trend-xaxis">
        <span>{{ labels[0] }}</span>
        <span>{{ labels[labels.length - 1] }}</span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.cc-trend {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 180px;
}
.cc-trend-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.cc-trend-grid {
  stroke: var(--border);
  stroke-dasharray: 3 4;
}
.cc-trend-line {
  filter: drop-shadow(0 1px 5px color-mix(in srgb, var(--g) 45%, transparent));
}
.cc-trend-ylabel {
  position: absolute;
  left: 0;
  transform: translateY(-50%);
  padding-left: 2px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, 'Cascadia Code', monospace;
  font-size: 0.6rem;
  color: var(--muted-foreground);
  background: color-mix(in srgb, var(--card) 70%, transparent);
}
.cc-trend-dot {
  position: absolute;
  width: 9px;
  height: 9px;
  border-radius: 9999px;
  background: var(--g);
  transform: translate(-50%, -50%);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--g) 22%, transparent);
}
.cc-trend-xaxis {
  position: absolute;
  inset-inline: 0;
  bottom: -18px;
  display: flex;
  justify-content: space-between;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, 'Cascadia Code', monospace;
  font-size: 0.6rem;
  color: var(--muted-foreground);
}
</style>
