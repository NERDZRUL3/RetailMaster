import './styles.css'

import { createApp } from 'vue'

import App from './App.vue'
import { applyLocale, i18n, initialLocale } from './i18n'
import { router } from './router'
import { initTheme } from './theme'

initTheme()
applyLocale(initialLocale())

createApp(App).use(i18n).use(router).mount('#app')
