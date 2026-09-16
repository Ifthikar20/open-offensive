<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Radar } from '@lucide/vue'
import { useScansStore } from '@/stores/scans'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { cn } from '@/lib/utils'

const router = useRouter()
const scans = useScansStore()

const open = ref(false)
const target = ref('')
const mode = ref('auto')
const busy = ref(false)
const error = ref('')

const MODES = [
  { value: 'auto', label: 'Auto', hint: 'LLM agents when a key is set, else scripted' },
  { value: 'llm', label: 'LLM', hint: 'Full multi-agent run (needs an API key)' },
  { value: 'scripted', label: 'Scripted', hint: 'Deterministic checks, no LLM' },
]

async function submit() {
  error.value = ''
  busy.value = true
  try {
    const scan = await scans.create(target.value.trim(), mode.value)
    open.value = false
    target.value = ''
    mode.value = 'auto'
    router.push({ name: 'scan-detail', params: { id: scan.id } })
  } catch (e) {
    error.value = e?.displayMessage || 'Could not start the scan.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogTrigger as-child>
      <Button size="sm">
        <Radar class="size-4" />
        New scan
      </Button>
    </DialogTrigger>
    <DialogContent>
      <DialogHeader>
        <DialogTitle>New scan</DialogTitle>
        <DialogDescription>
          Point the engine at a repo, a live URL, or leave it blank to run the bundled demo.
        </DialogDescription>
      </DialogHeader>

      <form class="grid gap-4" @submit.prevent="submit">
        <div class="grid gap-1.5">
          <Label for="scan-target">Target</Label>
          <Input
            id="scan-target"
            v-model="target"
            placeholder="https://github.com/acme/app  ·  https://staging.acme.com"
          />
        </div>

        <div class="grid gap-1.5">
          <Label>Mode</Label>
          <div class="flex gap-0.5 rounded-[10px] bg-muted p-[3px]">
            <button
              v-for="m in MODES"
              :key="m.value"
              type="button"
              :title="m.hint"
              :class="
                cn(
                  'flex-1 rounded-lg px-3 py-1.5 text-[13px] font-semibold transition-colors',
                  mode === m.value
                    ? 'bg-card text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                )
              "
              @click="mode = m.value"
            >
              {{ m.label }}
            </button>
          </div>
          <p class="text-[11px] text-muted-foreground">
            {{ MODES.find((m) => m.value === mode)?.hint }}
          </p>
        </div>

        <Alert v-if="error" variant="destructive">
          <AlertDescription>{{ error }}</AlertDescription>
        </Alert>

        <DialogFooter>
          <Button type="submit" :disabled="busy">
            {{ busy ? 'Starting…' : 'Run scan' }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
