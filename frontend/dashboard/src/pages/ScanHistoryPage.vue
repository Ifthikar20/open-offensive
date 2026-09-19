<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'

import { useScansStore } from '@/stores/scans'
import StatusPill from '@/components/StatusPill.vue'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import EmptyState from '@/components/ui/EmptyState.vue'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'

const router = useRouter()
const scans = useScansStore()

const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info']
const TERMINAL = new Set(['done', 'error'])

const loading = ref(true)
const error = ref('')
let timer = null

const query = ref('')
const statusFilter = ref('')
const minSev = ref('')
const sortKey = ref('newest')

const anyRunning = computed(() => scans.list.some((s) => !TERMINAL.has(s.status)))

function fmt(iso) {
  return iso
    ? new Date(iso).toLocaleString(undefined, {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
      })
    : '—'
}

const filtered = computed(() => {
  let list = scans.list.slice()
  const q = query.value.trim().toLowerCase()
  if (q) list = list.filter((s) => (s.target || '').toLowerCase().includes(q))
  if (statusFilter.value) list = list.filter((s) => s.status === statusFilter.value)
  if (minSev.value) {
    const upto = SEVERITIES.slice(0, SEVERITIES.indexOf(minSev.value) + 1)
    list = list.filter((s) => {
      const c = s.summary?.counts || {}
      return upto.some((sev) => (c[sev] || 0) > 0)
    })
  }
  if (sortKey.value === 'oldest') {
    list.sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
  } else if (sortKey.value === 'findings') {
    list.sort((a, b) => (b.finding_count || 0) - (a.finding_count || 0))
  } else {
    list.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
  }
  return list
})

// Light date grouping for the date-sorted views; flat for the findings sort.
const groups = computed(() => {
  if (sortKey.value === 'findings') return [{ label: null, rows: filtered.value }]
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const weekAgo = startOfToday - 6 * 86400000
  const buckets = { Today: [], 'This week': [], Earlier: [] }
  for (const s of filtered.value) {
    const t = new Date(s.created_at).getTime()
    if (t >= startOfToday) buckets['Today'].push(s)
    else if (t >= weekAgo) buckets['This week'].push(s)
    else buckets['Earlier'].push(s)
  }
  return Object.entries(buckets)
    .filter(([, rows]) => rows.length)
    .map(([label, rows]) => ({ label, rows }))
})

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
  <div class="fade-in flex flex-1 flex-col gap-6">
    <div>
      <h1 class="text-2xl font-semibold tracking-tight">Scan history</h1>
      <p class="mt-1 text-sm text-muted-foreground">Every scan you've run, searchable and filterable.</p>
    </div>

    <!-- filter bar -->
    <div class="flex flex-wrap items-center gap-2">
      <Input v-model="query" placeholder="Search target…" class="h-9 max-w-xs" />
      <select v-model="statusFilter" class="h-9 rounded-md border border-border bg-card px-2 text-sm" aria-label="Status">
        <option value="">All statuses</option>
        <option value="done">Done</option>
        <option value="running">Running</option>
        <option value="queued">Queued</option>
        <option value="error">Error</option>
      </select>
      <select v-model="minSev" class="h-9 rounded-md border border-border bg-card px-2 text-sm" aria-label="Minimum severity">
        <option value="">Any severity</option>
        <option value="critical">Critical+</option>
        <option value="high">High+</option>
        <option value="medium">Medium+</option>
        <option value="low">Low+</option>
      </select>
      <select v-model="sortKey" class="h-9 rounded-md border border-border bg-card px-2 text-sm" aria-label="Sort">
        <option value="newest">Newest first</option>
        <option value="oldest">Oldest first</option>
        <option value="findings">Most findings</option>
      </select>
      <span class="ml-auto text-sm text-muted-foreground">
        {{ filtered.length }} of {{ scans.list.length }} scan{{ scans.list.length === 1 ? '' : 's' }}
      </span>
    </div>

    <div v-if="loading">
      <Skeleton class="h-64 rounded-xl" />
    </div>

    <Alert v-else-if="error" variant="destructive">
      <AlertTitle>Couldn't load your scans</AlertTitle>
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <EmptyState
      v-else-if="scans.list.length === 0"
      variant="panel"
      title="No scans yet"
      body="Run your first scan to build up a history. Point the engine at a git repo, a live URL, or a local path."
    />

    <EmptyState
      v-else-if="filtered.length === 0"
      variant="panel"
      title="No matching scans"
      body="No scans match your filters. Try widening the search or clearing a filter."
    />

    <section v-else class="space-y-6">
      <div v-for="g in groups" :key="g.label || 'all'" class="space-y-2">
        <h2 v-if="g.label" class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {{ g.label }}
        </h2>
        <Card class="p-0">
          <Table class="min-w-[640px]">
            <TableHeader>
              <TableRow>
                <TableHead>Target</TableHead>
                <TableHead>Mode</TableHead>
                <TableHead>Status</TableHead>
                <TableHead class="text-right">Findings</TableHead>
                <TableHead>Started</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow
                v-for="s in g.rows"
                :key="s.id"
                class="cursor-pointer"
                @click="router.push({ name: 'scan-detail', params: { id: s.id } })"
              >
                <TableCell class="font-medium">{{ s.target }}</TableCell>
                <TableCell class="text-muted-foreground">{{ s.mode }}</TableCell>
                <TableCell><StatusPill :status="s.status" /></TableCell>
                <TableCell class="text-right">
                  <span class="tabular-nums font-medium">{{ s.finding_count }}</span>
                  <span v-if="s.finding_count" class="ml-2 inline-flex gap-1 align-middle">
                    <template v-for="sev in SEVERITIES" :key="sev">
                      <span
                        v-if="(s.summary?.counts?.[sev] || 0) > 0"
                        class="size-2 rounded-full"
                        :style="{ background: `var(--severity-${sev})` }"
                        :title="`${s.summary.counts[sev]} ${sev}`"
                      />
                    </template>
                  </span>
                </TableCell>
                <TableCell class="text-muted-foreground">{{ fmt(s.created_at) }}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>
      </div>
    </section>
  </div>
</template>
