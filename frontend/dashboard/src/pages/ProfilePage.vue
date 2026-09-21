<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useScansStore } from '@/stores/scans'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'

const auth = useAuthStore()
const scans = useScansStore()

const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info']

const form = reactive({ first_name: '', last_name: '', email: '' })
const saving = ref(false)
const saved = ref(false)
const error = ref('')

function loadForm() {
  form.first_name = auth.user?.first_name || ''
  form.last_name = auth.user?.last_name || ''
  form.email = auth.user?.email || ''
}

const initials = computed(() => (auth.user?.username || 'OO').slice(0, 2).toUpperCase())
const joined = computed(() =>
  auth.user?.date_joined
    ? new Date(auth.user.date_joined).toLocaleDateString(undefined, {
        year: 'numeric', month: 'long', day: 'numeric',
      })
    : '—'
)

const totals = computed(() => {
  const acc = { critical: 0, high: 0, medium: 0, low: 0, info: 0 }
  for (const s of scans.list) {
    const c = s.summary?.counts || {}
    for (const k of SEVERITIES) acc[k] += c[k] || 0
  }
  return acc
})
const totalFindings = computed(() => SEVERITIES.reduce((n, k) => n + totals.value[k], 0))

async function save() {
  error.value = ''
  saved.value = false
  saving.value = true
  try {
    await auth.updateProfile({
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      email: form.email.trim(),
    })
    saved.value = true
  } catch (e) {
    error.value = e?.displayMessage || 'Could not save your profile.'
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadForm()
  if (!scans.list.length) scans.fetchList().catch(() => {})
})
</script>

<template>
  <div class="fade-in mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6">
    <div>
      <h1 class="text-2xl font-semibold tracking-tight">Profile</h1>
      <p class="mt-1 text-sm text-muted-foreground">Your account and activity.</p>
    </div>

    <!-- identity -->
    <Card>
      <CardContent class="flex items-center gap-4 pt-6">
        <Avatar class="size-14 rounded-xl">
          <AvatarFallback class="rounded-xl bg-sidebar-primary text-lg text-sidebar-primary-foreground">
            {{ initials }}
          </AvatarFallback>
        </Avatar>
        <div class="grid gap-0.5">
          <div class="flex items-center gap-2">
            <span class="text-lg font-semibold">{{ auth.user?.username }}</span>
            <span
              v-if="auth.user?.is_staff"
              class="rounded-full bg-accent px-2 py-0.5 text-[11px] font-semibold text-accent-foreground"
            >staff</span>
          </div>
          <span class="text-sm text-muted-foreground">{{ auth.user?.email || 'No email set' }}</span>
          <span class="text-xs text-muted-foreground">Joined {{ joined }}</span>
        </div>
      </CardContent>
    </Card>

    <!-- edit -->
    <Card>
      <CardHeader>
        <CardTitle>Edit profile</CardTitle>
        <CardDescription>Your username can't be changed. Update your name and email here.</CardDescription>
      </CardHeader>
      <form @submit.prevent="save">
        <CardContent class="grid gap-4">
          <div class="grid gap-1.5 sm:grid-cols-2 sm:gap-4">
            <div class="grid gap-1.5">
              <Label for="fn">First name</Label>
              <Input id="fn" v-model="form.first_name" autocomplete="given-name" />
            </div>
            <div class="grid gap-1.5">
              <Label for="ln">Last name</Label>
              <Input id="ln" v-model="form.last_name" autocomplete="family-name" />
            </div>
          </div>
          <div class="grid gap-1.5">
            <Label for="email">Email</Label>
            <Input id="email" v-model="form.email" type="email" autocomplete="email" />
          </div>
          <Alert v-if="error" variant="destructive">
            <AlertDescription>{{ error }}</AlertDescription>
          </Alert>
          <p v-else-if="saved" class="text-sm text-[color:var(--color-success)]">Profile saved.</p>
        </CardContent>
        <CardFooter>
          <Button type="submit" :disabled="saving">{{ saving ? 'Saving…' : 'Save changes' }}</Button>
        </CardFooter>
      </form>
    </Card>

    <!-- activity -->
    <Card>
      <CardHeader>
        <CardTitle>Your activity</CardTitle>
        <CardDescription>Across all of your scans.</CardDescription>
      </CardHeader>
      <CardContent class="grid gap-4">
        <div class="flex items-baseline gap-6">
          <div>
            <div class="text-2xl font-bold tabular-nums">{{ scans.list.length }}</div>
            <div class="text-[11px] uppercase tracking-wide text-muted-foreground">scans</div>
          </div>
          <div>
            <div class="text-2xl font-bold tabular-nums">{{ totalFindings }}</div>
            <div class="text-[11px] uppercase tracking-wide text-muted-foreground">findings</div>
          </div>
        </div>
        <div class="flex flex-wrap gap-x-5 gap-y-2 text-[13px]">
          <span
            v-for="sev in SEVERITIES"
            :key="sev"
            class="inline-flex items-center gap-1.5"
            :class="totals[sev] ? '' : 'opacity-40'"
          >
            <span class="size-2 rounded-full" :style="{ background: `var(--severity-${sev})` }" />
            <span class="font-semibold tabular-nums">{{ totals[sev] }}</span>
            <span class="text-muted-foreground">{{ sev }}</span>
          </span>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
