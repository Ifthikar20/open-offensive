<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Radar, Bug, ShieldAlert, Activity, ArrowUpRight, Cpu } from '@lucide/vue'

import { useAuthStore } from '@/stores/auth'
import { useScansStore } from '@/stores/scans'
import StatusPill from '@/components/StatusPill.vue'
import NewScanDialog from '@/components/NewScanDialog.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import RiskGauge from '@/components/charts/RiskGauge.vue'
import SeverityDonut from '@/components/charts/SeverityDonut.vue'
import TrendChart from '@/components/charts/TrendChart.vue'
import SeverityBar from '@/components/charts/SeverityBar.vue'
import MiniSpark from '@/components/charts/MiniSpark.vue'

const router = useRouter()
const auth = useAuthStore()
const scans = useScansStore()

const loading = ref(true)
const error = ref('')
let timer = null

const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info']
// Weighted contribution of one finding at each severity to the risk index.
const WEIGHTS = { critical: 25, high: 10, medium: 4, low: 1, info: 0 }
const TERMINAL = new Set(['done', 'error'])

const SEV_META = [
  ['critical', 'Critical', 'var(--severity-critical)'],
  ['high', 'High', 'var(--severity-high)'],
  ['medium', 'Medium', 'var(--severity-medium)'],
  ['low', 'Low', 'var(--severity-low)'],
  ['info', 'Info', 'var(--severity-info)'],
]
const STATUS_META = [
  ['done', 'Completed', 'var(--color-success)'],
  ['running', 'Running', 'var(--brand-accent)'],
  ['queued', 'Queued', 'var(--color-warning)'],
  ['error', 'Failed', 'var(--color-danger)'],
]

const greeting = computed(() => {
  const h = new Date().getHours()
  const t = h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening'
  return `Good ${t}, ${auth.user?.username || 'operator'}`
})

// One source of truth for a scan's finding total. The engine keeps finding_count
// (len of findings) and summary.total/counts in lock-step; this falls back across
// them so every panel agrees even when the list row carries only a summary.
function nfindings(s) {
  if (typeof s.finding_count === 'number' && s.finding_count > 0) return s.finding_count
  const su = s.summary || {}
  if (typeof su.total === 'number' && su.total > 0) return su.total
  const c = su.counts || {}
  return SEVERITIES.reduce((n, k) => n + (c[k] || 0), 0)
}

// Oldest → newest, for time-ordered charts (the API list is newest-first).
const chrono = computed(() => [...scans.list].reverse())

// Aggregate severity counts across every scan (real numbers only — no fallback).
const totals = computed(() => {
  const acc = { critical: 0, high: 0, medium: 0, low: 0, info: 0 }
  for (const s of scans.list) {
    const c = s.summary?.counts || {}
    for (const k of SEVERITIES) acc[k] += c[k] || 0
  }
  return acc
})

const totalScans = computed(() => scans.list.length)
const totalFindings = computed(() => scans.list.reduce((n, s) => n + nfindings(s), 0))
const criticalHigh = computed(() => totals.value.critical + totals.value.high)
const avgPerRun = computed(() => (totalScans.value ? totalFindings.value / totalScans.value : 0))

const statusCounts = computed(() => {
  const acc = { done: 0, running: 0, queued: 0, error: 0 }
  for (const s of scans.list) if (s.status in acc) acc[s.status] += 1
  return acc
})
const successRate = computed(() => {
  const done = statusCounts.value.done
  const settled = done + statusCounts.value.error
  return settled ? Math.round((done / settled) * 100) : null
})
const anyRunning = computed(() => scans.list.some((s) => !TERMINAL.has(s.status)))

// Risk index: saturating map of weighted severity load onto 0–100.
const riskIndex = computed(() => {
  const weighted = SEVERITIES.reduce((n, k) => n + totals.value[k] * WEIGHTS[k], 0)
  return Math.min(100, Math.round(100 * (1 - Math.exp(-weighted / 60))))
})
const riskBand = computed(() => {
  const v = riskIndex.value
  if (v <= 0) return { label: 'Clear', color: 'var(--color-success)' }
  if (v < 25) return { label: 'Low', color: 'var(--severity-low)' }
  if (v < 50) return { label: 'Guarded', color: 'var(--severity-medium)' }
  if (v < 75) return { label: 'Elevated', color: 'var(--severity-high)' }
  return { label: 'Critical', color: 'var(--severity-critical)' }
})

