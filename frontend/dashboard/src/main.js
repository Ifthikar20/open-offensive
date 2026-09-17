import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import './assets/tailwind.css' // Tailwind v4 + shadcn tokens first
import './assets/main.css' // legacy design-system layer second (wins ties)

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
