import './styles.css'

import { createApp } from 'vue'

import App from './App.vue'
import { applyLocale, i18n, initialLocale } from './i18n'
import { router } from './router'

applyLocale(initialLocale())

createApp(App).use(i18n).use(router).mount('#app')
