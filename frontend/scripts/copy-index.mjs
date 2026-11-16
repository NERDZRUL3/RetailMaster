// After `vite build`: copy the built index.html to the Frappe www folder so
// Frappe serves it at /retail. The JS/CSS stay in public/frontend.
import { copyFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const app = resolve(dirname(fileURLToPath(import.meta.url)), '../../apps/retail_management/retail_management')
const source = resolve(app, 'public/frontend/index.html')
const target = resolve(app, 'www/retail.html')

mkdirSync(dirname(target), { recursive: true })
copyFileSync(source, target)
console.log(`Copied ${source} -> ${target}`)
