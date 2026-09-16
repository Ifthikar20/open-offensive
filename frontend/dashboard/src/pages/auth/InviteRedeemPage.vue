<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight } from '@lucide/vue'

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

const step = ref(1)
const invite = ref('')
const username = ref('')
const email = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

function toStep2() {
  error.value = ''
  if (!invite.value.trim()) {
    error.value = 'Enter the invite code you were given.'
    return
  }
  step.value = 2
}

async function submit() {
  error.value = ''
  busy.value = true
  try {
    await auth.register({
      username: username.value.trim(),
      email: email.value.trim() || undefined,
      password: password.value,
      invite_code: invite.value.trim(),
    })
    router.push(route.query.redirect || { name: 'dashboard' })
  } catch (e) {
    error.value = e?.displayMessage || 'Could not create your account.'
    // A bad/used code comes back on this call — send the user back to fix it.
    if (/invite/i.test(error.value)) step.value = 1
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthLayout>
    <Card class="p-8">
      <Brand class="text-foreground" />
      <h1 class="mt-5 text-2xl font-semibold tracking-tight">
        {{ step === 1 ? 'Enter your invite' : 'Create your account' }}
      </h1>
      <p class="mt-1 text-sm text-muted-foreground">
        {{
          step === 1
            ? 'OpenOffensive is invite-only. Enter the code you were given to get started.'
            : 'Pick a username and password — you’ll use these to sign back in.'
        }}
      </p>

      <form class="mt-6 grid gap-4" @submit.prevent="step === 1 ? toStep2() : submit()">
        <div v-if="step === 1" class="grid gap-1.5">
          <Label for="invite">Invite code</Label>
          <Input id="invite" v-model="invite" placeholder="e.g. lo5TXZg2T1GV" autofocus />
        </div>

        <template v-else>
          <div class="grid gap-1.5">
            <Label for="username">Username</Label>
            <Input id="username" v-model="username" autocomplete="username" autofocus />
          </div>
          <div class="grid gap-1.5">
            <Label for="email">Email <span class="text-muted-foreground">(optional)</span></Label>
            <Input id="email" v-model="email" type="email" autocomplete="email" />
          </div>
          <div class="grid gap-1.5">
            <Label for="password">Password</Label>
            <Input
              id="password"
              v-model="password"
              type="password"
              autocomplete="new-password"
              minlength="8"
            />
          </div>
        </template>

        <Alert v-if="error" variant="destructive">
          <AlertDescription>{{ error }}</AlertDescription>
        </Alert>

        <Button type="submit" :disabled="busy" class="mt-1">
          <template v-if="step === 1">
            Continue
            <ArrowRight class="size-4" />
          </template>
          <template v-else>
            {{ busy ? 'Creating…' : 'Create account' }}
          </template>
        </Button>

        <button
          v-if="step === 2"
          type="button"
          class="text-xs text-muted-foreground hover:text-foreground"
          @click="step = 1"
        >
          ← Back to invite code
        </button>
      </form>

      <p class="mt-6 text-center text-sm text-muted-foreground">
        Already have an account?
        <router-link to="/signin" class="font-medium text-foreground hover:underline">
          Sign in
        </router-link>
      </p>
    </Card>
  </AuthLayout>
</template>
