import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

// The app is served same-origin with Django in production; in dev we proxy /api
// so the session cookie + CSRF work without cross-site cookie juggling.
const API_TARGET = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true, secure: false },
      '/admin': { target: API_TARGET, changeOrigin: true, secure: false },
      '/static': { target: API_TARGET, changeOrigin: true, secure: false },
    },
  },
})
