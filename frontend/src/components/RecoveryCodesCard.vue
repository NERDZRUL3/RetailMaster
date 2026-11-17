<script setup lang="ts">
// The signed-in owner's recovery codes: how many are left, and making a new
// set. A new set is shown once, to print, download or copy; the old set
// stops working. Hidden for accounts that cannot hold codes.
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import { branding } from '@/branding'
import { recoveryApi, type RecoveryStatus } from '@/recovery'
import { session } from '@/session'

const { t, locale } = useI18n()

const status = ref<RecoveryStatus | null>(null)
const codes = ref<string[]>([])
const confirming = ref(false)
const busy = ref(false)
const error = ref('')
const copied = ref(false)

onMounted(async () => {
  try {
    status.value = await recoveryApi.status()
  } catch {
    status.value = null // not an owner: nothing to show
  }
})

const created = computed(() =>
  status.value?.created
    ? new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium' }).format(new Date(status.value.created.replace(' ', 'T')))
    : '',
)
const account = computed(() => session.context?.user ?? '')

async function generate() {
  if (status.value?.total && !confirming.value) {
    confirming.value = true
    return
  }
  confirming.value = false
  busy.value = true
  error.value = ''
  try {
    const result = await recoveryApi.generate()
    codes.value = result.codes
    status.value = { remaining: result.remaining, total: result.remaining, created: new Date().toISOString() }
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    busy.value = false
  }
}

function asText() {
  return [`${branding.app_name} - ${t('recovery.title')}`, account.value, '', ...codes.value].join('\n')
}

async function copy() {
  try {
    await navigator.clipboard.writeText(asText())
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    // Clipboard blocked: download or print still work.
  }
}

function download() {
  const url = URL.createObjectURL(new Blob([asText() + '\n'], { type: 'text/plain' }))
  const link = Object.assign(document.createElement('a'), { href: url, download: 'recovery-codes.txt' })
  link.click()
  URL.revokeObjectURL(url)
}

function print() {
  window.print()
}
</script>

<template>
  <section v-if="status" class="card-pad">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 class="section-title">{{ t('recovery.title') }}</h2>
        <p class="hint mt-1 max-w-xl">{{ t('recovery.hint') }}</p>
      </div>
      <span v-if="status.total" :class="status.remaining > 2 ? 'badge-ok' : 'badge-warn'">
        {{ t('recovery.left', { count: status.remaining, total: status.total }) }}
      </span>
      <span v-else class="badge-warn">{{ t('recovery.none') }}</span>
    </div>
    <p v-if="created" class="hint mt-2">{{ t('recovery.created', { date: created }) }}</p>

    <!-- A new set, shown once -->
    <div v-if="codes.length" class="mt-5 rounded-2xl bg-slate-50 p-4 ring-1 ring-[var(--hairline)]">
      <p class="notice-warn mb-4">{{ t('recovery.showOnce') }}</p>
      <ol class="stagger grid grid-cols-2 gap-2 sm:grid-cols-5" dir="ltr">
        <li
          v-for="code in codes"
          :key="code"
          class="rounded-lg bg-white px-2 py-2 text-center font-mono text-[14px] tracking-wide text-slate-900 ring-1 ring-[var(--hairline)]"
        >
          {{ code }}
        </li>
      </ol>
      <div class="mt-4 flex flex-wrap gap-2">
        <button type="button" class="btn-secondary" @click="copy">{{ copied ? t('recovery.copied') : t('recovery.copy') }}</button>
        <button type="button" class="btn-secondary" @click="download">{{ t('recovery.download') }}</button>
        <button type="button" class="btn-secondary" @click="print">{{ t('recovery.print') }}</button>
      </div>
    </div>

    <p v-if="confirming" class="notice-warn mt-5" role="alert">{{ t('recovery.replaceWarning') }}</p>
    <p v-if="error" class="notice-error mt-5" role="alert">{{ error }}</p>
    <div class="mt-5 flex flex-wrap gap-2">
      <button type="button" class="btn-primary" :disabled="busy" @click="generate">
        {{ confirming ? t('recovery.replaceConfirm') : status.total ? t('recovery.regenerate') : t('recovery.generate') }}
      </button>
      <button v-if="confirming" type="button" class="btn-secondary" @click="confirming = false">{{ t('recovery.cancel') }}</button>
    </div>

    <!-- Printout: only the codes -->
    <Teleport v-if="codes.length" to="body">
      <div class="print-area">
        <div class="print-a4">
          <div class="a4-brand">{{ branding.app_name }}</div>
          <div class="a4-title" style="margin-top: 8px">{{ t('recovery.title') }}</div>
          <p>{{ account }}</p>
          <p>{{ t('recovery.printHint') }}</p>
          <ol style="font: 16px/2 ui-monospace, monospace">
            <li v-for="code in codes" :key="code">{{ code }}</li>
          </ol>
        </div>
      </div>
    </Teleport>
  </section>
</template>
