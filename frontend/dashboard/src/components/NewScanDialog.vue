<script setup>
import { ref, computed } from 'vue'
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

const router = useRouter()
const scans = useScansStore()

const open = ref(false)
const target = ref('')
const busy = ref(false)
const error = ref('')

const canSubmit = computed(() => target.value.trim().length > 0)

async function submit() {
  if (!canSubmit.value) {
    error.value = 'Enter a target to scan.'
    return
  }
  error.value = ''
  busy.value = true
  try {
    const scan = await scans.create(target.value.trim())
    open.value = false
    target.value = ''
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
          Point the engine at a git repo, a live URL/host, or a local path. Scans need a
          configured model key and run only against targets you're authorized to test.
        </DialogDescription>
      </DialogHeader>

      <form class="grid gap-4" @submit.prevent="submit">
        <div class="grid gap-1.5">
          <Label for="scan-target">Target</Label>
          <Input
            id="scan-target"
            v-model="target"
            required
            placeholder="https://github.com/acme/app  ·  https://staging.acme.com"
          />
        </div>

        <Alert v-if="error" variant="destructive">
          <AlertDescription>{{ error }}</AlertDescription>
        </Alert>

        <DialogFooter>
          <Button type="submit" :disabled="busy || !canSubmit">
            {{ busy ? 'Starting…' : 'Run scan' }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
