<script setup>
import { computed } from 'vue'

// A tiny responsive sparkline (area + line) for KPI tiles. Stroke stays crisp at
// any width via non-scaling-stroke; the gradient id is randomised so multiple
// sparks on one page don't collide.
const props = defineProps({
  points: { type: Array, default: () => [] },
  color: { type: String, default: 'var(--brand-accent)' },
  height: { type: Number, default: 34 },
})

const W = 100
const gid = 'ms-' + Math.random().toString(36).slice(2, 9)

const geo = computed(() => {
  const p = props.points.filter((v) => typeof v === 'number')
  if (!p.length) return null
  const H = props.height
  const max = Math.max(...p, 1)
  const min = Math.min(...p, 0)
  const span = max - min || 1
  const n = p.length
  const x = (i) => (n === 1 ? W / 2 : (i / (n - 1)) * W)
  const y = (v) => H - 2 - ((v - min) / span) * (H - 4)
  const pts = p.map((v, i) => [x(i), y(v)])
  const line = pts.map((c, i) => (i ? 'L' : 'M') + c[0].toFixed(1) + ' ' + c[1].toFixed(1)).join(' ')
  const area = `${line} L ${W} ${H} L 0 ${H} Z`
  return { line, area, last: pts[pts.length - 1] }
})
</script>

<template>
  <svg
    v-if="geo"
    :viewBox="`0 0 ${W} ${height}`"
    preserveAspectRatio="none"
    class="block w-full"
    :style="{ height: height + 'px' }"
    aria-hidden="true"
  >
    <defs>
      <linearGradient :id="gid" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" :stop-color="color" stop-opacity="0.28" />
        <stop offset="1" :stop-color="color" stop-opacity="0" />
      </linearGradient>
    </defs>
    <path :d="geo.area" :fill="`url(#${gid})`" />
    <path
      :d="geo.line"
      fill="none"
      :stroke="color"
      stroke-width="1.5"
      stroke-linejoin="round"
      stroke-linecap="round"
      vector-effect="non-scaling-stroke"
    />
    <circle
      :cx="geo.last[0]"
      :cy="geo.last[1]"
      r="1.6"
      :fill="color"
      vector-effect="non-scaling-stroke"
    />
  </svg>
</template>