// Time series (oldest → newest).
const findingsSeries = computed(() => chrono.value.map((s) => nfindings(s)))
const critHighSeries = computed(() =>
  chrono.value.map((s) => (s.summary?.counts?.critical || 0) + (s.summary?.counts?.high || 0))
)
const scanCumSeries = computed(() => chrono.value.map((_, i) => i + 1))
const findingsCumSeries = computed(() => {
  const out = []
  let run = 0
  for (const s of chrono.value) {
    run += nfindings(s)
    out.push(run)
  }
  return out
})
const trendLabels = computed(() => chrono.value.map((s) => fmtDay(s.created_at)))
const peakFindings = computed(() => Math.max(0, ...findingsSeries.value))
const targetsCount = computed(() => new Set(scans.list.map((s) => s.target)).size)

const kpis = computed(() => [
  {
    key: 'scans',
    label: 'Total scans',
    icon: Radar,
    value: totalScans.value,
    spark: scanCumSeries.value,
    color: 'var(--brand-accent)',
    foot: `${statusCounts.value.done} completed`,
  },
  {
    key: 'findings',
    label: 'Findings',
    icon: Bug,
    value: totalFindings.value,
    spark: findingsCumSeries.value,
    color: 'var(--brand-accent)',
    foot: `across ${targetsCount.value} target${targetsCount.value === 1 ? '' : 's'}`,
  },
  {
    key: 'ch',
    label: 'Critical + High',
    icon: ShieldAlert,
    value: criticalHigh.value,
    spark: critHighSeries.value,
    color: 'var(--severity-high)',
    glow: true,
    foot: `${totals.value.critical} critical`,
  },
  {
    key: 'avg',
    label: 'Avg / run',
    icon: Activity,
    value: avgPerRun.value.toFixed(1),
    spark: findingsSeries.value,
    color: 'var(--brand-accent)',
    foot: `peak ${peakFindings.value}`,
  },
])

// Severity legend for the donut panel.
const severityLegend = computed(() =>
  SEV_META.map(([k, label, color]) => {
    const v = totals.value[k]
    return {
      k,
      label,
      color,
      v,
      pct: totalFindings.value ? Math.round((v / totalFindings.value) * 100) : 0,
    }
  })
)

// Top targets by finding volume (grouped across their runs).
const topTargets = computed(() => {
  const m = new Map()
  for (const s of scans.list) {
    const cur = m.get(s.target) || { target: s.target, findings: 0, runs: 0, counts: {} }
    cur.findings += nfindings(s)
    cur.runs += 1
    const c = s.summary?.counts || {}
    for (const k of SEVERITIES) cur.counts[k] = (cur.counts[k] || 0) + (c[k] || 0)
    m.set(s.target, cur)
  }
  const rows = [...m.values()].filter((r) => r.findings > 0).sort((a, b) => b.findings - a.findings)
  const max = Math.max(1, ...rows.map((r) => r.findings))
  return rows.slice(0, 5).map((r) => ({ ...r, pct: Math.max(6, (r.findings / max) * 100) }))
})

const recent = computed(() => scans.list.slice(0, 6))

const avgDuration = computed(() => {
  const d = scans.list.map((s) => s.summary?.duration).filter((x) => typeof x === 'number' && x > 0)
  return d.length ? d.reduce((a, b) => a + b, 0) / d.length : null
})
const lastRunAt = computed(() => scans.list[0]?.created_at || null)

function fmtDay(iso) {
  return iso ? new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : ''
}
function fmtDur(sec) {
  if (sec == null) return '—'
  return sec < 60 ? `${Math.round(sec)}s` : `${(sec / 60).toFixed(1)}m`
}
function ago(iso) {
  if (!iso) return '—'
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'just now'
  const m = s / 60
  if (m < 60) return `${Math.floor(m)}m ago`
  const h = m / 60
  if (h < 24) return `${Math.floor(h)}h ago`
  const d = h / 24
  if (d < 7) return `${Math.floor(d)}d ago`
  return fmtDay(iso)
}

async function refresh() {
  try {
    await scans.fetchList()
    error.value = ''
  } catch (e) {
    error.value = e?.displayMessage || 'Could not reach the server.'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await refresh()
  timer = window.setInterval(() => {
    if (anyRunning.value) refresh()
  }, 2500)
})
onBeforeUnmount(() => timer && window.clearInterval(timer))
</script>

