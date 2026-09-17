# OpenOffensive console (dashboard)

The invite-only web console for the OpenOffensive pentester — **Vue 3 + Vite +
Tailwind v4 + shadcn-vue** (reka-ui), built on a warm off-white / purple-accent
design system with a pure black-and-white dark mode. It talks to the
[Django backend](../../backend) over a session cookie: redeem an invite, run
scans, and watch findings land in real time.

## Develop

```bash
# 1) start the backend in another terminal (see ../../backend/README.md)
#    cd ../../backend && OPENOFFENSIVE_ENGINE_SANDBOX=local python manage.py runserver

# 2) start the dashboard
npm install
cp .env.example .env      # optional; defaults target the backend on :8000
npm run dev               # http://localhost:5173
```

The dev server proxies `/api` (and `/admin`, `/static`) to the backend so the
app is same-origin with Django — the session cookie + CSRF just work, and **no
secrets live in the frontend**.

## Build / lint

```bash
npm run build    # static bundle in dist/ (served by Django in production)
npm run lint     # ESLint (flat config) + Prettier
npm run format   # prettier --write src/
```

## Layout

```
src/
  assets/          tailwind.css (design tokens) + legacy css layer
  components/ui/   shadcn-vue primitives (button, card, sidebar, dialog, …)
  components/      Brand, StatusPill, NewScanDialog, SeverityBadge
  api/             session+CSRF axios client + auth/scans modules
  stores/          Pinia: auth, app (theme), scans
  router/          invite-first guard + protected app routes
  layouts/         AppLayout (sidebar shell), AuthLayout (forced-light)
  pages/           Dashboard, ScanDetail, Settings; auth/{InviteRedeem,SignIn}
```

Scans are followed by **polling** the detail endpoint (no websockets), matching
the backend's simple subprocess model. Dark mode is keyed on
`data-theme="dark"` (persisted in `localStorage['oo-theme']`).
