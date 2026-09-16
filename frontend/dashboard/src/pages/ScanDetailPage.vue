<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ChevronLeft, ChevronDown, Loader2 } from '@lucide/vue'

import { useScansStore } from '@/stores/scans'
import StatusPill from '@/components/StatusPill.vue'
import { SeverityBadge } from '@/components/ui/severity-badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

const route = useRoute()
const scans = useScansStore()

const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info']
const TERMINAL = new Set(['done', 'error'])
const loading = ref(true)
const open = ref({})
const showReport = ref(false)
let timer = null

const scan = computed(() => scans.detail)
const running = computed(() => scan.value && !TERMINAL.has(scan.value.status))
const counts = computed(() => scan.value?.summary?.counts || {})

const sortedFindings = computed(() =>
  [...(scan.value?.findings || [])].sort(
    (a, b) => SEVERITIES.indexOf(a.severity) - SEVERITIES.indexOf(b.severity)
  )
)

async function refresh() {
  try {
    await scans.fetchDetail(route.params.id)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await refresh()
  timer = window.setInterval(() => {
    if (running.value) refresh()
  }, 2500)
})
onBeforeUnmount(() => timer && window.clearInterval(timer))
</script>

<template>
  <div class="fade-in flex flex-1 flex-col gap-6">
    <router-link
      to="/dashboard"
      class="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ChevronLeft class="size-4" /> Scans
    </router-link>

    <div v-if="loading" class="space-y-4">
      <Skeleton class="h-9 w-72 rounded-lg" />
      <Skeleton class="h-24 rounded-xl" />
      <Skeleton class="h-64 rounded-xl" />
    </div>

    <template v-else-if="scan">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 class="text-2xl font-semibold tracking-tight">{{ scan.target || 'Bundled demo' }}</h1>
          <p class="mt-1 text-sm text-muted-foreground">
            {{ scan.mode }} mode
            <template v-if="scan.engine_scan_id"> · <code>{{ scan.engine_scan_id }}</code></template>
            <template v-if="scan.exit_code != null"> · exit {{ scan.exit_code }}</template>
          </p>
        </div>
        <StatusPill :status="scan.status" />
      </div>

      <Alert v-if="scan.status === 'error'" variant="destructive">
        <AlertTitle>Scan failed</AlertTitle>
        <AlertDescription>{{ scan.error || 'The engine reported an error.' }}</AlertDescription>
      </Alert>

      <Alert v-else-if="running">
        <Loader2 class="size-4 animate-spin" />
        <AlertTitle>The engine is working…</AlertTitle>
        <AlertDescription>Findings will appear here as they land.</AlertDescription>
      </Alert>

      <!-- KPI tiles -->
      <div class="grid grid-cols-2 gap-4 sm:grid-cols-5">
        <Card v-for="sev in SEVERITIES" :key="sev" class="flex flex-col items-center gap-1 p-4">
          <span class="text-2xl font-bold tabular-nums" :class="`text-severity-${sev}`">
            {{ counts[sev] || 0 }}
          </span>
          <span class="text-[11px] uppercase tracking-wide text-muted-foreground">{{ sev }}</span>
        </Card>
      </div>

      <!-- Findings -->
      <section v-if="sortedFindings.length" class="space-y-2">
        <h2 class="text-lg font-semibold tracking-tight">
          Findings <span class="text-muted-foreground">({{ sortedFindings.length }})</span>
        </h2>
        <Card
          v-for="f in sortedFindings"
          :key="f.id"
          class="overflow-hidden border-l-4 p-0"
          :style="{ borderLeftColor: `var(--severity-${f.severity})` }"
        >
          <button
            class="flex w-full items-center gap-3 px-4 py-3 text-left"
            @click="open[f.id] = !open[f.id]"
          >
            <SeverityBadge :severity="f.severity" />
            <span class="min-w-0 flex-1 truncate font-medium">{{ f.title }}</span>
            <span class="hidden items-center gap-1.5 text-xs text-muted-foreground sm:flex">
              <span v-if="f.cvss" class="rounded-full border border-border px-2 py-0.5">
                CVSS {{ Number(f.cvss).toFixed(1) }}
              </span>
              <span v-if="f.cwe" class="rounded-full border border-border px-2 py-0.5">{{ f.cwe }}</span>
              <span v-if="f.agent" class="rounded-full border border-border px-2 py-0.5">{{ f.agent }}</span>
            </span>
            <ChevronDown
              class="size-4 shrink-0 text-muted-foreground transition-transform"
              :class="open[f.id] && 'rotate-180'"
            />
          </button>
          <div v-if="open[f.id]" class="grid gap-3 border-t border-border px-4 py-4 text-sm">
            <div v-if="f.endpoint || f.target" class="grid gap-1">
              <span class="text-[11px] uppercase tracking-wide text-muted-foreground">Location</span>
              <code class="text-xs">{{ f.endpoint || f.target }}</code>
            </div>
            <div v-if="f.evidence" class="grid gap-1">
              <span class="text-[11px] uppercase tracking-wide text-muted-foreground">Evidence</span>
              <span>{{ f.evidence }}</span>
            </div>
            <div v-if="f.command" class="grid gap-1">
              <span class="text-[11px] uppercase tracking-wide text-muted-foreground">Command</span>
              <pre class="overflow-x-auto rounded-md border border-border bg-muted px-3 py-2 text-xs">{{ f.command }}</pre>
            </div>
            <div v-if="f.output" class="grid gap-1">
              <span class="text-[11px] uppercase tracking-wide text-muted-foreground">Output</span>
              <pre class="overflow-x-auto rounded-md border border-border bg-muted px-3 py-2 text-xs">{{ f.output }}</pre>
            </div>
            <div v-if="f.poc" class="grid gap-1">
              <span class="text-[11px] uppercase tracking-wide text-muted-foreground">PoC</span>
              <pre class="overflow-x-auto rounded-md border border-border bg-muted px-3 py-2 text-xs">{{ f.poc }}</pre>
            </div>
            <div v-if="f.remediation" class="grid gap-1">
              <span class="text-[11px] uppercase tracking-wide text-muted-foreground">Remediation</span>
              <span>{{ f.remediation }}</span>
            </div>
          </div>
        </Card>
      </section>

      <p v-else-if="!running" class="text-sm text-muted-foreground">
        No findings were reported for this scan.
      </p>

      <!-- Report -->
      <div v-if="scan.report_md" class="space-y-2">
        <Button variant="ghost" size="sm" class="w-fit" @click="showReport = !showReport">
          {{ showReport ? 'Hide' : 'Show' }} full report
        </Button>
        <pre
          v-if="showReport"
          class="max-h-[520px] overflow-auto rounded-xl border border-border bg-card p-4 text-xs"
          >{{ scan.report_md }}</pre
        >
      </div>
    </template>
  </div>
</template>