<template>
  <div class="cc fade-in flex flex-1 flex-col gap-5">
    <!-- Header -->
    <div class="cc-top flex flex-wrap items-start justify-between gap-4">
      <div>
        <div class="cc-eyebrow">Threat console</div>
        <h1 class="mt-1 text-2xl font-semibold tracking-tight">{{ greeting }}</h1>
        <p class="mt-1 text-sm text-muted-foreground">
          Live posture across every target the engine has assessed.
        </p>
      </div>
      <span class="cc-live" :data-on="anyRunning">
        <span class="cc-live-dot" />
        {{ anyRunning ? 'Scanning' : 'Idle' }}
      </span>
    </div>

    <!-- Telemetry strip -->
    <div v-if="!loading && !error && totalScans" class="cc-strip">
      <span class="cc-strip-item"><b>OPERATOR</b> {{ auth.user?.username || '—' }}</span>
      <span class="cc-strip-item"><b>SCANS</b> {{ totalScans }}</span>
      <span class="cc-strip-item"><b>FINDINGS</b> {{ totalFindings }}</span>
      <span class="cc-strip-item"><b>LAST RUN</b> {{ ago(lastRunAt) }}</span>
      <span class="cc-strip-item"><b>AVG TIME</b> {{ fmtDur(avgDuration) }}</span>
      <span class="cc-strip-item cc-strip-eng"><Cpu class="size-3" /> ENGINE · LLM</span>
    </div>

    <!-- Loading -->
    <template v-if="loading">
      <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Skeleton v-for="n in 4" :key="n" class="h-28 rounded-2xl" />
      </div>
      <div class="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <Skeleton class="h-72 rounded-2xl lg:col-span-5" />
        <Skeleton class="h-72 rounded-2xl lg:col-span-3" />
        <Skeleton class="h-72 rounded-2xl lg:col-span-4" />
      </div>
    </template>

    <!-- Error -->
    <Alert v-else-if="error" variant="destructive">
      <AlertTitle>Couldn't load your console</AlertTitle>
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <!-- Empty -->
    <EmptyState
      v-else-if="totalScans === 0"
      variant="panel"
      title="No telemetry yet"
      body="Run your first scan to light up the console. Point the engine at a git repo, a live URL, or a local path — findings, risk, and trends appear here in real time."
    >
      <NewScanDialog />
    </EmptyState>

    <!-- Console -->
    <template v-else>
      <!-- KPI strip -->
      <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <section v-for="k in kpis" :key="k.key" class="cc-panel cc-kpi">
          <div class="flex items-center justify-between">
            <span class="cc-label"><span class="cc-tick" />{{ k.label }}</span>
            <component :is="k.icon" class="size-4 text-muted-foreground" />
          </div>
          <div
            class="cc-num mt-2 text-3xl font-bold"
            :class="k.glow && 'cc-glow'"
            :style="k.glow ? { color: k.color } : {}"
          >
            {{ k.value }}
          </div>
          <div class="mt-2 h-9">
            <MiniSpark :points="k.spark" :color="k.color" :height="34" />
          </div>
          <div class="cc-foot mt-1">{{ k.foot }}</div>
        </section>
      </div>

      <!-- Row: risk · severity · operations -->
      <div class="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <!-- Risk index -->
        <section class="cc-panel lg:col-span-5">
          <header class="cc-panel-head">
            <span class="cc-label"><span class="cc-tick" :style="{ background: riskBand.color }" />Risk index</span>
            <span class="cc-foot">weighted exposure</span>
          </header>
          <div class="cc-panel-body flex flex-col items-center gap-4">
            <RiskGauge
              :value="riskIndex"
              :color="riskBand.color"
              :band="riskBand.label"
              caption="risk index"
            />
            <div class="w-full">
              <div class="mb-1.5 flex items-center justify-between">
                <span class="cc-foot">Severity load</span>
                <span class="cc-foot">{{ totalFindings }} findings</span>
              </div>
              <SeverityBar :counts="totals" :height="10" />
              <div class="mt-3 grid grid-cols-5 gap-1 text-center">
                <div v-for="s in severityLegend" :key="s.k" class="flex flex-col items-center gap-1">
                  <span class="cc-num text-sm font-bold" :style="{ color: s.color }">{{ s.v }}</span>
                  <span class="cc-mini-label">{{ s.label }}</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- Severity mix -->
        <section class="cc-panel lg:col-span-3">
          <header class="cc-panel-head">
            <span class="cc-label"><span class="cc-tick" />Severity mix</span>
          </header>
          <div class="cc-panel-body flex flex-col items-center gap-4">
            <SeverityDonut :counts="totals" />
            <ul class="w-full space-y-1.5">
              <li v-for="s in severityLegend" :key="s.k" class="flex items-center gap-2 text-sm">
                <span class="cc-dot" :style="{ '--g': s.color, background: s.color }" />
                <span class="text-muted-foreground">{{ s.label }}</span>
                <span class="cc-num ml-auto font-semibold">{{ s.v }}</span>
                <span class="cc-foot w-9 text-right">{{ s.pct }}%</span>
              </li>
            </ul>
          </div>
        </section>

        <!-- Operations -->
        <section class="cc-panel lg:col-span-4">
          <header class="cc-panel-head">
            <span class="cc-label"><span class="cc-tick" />Operations</span>
            <span v-if="successRate !== null" class="cc-foot">{{ successRate }}% success</span>
          </header>
          <div class="cc-panel-body flex flex-col gap-3">
            <div class="flex items-baseline gap-2">
              <span class="cc-num text-4xl font-bold">{{ totalScans }}</span>
              <span class="cc-foot">runs total</span>
            </div>
            <ul class="space-y-2.5">
              <li v-for="[key, label, color] in STATUS_META" :key="key" class="flex items-center gap-3">
                <span class="cc-dot" :style="{ '--g': color, background: color }" />
                <span class="w-20 text-sm text-muted-foreground">{{ label }}</span>
                <span class="cc-ops-track">
                  <span
                    class="cc-ops-fill"
                    :style="{
                      width: (statusCounts[key] / Math.max(totalScans, 1)) * 100 + '%',
                      background: color,
                    }"
                  />
                </span>
                <span class="cc-num w-6 text-right text-sm font-semibold">{{ statusCounts[key] }}</span>
              </li>
            </ul>
            <div class="cc-foot mt-auto flex items-center justify-between border-t border-border pt-3">
              <span>Avg duration</span>
              <span class="cc-num text-foreground">{{ fmtDur(avgDuration) }}</span>
            </div>
          </div>
        </section>
      </div>

      <!-- Row: trend · top targets -->
      <div class="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <!-- Findings per run -->
        <section class="cc-panel lg:col-span-8">
          <header class="cc-panel-head">
            <span class="cc-label"><span class="cc-tick" />Findings per run</span>
            <span class="cc-foot">{{ totalScans }} runs · peak {{ peakFindings }}</span>
          </header>
          <div class="cc-panel-body">
            <div class="h-52">
              <TrendChart :points="findingsSeries" :labels="trendLabels" color="var(--brand-accent)" />
            </div>
          </div>
        </section>

        <!-- Top targets -->
        <section class="cc-panel lg:col-span-4">
          <header class="cc-panel-head">
            <span class="cc-label"><span class="cc-tick" />Top targets</span>
            <span class="cc-foot">by findings</span>
          </header>
          <div class="cc-panel-body">
            <ul v-if="topTargets.length" class="space-y-3.5">
              <li v-for="t in topTargets" :key="t.target">
                <div class="mb-1 flex items-center justify-between gap-2">
                  <span class="cc-mono truncate text-sm" :title="t.target">{{ t.target }}</span>
                  <span class="cc-num text-sm font-semibold">{{ t.findings }}</span>
                </div>
                <div class="cc-tt-track">
                  <div class="cc-tt-fill" :style="{ width: t.pct + '%' }">
                    <SeverityBar :counts="t.counts" :height="8" />
                  </div>
                </div>
              </li>
            </ul>
            <p v-else class="cc-foot py-8 text-center">No findings recorded yet.</p>
          </div>
        </section>
      </div>

      <!-- Recent activity -->
      <section class="cc-panel">
        <header class="cc-panel-head">
          <span class="cc-label"><span class="cc-tick" />Recent activity</span>
          <router-link to="/history" class="cc-viewall">
            View all <ArrowUpRight class="size-3" />
          </router-link>
        </header>
        <ul class="divide-y divide-border">
          <li v-for="s in recent" :key="s.id">
            <button class="cc-feed-row" @click="router.push({ name: 'scan-detail', params: { id: s.id } })">
              <StatusPill :status="s.status" class="cc-feed-status" />
              <span class="cc-mono truncate" :title="s.target">{{ s.target }}</span>
              <div class="cc-feed-bar"><SeverityBar :counts="s.summary?.counts || {}" :height="7" /></div>
              <span class="cc-num cc-feed-count">{{ nfindings(s) }}</span>
              <span class="cc-foot cc-feed-time">{{ ago(s.created_at) }}</span>
            </button>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.cc {
  --cc-grid: var(--border);
}
/* Faint blueprint grid, fading out from the top-left — the command-center bed. */
.cc::before {
  content: '';
  position: absolute;
  inset: -24px -24px auto -24px;
  height: 460px;
  z-index: 0;
  pointer-events: none;
  background-image:
    linear-gradient(to right, var(--cc-grid) 1px, transparent 1px),
    linear-gradient(to bottom, var(--cc-grid) 1px, transparent 1px);
  background-size: 34px 34px;
  -webkit-mask-image: radial-gradient(130% 90% at 18% -20%, #000 0%, transparent 68%);
  mask-image: radial-gradient(130% 90% at 18% -20%, #000 0%, transparent 68%);
  opacity: 0.8;
}
.cc > * {
  position: relative;
  z-index: 1;
}

.cc-eyebrow {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, 'Cascadia Code', monospace;
  font-size: 0.66rem;
  font-weight: 600;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: var(--brand-accent);
}

/* Live pill */
.cc-live {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border);
  border-radius: 9999px;
  padding: 4px 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, 'Cascadia Code', monospace;
  font-size: 0.64rem;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--muted-foreground);
}
.cc-live-dot {
  width: 7px;
  height: 7px;
  border-radius: 9999px;
  background: var(--muted-foreground);
}
.cc-live[data-on='true'] {
  color: var(--brand-accent);
  border-color: color-mix(in srgb, var(--brand-accent) 40%, transparent);
}
.cc-live[data-on='true'] .cc-live-dot {
  background: var(--brand-accent);
  box-shadow: 0 0 8px var(--brand-accent);
  animation: cc-pulse 1.4s ease-in-out infinite;
}
@keyframes cc-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}

