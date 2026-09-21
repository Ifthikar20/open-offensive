<script setup>
import { ref, reactive, computed, watch, nextTick } from 'vue'

const props = defineProps({
  events: { type: Array, default: () => [] },
  live: { type: Boolean, default: false },
})

const LEVELS = {
  system: 'lv-system',
  graph: 'lv-graph',
  phase: 'lv-phase',
  think: 'lv-think',
  skill: 'lv-skill',
  tool: 'lv-tool',
  finding: 'lv-finding',
  report: 'lv-report',
  error: 'lv-error',
}
const levelClass = (l) => LEVELS[l] || 'lv-system'

// Colour agents by role so the eye can follow one specialist through the stream.
const ROLE_CLASS = {
  root: 'ro-root',
  recon: 'ro-recon',
  injection: 'ro-injection',
  access: 'ro-access',
}
const roleClass = (r) => ROLE_CLASS[r] || 'ro-system'

const STATUS_LABEL = {
  spawning: 'spawning',
  running: 'running',
  waiting: 'waiting',
  done: 'done',
  stopped: 'stopped',
}

function fmtTime(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const p = (n, w = 2) => String(n).padStart(w, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`
}

// Live agent roster derived from the event stream: who exists, their role, and
// their latest status — this is the "who's running / picking up next" view.
const agents = computed(() => {
  const m = new Map()
  for (const e of props.events) {
    const id = e.agent_id
    if (!id || id === 'system') continue
    let a = m.get(id)
    if (!a) {
      a = { id, name: e.agent || 'agent', role: e.role || 'agent', status: 'spawning' }
      m.set(id, a)
    }
    if (e.agent) a.name = e.agent
    if (e.role) a.role = e.role
    if (e.level === 'graph' && e.data && e.data.status) a.status = e.data.status
  }
  // Root first, then in the order they appeared.
  return [...m.values()].sort((x, y) => (y.role === 'root') - (x.role === 'root'))
})

// Per-row expand state (tool output / finding detail).
const openSeqs = reactive({})
const toggle = (seq) => { openSeqs[seq] = !openSeqs[seq] }

const toolOutput = (e) => (e.level === 'tool' ? e.data?.output || '' : '')
const findingOf = (e) => (e.level === 'finding' ? e.data?.finding || null : null)
const isReasoning = (e) => e.level === 'think' && !!e.data?.reasoning
const isThink = (e) => e.level === 'think'
const hasDetail = (e) => !!(toolOutput(e) || findingOf(e))

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

    <!-- Live agent roster: who's running / who's next -->
    <div v-if="agents.length" class="al-agents">
      <span
        v-for="a in agents"
        :key="a.id"
        class="al-agent"
        :class="[roleClass(a.role), `st-${a.status}`]"
        :title="`${a.role} · ${STATUS_LABEL[a.status] || a.status}`"
      >
        <span class="al-agent-dot" :class="{ spin: a.status === 'running' }" />
        <b>{{ a.name }}</b>
        <span class="al-agent-st">{{ STATUS_LABEL[a.status] || a.status }}</span>
      </span>
    </div>

    <div ref="scroller" class="al-body" @scroll="onScroll">
      <div
        v-for="e in events"
        :key="e.seq"
        class="al-row"
        :class="{ 'is-think': isThink(e), 'is-reason': isReasoning(e) }"
      >
        <div class="al-head">
          <span class="c-time">{{ fmtTime(e.ts) }}</span>
          <span class="c-level"><span class="chip" :class="levelClass(e.level)">{{ e.level }}</span></span>
          <span class="c-agent" :class="roleClass(e.role)">{{ e.agent }}</span>
          <span v-if="isReasoning(e)" class="reason-tag">reasoning</span>
          <span class="c-msg" :class="{ wrap: isThink(e) }">{{ e.message }}</span>
          <button v-if="hasDetail(e)" class="c-exp" type="button" @click="toggle(e.seq)">
            {{ openSeqs[e.seq] ? '−' : '+' }}
          </button>
        </div>

        <!-- expandable detail: real tool output, or a filed finding -->
        <div v-if="hasDetail(e) && openSeqs[e.seq]" class="al-detail">
          <pre v-if="toolOutput(e)" class="al-out">{{ toolOutput(e) }}</pre>
          <div v-else-if="findingOf(e)" class="al-find">
            <div>
              <b>{{ findingOf(e).severity }}</b>
              <template v-if="findingOf(e).cvss"> · CVSS {{ findingOf(e).cvss }}</template>
              — {{ findingOf(e).title }}
            </div>
            <div v-if="findingOf(e).endpoint" class="al-find-k">
              endpoint <code>{{ findingOf(e).endpoint }}</code>
            </div>
            <div v-if="findingOf(e).evidence" class="al-find-k">{{ findingOf(e).evidence }}</div>
            <div v-if="findingOf(e).remediation" class="al-find-fix">
              fix: {{ findingOf(e).remediation }}
            </div>
          </div>
        </div>
      </div>

      <div v-if="events.length === 0" class="al-empty">
        {{ live ? 'Waiting for the agents to start…' : 'No activity recorded for this scan.' }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.agentlog {
  /* Follows the app theme: a light console in light mode, near-black in dark. */
  --al-bg: var(--card);
  --al-bar: var(--muted);
  --al-line: var(--border);
  --al-ink: var(--foreground);
  --al-mut: var(--muted-foreground);
  --al-hover: color-mix(in srgb, var(--foreground) 6%, transparent);
  --al-row: color-mix(in srgb, var(--foreground) 3%, transparent);
  --al-blue: #2563eb;
  --ro-root: var(--brand-accent);
  --ro-recon: #2563eb;
  --ro-injection: var(--severity-high);
  --ro-access: var(--severity-medium);
  --ro-system: var(--muted-foreground);
  border: 1px solid var(--al-line);
  border-radius: 14px;
  overflow: hidden;
  background: var(--al-bg);
  box-shadow: var(--shadow-card, 0 1px 2px rgba(20, 20, 18, 0.05));
}
[data-theme='dark'] .agentlog {
  --al-blue: #6ea8fe;
  --ro-recon: #6ea8fe;
}
.al-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 14px;
  background: var(--al-bar);
  border-bottom: 1px solid var(--al-line);
}
.al-title { font-size: 13px; font-weight: 600; color: var(--al-ink); }
.al-live {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 600; color: var(--color-success);
}
.al-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--color-success); animation: alpulse 1s ease-in-out infinite;
}
@keyframes alpulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
.al-count { margin-left: auto; font-size: 12px; color: var(--al-mut); font-variant-numeric: tabular-nums; }

/* ---- live agent roster ---- */
.al-agents {
  display: flex; flex-wrap: wrap; gap: 8px;
  padding: 10px 14px; border-bottom: 1px solid var(--al-line);
}
.al-agent {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 4px 10px; border-radius: 999px;
  border: 1px solid var(--al-line); background: var(--al-row);
  font-size: 12px; color: var(--al-ink);
}
.al-agent b { font-weight: 600; }
.al-agent-st { color: var(--al-mut); font-size: 11px; }
.al-agent-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--ro, var(--al-mut)); }
.al-agent-dot.spin { animation: alpulse 1s ease-in-out infinite; }
.al-agent.st-done { opacity: 0.7; }
.al-agent.st-stopped { border-color: color-mix(in srgb, var(--color-danger) 50%, var(--al-line)); }
.ro-root { --ro: var(--ro-root); }
.ro-recon { --ro: var(--ro-recon); }
.ro-injection { --ro: var(--ro-injection); }
.ro-access { --ro: var(--ro-access); }
.ro-system { --ro: var(--ro-system); }

/* ---- log body ---- */
.al-body {
  max-height: 460px; overflow: auto;
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  font-size: 12.5px;
}
.al-row { border-bottom: 1px solid color-mix(in srgb, var(--al-line) 55%, transparent); }
.al-row:nth-child(even) { background: var(--al-row); }
.al-row:hover { background: var(--al-hover); }
.al-head {
  display: grid;
  grid-template-columns: 104px 74px 128px minmax(0, 1fr) auto;
  gap: 12px; align-items: start; padding: 6px 14px; min-width: 620px;
}
.c-time { color: var(--al-mut); white-space: nowrap; padding-top: 1px; }
.c-agent {
  color: var(--ro, var(--al-ink)); font-weight: 600;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.reason-tag {
  align-self: center; font-size: 9.5px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.04em; color: var(--brand-accent);
  background: color-mix(in srgb, var(--brand-accent) 15%, transparent);
  padding: 1px 6px; border-radius: 5px;
}
.c-msg { color: var(--al-ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.c-msg.wrap { white-space: pre-wrap; overflow: visible; word-break: break-word; }
.is-think .c-msg { color: color-mix(in srgb, var(--al-ink) 90%, transparent); }
.is-reason .c-msg { font-style: italic; color: color-mix(in srgb, var(--al-ink) 82%, transparent); }
.c-exp {
  border: 1px solid var(--al-line); background: transparent; color: var(--al-mut);
  width: 20px; height: 20px; border-radius: 6px; cursor: pointer; line-height: 1;
  font-size: 14px; align-self: center;
}
.c-exp:hover { color: var(--al-ink); border-color: var(--al-mut); }

/* ---- expandable detail ---- */
.al-detail { padding: 0 14px 10px 118px; }
.al-out {
  margin: 0; padding: 8px 10px; border: 1px solid var(--al-line); border-radius: 8px;
  background: color-mix(in srgb, var(--al-ink) 4%, transparent);
  max-height: 260px; overflow: auto; white-space: pre-wrap; word-break: break-word;
  font-size: 12px; line-height: 1.5; color: var(--al-ink);
}
.al-find {
  border: 1px solid var(--al-line); border-radius: 8px; padding: 8px 10px;
  display: grid; gap: 4px; font-family: var(--font-family, sans-serif); font-size: 12.5px;
}
.al-find-k { color: var(--al-mut); }
.al-find-fix { color: var(--color-success); }
.al-find code { font-family: ui-monospace, Menlo, monospace; }

.chip {
  display: inline-block; font-size: 10.5px; font-weight: 700; padding: 2px 7px;
  border-radius: 6px; text-transform: lowercase; letter-spacing: 0.02em;
  color: var(--lvl); background: color-mix(in srgb, var(--lvl) 16%, transparent);
}
/* Level colours come from theme tokens, so they flip with light/dark. */
.lv-system { --lvl: var(--muted-foreground); }
.lv-think { --lvl: var(--brand-accent); }
.lv-skill { --lvl: var(--severity-low); }
.lv-graph { --lvl: var(--brand-accent); }
.lv-phase { --lvl: var(--color-warning); }
.lv-tool { --lvl: var(--al-blue); }
.lv-finding { --lvl: var(--severity-high); }
.lv-report { --lvl: var(--color-success); }
.lv-error { --lvl: var(--color-danger); }
.al-empty { padding: 28px 14px; text-align: center; color: var(--al-mut); font-size: 13px; }
</style>
