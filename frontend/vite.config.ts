import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// The Frappe dev stack (infrastructure/docker). Only used by the dev server.
const backend = process.env.RETAIL_BACKEND_URL ?? 'http://127.0.0.1:8080'

export default defineConfig(({ command }) => ({
  // In production Frappe serves the built files from the app's public folder.
  base: command === 'build' ? '/assets/retail_management/frontend/' : '/',
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5183,
    strictPort: true,
    proxy: {
      '/api': backend,
      '/assets': backend,
      '/files': backend,
    },
  },
  build: {
    outDir: '../apps/retail_management/retail_management/public/frontend',
    emptyOutDir: true,
  },
}))
