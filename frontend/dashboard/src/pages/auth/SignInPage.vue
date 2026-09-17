<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import AuthLayout from '@/layouts/AuthLayout.vue'
import Brand from '@/components/Brand.vue'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  error.value = ''
  busy.value = true
  try {
    await auth.login(username.value.trim(), password.value)
    router.push(route.query.redirect || { name: 'dashboard' })
  } catch (e) {
    error.value = e?.displayMessage || 'Invalid username or password.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthLayout>
    <Card class="p-8">
      <Brand class="text-foreground" />
      <h1 class="mt-5 text-2xl font-semibold tracking-tight">Sign in</h1>
      <p class="mt-1 text-sm text-muted-foreground">Welcome back. Sign in to run and review scans.</p>

      <form class="mt-6 grid gap-4" @submit.prevent="submit">
        <div class="grid gap-1.5">
          <Label for="username">Username</Label>
          <Input id="username" v-model="username" autocomplete="username" autofocus />
        </div>
        <div class="grid gap-1.5">
          <Label for="password">Password</Label>
          <Input id="password" v-model="password" type="password" autocomplete="current-password" />
        </div>

        <Alert v-if="error" variant="destructive">
          <AlertDescription>{{ error }}</AlertDescription>
        </Alert>

        <Button type="submit" :disabled="busy" class="mt-1">
          {{ busy ? 'Signing in…' : 'Sign in' }}
        </Button>
      </form>

      <p class="mt-6 text-center text-sm text-muted-foreground">
        Have an invite code?
        <router-link to="/access" class="font-medium text-foreground hover:underline">
          Redeem it
        </router-link>
      </p>
    </Card>
  </AuthLayout>
</template>
