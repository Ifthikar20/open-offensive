<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  events: { type: Array, default: () => [] },
  live: { type: Boolean, default: false },
})

const LEVELS = {
  system: 'lv-system',
  graph: 'lv-graph',
  phase: 'lv-phase',
  think: 'lv-think',
  tool: 'lv-tool',
  finding: 'lv-finding',
  report: 'lv-report',
  error: 'lv-error',
}
const levelClass = (l) => LEVELS[l] || 'lv-system'

function fmtTime(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const p = (n, w = 2) => String(n).padStart(w, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`
}

// Stick to the newest row unless the user has scrolled up to read history.
const scroller = ref(null)
const stick = ref(true)
function onScroll() {
  const el = scroller.value
  if (!el) return
  stick.value = el.scrollHeight - el.scrollTop - el.clientHeight < 48
}
watch(
  () => props.events.length,
  async () => {
    if (!stick.value) return
    await nextTick()
    const el = scroller.value
    if (el) el.scrollTop = el.scrollHeight
  }
)
</script>

<template>
  <div class="agentlog">
    <div class="al-bar">
      <span class="al-title">Agent activity</span>
      <span v-if="live" class="al-live"><span class="al-dot" /> Live</span>
      <span class="al-count">{{ events.length }} event{{ events.length === 1 ? '' : 's' }}</span>
    </div>

    <div class="al-head">
      <span>Time</span><span>Level</span><span>Agent</span><span>Message</span>
    </div>

    <div ref="scroller" class="al-body" @scroll="onScroll">
      <div v-for="e in events" :key="e.seq" class="al-row" :title="e.message">
        <span class="c-time">{{ fmtTime(e.ts) }}</span>
        <span class="c-level"><span class="chip" :class="levelClass(e.level)">{{ e.level }}</span></span>
        <span class="c-agent">{{ e.agent }}</span>
        <span class="c-msg">{{ e.message }}</span>
      </div>

      <div v-if="events.length === 0" class="al-empty">
        {{ live ? 'Waiting for the agents to start…' : 'No activity recorded for this scan.' }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.agentlog {
  --al-bg: #0f0f12;
  --al-bar: #16161a;
  --al-line: rgba(255, 255, 255, 0.07);
  --al-ink: #d9d5ca;
  --al-mut: #86847a;
  border: 1px solid var(--al-line);
  border-radius: 14px;
  overflow: hidden;
  background: var(--al-bg);
  box-shadow: 0 20px 50px -30px rgba(0, 0, 0, 0.6);
}
.al-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 14px;
  background: var(--al-bar);
  border-bottom: 1px solid var(--al-line);
}
.al-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--al-ink);
}
.al-live {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #4ade80;
}
.al-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #4ade80;
  animation: alpulse 1s ease-in-out infinite;
}
@keyframes alpulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
}
.al-count {
  margin-left: auto;
  font-size: 12px;
  color: var(--al-mut);
  font-variant-numeric: tabular-nums;
}
.al-head,
.al-row {
  display: grid;
  grid-template-columns: 108px 78px 132px minmax(0, 1fr);
  gap: 14px;
  align-items: center;
  padding: 0 14px;
  min-width: 620px;
}
.al-head {
  height: 30px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--al-mut);
  border-bottom: 1px solid var(--al-line);
  overflow-x: auto;
}
.al-body {
  max-height: 440px;
  overflow: auto;
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  font-size: 12.5px;
}
.al-row {
  height: 30px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.035);
}
.al-row:hover {
  background: rgba(255, 255, 255, 0.03);
}
.c-time {
  color: var(--al-mut);
  white-space: nowrap;
}
.c-agent {
  color: #c7c3b6;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.c-msg {
  color: var(--al-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.chip {
  display: inline-block;
  font-size: 10.5px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 6px;
  text-transform: lowercase;
  letter-spacing: 0.02em;
}
.lv-system { color: #9a9788; background: rgba(154, 151, 136, 0.14); }
.lv-graph { color: #a78bfa; background: rgba(167, 139, 250, 0.16); }
.lv-phase { color: #f0a35a; background: rgba(240, 163, 90, 0.16); }
.lv-think { color: #8a8778; background: rgba(138, 135, 120, 0.12); }
.lv-tool { color: #6ea8fe; background: rgba(110, 168, 254, 0.16); }
.lv-finding { color: #ffa657; background: rgba(255, 166, 87, 0.16); }
.lv-report { color: #4ade80; background: rgba(74, 222, 128, 0.16); }
.lv-error { color: #ff6b6b; background: rgba(255, 107, 107, 0.16); }
.al-empty {
  padding: 28px 14px;
  text-align: center;
  color: var(--al-mut);
  font-size: 13px;
}
</style>
