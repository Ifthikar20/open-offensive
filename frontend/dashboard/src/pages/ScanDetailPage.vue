<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ChevronLeft, Loader2, Download } from '@lucide/vue'

import { useScansStore } from '@/stores/scans'
import scansApi from '@/api/scans'
import StatusPill from '@/components/StatusPill.vue'
import AgentLog from '@/components/AgentLog.vue'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

const route = useRoute()
const scans = useScansStore()

const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info']
const TERMINAL = new Set(['done', 'error'])
const loading = ref(true)
const error = ref('')
const showReport = ref(false)
const downloading = ref(false)
const pdfTemplate = ref('technical')
const pdfError = ref('')
const events = ref([])
const lastSeq = ref(0)
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
    error.value = ''
  } catch (e) {
    error.value = e?.displayMessage || 'The scan could not be loaded.'
  } finally {
    loading.value = false
  }
}

async function fetchEvents() {
  try {
    const { data } = await scansApi.events(route.params.id, lastSeq.value)
    if (data.events && data.events.length) {
      events.value = events.value.concat(data.events)
      lastSeq.value = data.last_seq
    }
  } catch {
    /* keep the events we already have on a transient error */
  }
}

async function downloadPdf() {
  pdfError.value = ''
  downloading.value = true
  try {
    const res = await scansApi.reportPdf(route.params.id, pdfTemplate.value)
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `openoffensive-report-${route.params.id}-${pdfTemplate.value}.pdf`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch (e) {
    // With responseType 'blob' the error body is a Blob — read the real message out.
    let msg = e?.displayMessage
    try {
      const text = await e?.response?.data?.text?.()
      if (text) {
        const j = JSON.parse(text)
        msg = j.detail || j.error || msg
      }
    } catch {
      /* fall back to displayMessage */
    }
    pdfError.value = msg || 'Could not generate the report.'
  } finally {
    downloading.value = false
  }
}

onMounted(async () => {
  await refresh()
  await fetchEvents()
  timer = window.setInterval(async () => {
    if (running.value) {
      await refresh()
      await fetchEvents()
    } else if (timer) {
      window.clearInterval(timer)
      timer = null
    }
  }, 1500)
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
          <h1 class="text-2xl font-semibold tracking-tight">{{ scan.target }}</h1>
          <p class="mt-1 text-sm text-muted-foreground">
            {{ scan.mode }} mode
            <template v-if="scan.engine_scan_id"> · <code>{{ scan.engine_scan_id }}</code></template>
            <template v-if="scan.exit_code != null"> · exit {{ scan.exit_code }}</template>
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <template v-if="scan.status === 'done'">
            <select
              v-model="pdfTemplate"
              class="h-9 rounded-md border border-border bg-card px-2 text-sm"
              aria-label="Report template"
            >
              <option value="technical">Technical</option>
              <option value="executive">Executive</option>
              <option value="owasp">OWASP</option>
            </select>
            <Button size="sm" variant="outline" :disabled="downloading" @click="downloadPdf">
              <Download class="size-4" />
              {{ downloading ? 'Preparing…' : 'Download PDF' }}
            </Button>
          </template>
          <StatusPill :status="scan.status" />
        </div>
      </div>

      <Alert v-if="pdfError" variant="destructive">
        <AlertTitle>Report export failed</AlertTitle>
        <AlertDescription>{{ pdfError }}</AlertDescription>
      </Alert>

      <Alert v-if="scan.status === 'error'" variant="destructive">
        <AlertTitle>Scan failed</AlertTitle>
        <AlertDescription>{{ scan.error || 'The engine reported an error but captured no message.' }}</AlertDescription>
      </Alert>

      <Alert v-else-if="running">
        <Loader2 class="size-4 animate-spin" />
        <AlertTitle>The engine is working…</AlertTitle>
        <AlertDescription>Findings will appear here as they land.</AlertDescription>
      </Alert>

      <!-- severity summary -->
      <div class="flex flex-wrap items-center gap-x-5 gap-y-2 text-[13px]">
        <span class="text-sm font-semibold">
          {{ sortedFindings.length }} finding{{ sortedFindings.length === 1 ? '' : 's' }}
        </span>
        <span class="h-3.5 w-px bg-border" />
        <span
          v-for="sev in SEVERITIES"
          :key="sev"
          class="inline-flex items-center gap-1.5"
          :class="(counts[sev] || 0) ? '' : 'opacity-40'"
        >
          <span class="size-2 rounded-full" :style="{ background: `var(--severity-${sev})` }" />
          <span class="font-semibold tabular-nums">{{ counts[sev] || 0 }}</span>
          <span class="text-muted-foreground">{{ sev }}</span>
        </span>
      </div>

      <!-- Live agent activity -->
      <section class="space-y-2">
        <h2 class="text-lg font-semibold tracking-tight">Activity</h2>
        <AgentLog :events="events" :live="running" />
      </section>

      <!-- Findings — pentest-report style -->
      <section v-if="sortedFindings.length" class="space-y-3">
        <h2 class="text-lg font-semibold tracking-tight">
          Findings <span class="text-muted-foreground">({{ sortedFindings.length }})</span>
        </h2>
        <div class="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card">
          <article v-for="f in sortedFindings" :key="f.id" class="px-5 py-5">
            <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <h3 class="flex flex-wrap items-baseline gap-x-2.5 gap-y-1 text-[15px] font-semibold">
                <span
                  class="text-[11px] font-bold uppercase tracking-wide"
                  :class="`text-severity-${f.severity}`"
                >
                  {{ f.severity }}<template v-if="f.cvss"> · CVSS {{ Number(f.cvss).toFixed(1) }}</template>
                </span>
                <span>{{ f.title }}</span>
              </h3>
              <code class="shrink-0 text-xs text-muted-foreground">
                {{ f.id }}<template v-if="f.cwe"> · {{ f.cwe }}</template>
              </code>
            </div>

            <div
              v-if="f.endpoint || f.target || f.agent"
              class="mt-2 flex flex-wrap gap-x-6 gap-y-1 font-mono text-xs text-muted-foreground"
            >
              <span v-if="f.endpoint || f.target">
                <span class="opacity-60">endpoint</span> {{ f.endpoint || f.target }}
              </span>
              <span v-if="f.agent"><span class="opacity-60">found by</span> {{ f.agent }}</span>
            </div>

            <div class="mt-4 grid gap-3.5 text-sm">
              <div v-if="f.evidence" class="grid gap-1">
                <span class="text-[11px] uppercase tracking-wide text-muted-foreground">Evidence</span>
                <p class="leading-relaxed">{{ f.evidence }}</p>
              </div>
              <div v-if="f.command" class="grid gap-1">
                <span class="text-[11px] uppercase tracking-wide text-muted-foreground">Command</span>
                <pre class="overflow-x-auto rounded-md border border-border bg-muted px-3 py-2 font-mono text-xs leading-relaxed">{{ f.command }}</pre>
              </div>
              <div v-if="f.output" class="grid gap-1">
                <span class="text-[11px] uppercase tracking-wide text-muted-foreground">Output</span>
                <pre class="max-h-56 overflow-auto rounded-md border border-border bg-muted px-3 py-2 font-mono text-xs leading-relaxed">{{ f.output }}</pre>
              </div>
              <div v-if="f.poc" class="grid gap-1">
                <span class="text-[11px] uppercase tracking-wide text-muted-foreground">Proof of concept</span>
                <pre class="overflow-x-auto rounded-md border border-border bg-muted px-3 py-2 font-mono text-xs leading-relaxed">{{ f.poc }}</pre>
              </div>
              <div v-if="f.remediation" class="grid gap-1">
                <span class="text-[11px] font-semibold uppercase tracking-wide text-[color:var(--color-success)]">Fix</span>
                <p class="leading-relaxed">{{ f.remediation }}</p>
              </div>
            </div>
          </article>
        </div>
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

    <Alert v-else variant="destructive">
      <AlertTitle>Couldn't load this scan</AlertTitle>
      <AlertDescription>{{ error || 'The scan could not be loaded.' }}</AlertDescription>
    </Alert>
  </div>
</template>
