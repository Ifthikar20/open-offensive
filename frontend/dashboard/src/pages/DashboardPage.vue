<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { useScansStore } from '@/stores/scans'
import StatusPill from '@/components/StatusPill.vue'
import NewScanDialog from '@/components/NewScanDialog.vue'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import EmptyState from '@/components/ui/EmptyState.vue'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'

const router = useRouter()
const auth = useAuthStore()
const scans = useScansStore()

const loading = ref(true)
const error = ref('')
let timer = null
const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info']
const TERMINAL = new Set(['done', 'error'])

const greeting = computed(() => {
  const h = new Date().getHours()
  const t = h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening'
  return `Good ${t}, ${auth.user?.username || 'there'}`
})

// Aggregate finding counts across all scans (data-honesty: real numbers only).
const totals = computed(() => {
  const acc = { critical: 0, high: 0, medium: 0, low: 0, info: 0 }
  for (const s of scans.list) {
    const c = s.summary?.counts || {}
    for (const k of SEVERITIES) acc[k] += c[k] || 0
  }
  return acc
})

const anyRunning = computed(() => scans.list.some((s) => !TERMINAL.has(s.status)))

function fmt(iso) {
  return iso
    ? new Date(iso).toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—'
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
  <div class="fade-in flex flex-1 flex-col gap-6">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">{{ greeting }}</h1>
        <p class="mt-1 text-sm text-muted-foreground">
          Your scans and findings, in one place.
        </p>
      </div>
      <NewScanDialog />
    </div>

    <!-- KPI tiles -->
    <div v-if="loading" class="grid grid-cols-2 gap-4 sm:grid-cols-5">
      <Skeleton v-for="n in 5" :key="n" class="h-24 rounded-xl" />
    </div>
    <div v-else-if="!error" class="grid grid-cols-2 gap-4 sm:grid-cols-5">
      <Card v-for="sev in SEVERITIES" :key="sev" class="flex flex-col items-center gap-1 p-4">
        <span
          class="text-2xl font-bold tabular-nums"
          :class="`text-severity-${sev}`"
        >
          {{ totals[sev] }}
        </span>
        <span class="text-[11px] uppercase tracking-wide text-muted-foreground">{{ sev }}</span>
      </Card>
    </div>

    <!-- Scans -->
    <section class="space-y-3">
      <h2 class="text-lg font-semibold tracking-tight">Scans</h2>

      <div v-if="loading">
        <Skeleton class="h-40 rounded-xl" />
      </div>

      <Alert v-else-if="error" variant="destructive">
        <AlertTitle>Couldn't load your scans</AlertTitle>
        <AlertDescription>{{ error }}</AlertDescription>
      </Alert>

      <EmptyState
        v-else-if="scans.list.length === 0"
        variant="panel"
        title="No scans yet"
        body="Run your first scan to see findings here. Point the engine at a git repo, a live URL, or a local path."
      >
        <NewScanDialog />
      </EmptyState>

      <Card v-else class="p-0">
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
              v-for="s in scans.list"
              :key="s.id"
              class="cursor-pointer"
              @click="router.push({ name: 'scan-detail', params: { id: s.id } })"
            >
              <TableCell class="font-medium">{{ s.target }}</TableCell>
              <TableCell class="text-muted-foreground">{{ s.mode }}</TableCell>
              <TableCell><StatusPill :status="s.status" /></TableCell>
              <TableCell class="text-right tabular-nums">{{ s.finding_count }}</TableCell>
              <TableCell class="text-muted-foreground">{{ fmt(s.created_at) }}</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </Card>
    </section>
  </div>
</template>
