<script setup>
import { Sun, Moon, Monitor, Check } from '@lucide/vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

const app = useAppStore()
const auth = useAuthStore()

const THEMES = [
  { value: 'system', label: 'System', icon: Monitor },
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
]
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
    </Card>
  </div>
</template>