/* Telemetry strip */
.cc-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 20px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: color-mix(in srgb, var(--card) 60%, transparent);
  padding: 10px 16px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, 'Cascadia Code', monospace;
  font-size: 0.68rem;
  color: var(--foreground);
}
.cc-strip-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.cc-strip-item b {
  font-weight: 600;
  letter-spacing: 0.12em;
  color: var(--muted-foreground);
}
.cc-strip-eng {
  color: var(--brand-accent);
  letter-spacing: 0.1em;
}

/* Panels */
.cc-panel {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: var(--card);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}
.cc-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 11px 16px;
  border-bottom: 1px solid var(--border);
}
.cc-panel-body {
  flex: 1;
  padding: 16px;
}
.cc-kpi {
  padding: 16px;
}

/* Console typography */
.cc-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, 'Cascadia Code', monospace;
  font-size: 0.62rem;
  font-weight: 600;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--muted-foreground);
}
.cc-tick {
  width: 7px;
  height: 7px;
  border-radius: 2px;
  background: var(--brand-accent);
  box-shadow: 0 0 6px color-mix(in srgb, var(--brand-accent) 65%, transparent);
}
.cc-num {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, 'Cascadia Code', monospace;
  font-variant-numeric: tabular-nums;
}
.cc-glow {
  text-shadow: 0 0 22px color-mix(in srgb, currentColor 45%, transparent);
}
.cc-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, 'Cascadia Code', monospace;
}
.cc-foot {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, 'Cascadia Code', monospace;
  font-size: 0.62rem;
  letter-spacing: 0.04em;
  color: var(--muted-foreground);
}
.cc-mini-label {
  font-size: 0.56rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted-foreground);
}
.cc-dot {
  width: 8px;
  height: 8px;
  border-radius: 9999px;
  flex-shrink: 0;
  box-shadow: 0 0 6px color-mix(in srgb, var(--g) 55%, transparent);
}

