<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { LayoutGrid, Radar, History, User, Settings, LogOut, Sun, Moon, ChevronsUpDown } from '@lucide/vue'

import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import Brand from '@/components/Brand.vue'
import NewScanDialog from '@/components/NewScanDialog.vue'
import {
  SidebarProvider,
  Sidebar,
  SidebarInset,
  SidebarTrigger,
  SidebarRail,
  SidebarHeader,
  SidebarFooter,
  SidebarContent,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
} from '@/components/ui/sidebar'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
  Breadcrumb,
  BreadcrumbList,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const app = useAppStore()

const nav = [
  {
    label: 'Overview',
    items: [
      { title: 'Dashboard', icon: LayoutGrid, to: '/dashboard', match: '/dashboard' },
      { title: 'Scans', icon: Radar, to: '/dashboard', match: '/scans' },
      { title: 'History', icon: History, to: '/history', match: '/history' },
    ],
  },
  {
    label: 'Account',
    items: [
      { title: 'Profile', icon: User, to: '/profile', match: '/profile' },
      { title: 'Settings', icon: Settings, to: '/settings', match: '/settings' },
    ],
  },
]

function isActive(item) {
  return route.path === item.match || route.path.startsWith(item.match + '/')
}

const crumb = computed(() => {
  if (route.name === 'scan-detail') return 'Scan detail'
  if (route.name === 'scan-history') return 'Scan history'
  if (route.name === 'profile') return 'Profile'
  if (route.name === 'settings') return 'Settings'
  return 'Dashboard'
})

const initials = computed(() => (auth.user?.username || 'OO').slice(0, 2).toUpperCase())

async function signOut() {
  await auth.logout()
  router.push({ name: 'access' })
}
</script>

<template>
  <SidebarProvider>
    <Sidebar collapsible="icon" variant="inset">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton as-child size="lg" tooltip="OpenOffensive">
              <router-link to="/dashboard" class="flex items-center">
                <Brand class="group-data-[collapsible=icon]:hidden" />
                <Brand collapsed class="hidden group-data-[collapsible=icon]:flex" />
              </router-link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup v-for="group in nav" :key="group.label">
          <SidebarGroupLabel>{{ group.label }}</SidebarGroupLabel>
          <SidebarMenu>
            <SidebarMenuItem v-for="item in group.items" :key="item.title">
              <SidebarMenuButton as-child :is-active="isActive(item)" :tooltip="item.title">
                <router-link :to="item.to">
                  <component :is="item.icon" />
                  <span>{{ item.title }}</span>
                </router-link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <SidebarMenuButton
                  size="lg"
                  class="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                >
                  <Avatar class="size-8 rounded-lg">
                    <AvatarFallback class="rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                      {{ initials }}
                    </AvatarFallback>
                  </Avatar>
                  <div class="grid flex-1 text-left leading-tight">
                    <span class="truncate text-sm font-semibold">{{ auth.user?.username }}</span>
                    <span class="truncate text-xs text-muted-foreground">
                      {{ auth.user?.email || 'Signed in' }}
                    </span>
                  </div>
                  <ChevronsUpDown class="ml-auto size-4" />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" side="top" class="min-w-56 rounded-lg">
                <DropdownMenuLabel>{{ auth.user?.username }}</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem @click="router.push({ name: 'profile' })">
                  <User />
                  Profile
                </DropdownMenuItem>
                <DropdownMenuItem @click="router.push({ name: 'settings' })">
                  <Settings />
                  Settings
                </DropdownMenuItem>
                <DropdownMenuItem @click="app.toggleTheme()">
                  <component :is="app.isDark ? Sun : Moon" />
                  {{ app.isDark ? 'Light mode' : 'Dark mode' }}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem @click="signOut">
                  <LogOut />
                  Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>

    <SidebarInset
      class="md:m-2 md:min-h-[calc(100svh-1rem)] md:overflow-hidden md:rounded-xl md:border md:border-border md:shadow-sm"
    >
      <header
        class="flex h-16 shrink-0 items-center gap-2 border-b border-border bg-card transition-[width,height] ease-linear"
      >
        <div class="flex items-center gap-2 px-4 md:px-6">
          <SidebarTrigger
            class="-ml-1 size-9 border border-border bg-muted/60 shadow-sm hover:bg-muted"
          />
          <Separator orientation="vertical" class="mr-2 h-4" />
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem class="hidden md:block">
                <BreadcrumbLink as-child>
                  <router-link to="/dashboard">OpenOffensive</router-link>
                </BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator class="hidden md:block" />
              <BreadcrumbItem>
                <BreadcrumbPage>{{ crumb }}</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </div>

        <div class="ml-auto flex items-center gap-2 px-4 md:px-6">
          <Button
            variant="ghost"
            size="icon"
            class="size-9"
            :aria-label="app.isDark ? 'Switch to light mode' : 'Switch to dark mode'"
            @click="app.toggleTheme()"
          >
            <component :is="app.isDark ? Sun : Moon" class="size-4" />
          </Button>
          <NewScanDialog />
        </div>
      </header>

      <div class="flex w-full min-w-0 flex-1 flex-col gap-4 overflow-auto p-4 md:p-6">
        <router-view v-slot="{ Component }">
          <transition name="page-fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </div>
    </SidebarInset>
  </SidebarProvider>
</template>

<!-- Unscoped so the transition matches the routed page's root (see guide §9 #28). -->
<style>
.page-fade-leave-active {
  transition:
    opacity 120ms ease,
    transform 120ms ease;
}
.page-fade-enter-active {
  transition:
    opacity 280ms cubic-bezier(0.23, 1, 0.32, 1),
    transform 280ms cubic-bezier(0.23, 1, 0.32, 1);
}
.page-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
