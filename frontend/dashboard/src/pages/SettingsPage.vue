<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { Sun, Moon, Monitor, Check } from '@lucide/vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { cn } from '@/lib/utils'

const app = useAppStore()
const auth = useAuthStore()
const router = useRouter()

const THEMES = [
  { value: 'system', label: 'System', icon: Monitor },
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
]

const pw = reactive({ current_password: '', new_password: '', confirm: '' })
const changing = ref(false)
const changed = ref(false)
const pwError = ref('')

async function changePassword() {
  pwError.value = ''
  changed.value = false
  if (pw.new_password !== pw.confirm) {
    pwError.value = "New password and confirmation don't match."
    return
  }
  changing.value = true
  try {
    await auth.changePassword({
      current_password: pw.current_password,
      new_password: pw.new_password,
    })
    changed.value = true
    pw.current_password = pw.new_password = pw.confirm = ''
  } catch (e) {
    pwError.value = e?.displayMessage || 'Could not change your password.'
  } finally {
    changing.value = false
  }
}
</script>

<template>
  <div class="fade-in mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6">
    <div>
      <h1 class="text-2xl font-semibold tracking-tight">Settings</h1>
      <p class="mt-1 text-sm text-muted-foreground">Your account and appearance.</p>
    </div>

    <Card>
      <CardHeader>
        <CardTitle>Appearance</CardTitle>
        <CardDescription>Choose how OpenOffensive looks on this device.</CardDescription>
      </CardHeader>
      <CardContent>
        <div class="grid grid-cols-3 gap-3">
          <button
            v-for="t in THEMES"
            :key="t.value"
            type="button"
            :class="
              cn(
                'flex flex-col items-center gap-2 rounded-xl border border-border bg-card p-4 text-sm transition-colors hover:border-ring',
                app.theme === t.value && 'ring-2 ring-ring'
              )
            "
            @click="app.setTheme(t.value)"
          >
            <component :is="t.icon" class="size-5" />
            <span class="flex items-center gap-1 font-medium">
              {{ t.label }}
              <Check v-if="app.theme === t.value" class="size-3.5 text-[color:var(--brand-accent)]" />
            </span>
          </button>
        </div>
      </CardContent>
    </Card>

    <Card>
      <CardHeader>
        <CardTitle>Account</CardTitle>
        <CardDescription>Signed in to the OpenOffensive console.</CardDescription>
      </CardHeader>
      <CardContent class="grid gap-3 text-sm">
        <div class="flex justify-between border-b border-border pb-3">
          <span class="text-muted-foreground">Username</span>
          <span class="font-medium">{{ auth.user?.username }}</span>
        </div>
        <div class="flex justify-between">
          <span class="text-muted-foreground">Email</span>
          <span class="font-medium">{{ auth.user?.email || '—' }}</span>
        </div>
      </CardContent>
      <CardFooter>
        <Button variant="outline" size="sm" @click="router.push({ name: 'profile' })">
          Edit profile
        </Button>
      </CardFooter>
    </Card>

    <Card>
      <CardHeader>
        <CardTitle>Change password</CardTitle>
        <CardDescription>Use at least 8 characters. You'll stay signed in on this device.</CardDescription>
      </CardHeader>
      <form @submit.prevent="changePassword">
        <CardContent class="grid gap-4">
          <div class="grid gap-1.5">
            <Label for="cur">Current password</Label>
            <Input id="cur" v-model="pw.current_password" type="password" autocomplete="current-password" required />
          </div>
          <div class="grid gap-1.5">
            <Label for="new">New password</Label>
            <Input id="new" v-model="pw.new_password" type="password" autocomplete="new-password" required />
          </div>
          <div class="grid gap-1.5">
            <Label for="cfm">Confirm new password</Label>
            <Input id="cfm" v-model="pw.confirm" type="password" autocomplete="new-password" required />
          </div>
          <Alert v-if="pwError" variant="destructive">
            <AlertDescription>{{ pwError }}</AlertDescription>
          </Alert>
          <p v-else-if="changed" class="text-sm text-[color:var(--color-success)]">Password updated.</p>
        </CardContent>
        <CardFooter>
          <Button type="submit" :disabled="changing">{{ changing ? 'Updating…' : 'Update password' }}</Button>
        </CardFooter>
      </form>
    </Card>
  </div>
</template>