/* Operations bars */
.cc-ops-track {
  flex: 1;
  height: 6px;
  border-radius: 9999px;
  background: var(--muted);
  overflow: hidden;
}
.cc-ops-fill {
  display: block;
  height: 100%;
  border-radius: 9999px;
  transition: width 500ms cubic-bezier(0.23, 1, 0.32, 1);
}

/* Top-targets magnitude + mix */
.cc-tt-track {
  width: 100%;
}
.cc-tt-fill {
  transition: width 500ms cubic-bezier(0.23, 1, 0.32, 1);
}

.cc-viewall {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, 'Cascadia Code', monospace;
  font-size: 0.62rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--brand-accent);
}
.cc-viewall:hover {
  text-decoration: underline;
}

/* Recent feed */
.cc-feed-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 11px 16px;
  text-align: left;
  cursor: pointer;
  transition: background 150ms ease;
}
.cc-feed-row:hover {
  background: var(--card-hover, var(--muted));
}
.cc-feed-bar {
  display: none;
}
.cc-feed-count {
  min-width: 28px;
  text-align: right;
  font-size: 0.85rem;
  font-weight: 600;
}
.cc-feed-time {
  min-width: 64px;
  text-align: right;
}
@media (min-width: 640px) {
  .cc-feed-row {
    grid-template-columns: 96px minmax(0, 1fr) 180px 44px 84px;
  }
  .cc-feed-bar {
    display: block;
  }
}
</style>
