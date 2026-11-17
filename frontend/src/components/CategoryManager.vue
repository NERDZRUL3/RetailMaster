<script setup lang="ts">
// Manage product groups and their subgroups: add, rename, move, delete.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import { categoriesApi, type CategoryTree } from '@/categories'

const props = withDefaults(defineProps<{ tree: CategoryTree; closable?: boolean }>(), { closable: true })
const emit = defineEmits<{
  /** Something changed; renamed carries the old and new name of a renamed category. */
  changed: [renamed?: { from: string; to: string }]
  close: []
}>()
const { t } = useI18n()

const busy = ref(false)
const error = ref('')
const editing = ref('') // category being renamed
const editLabel = ref('')
const addingTo = ref<string | null>(null) // '' = new group, a name = new subgroup of it
const newLabel = ref('')

async function run(action: () => Promise<unknown>) {
  busy.value = true
  error.value = ''
  try {
    await action()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    busy.value = false
  }
}

function startRename(name: string) {
  editing.value = name
  editLabel.value = name
  addingTo.value = null
}
function rename(name: string, parent: string) {
  const label = editLabel.value.trim()
  if (!label || label === name) {
    editing.value = ''
    return
  }
  run(async () => {
    const saved = await categoriesApi.save(label, name, parent)
    editing.value = ''
    emit('changed', { from: name, to: saved.name })
  })
}

function startAdd(parent: string) {
  addingTo.value = parent
  newLabel.value = ''
  editing.value = ''
}
function add() {
  const label = newLabel.value.trim()
  if (!label || addingTo.value === null) return
  const parent = addingTo.value
  run(async () => {
    await categoriesApi.save(label, '', parent)
    addingTo.value = null
    emit('changed')
  })
}

function move(name: string, parent: string) {
  run(async () => {
    await categoriesApi.save(name, name, parent)
    emit('changed')
  })
}

function remove(name: string) {
  if (!window.confirm(t('categories.confirmDelete', { name }))) return
  run(async () => {
    await categoriesApi.remove(name)
    emit('changed')
  })
}

const canEdit = () => props.tree.can_write
</script>

<template>
  <section class="rounded-2xl bg-slate-50 p-4" :aria-busy="busy">
    <div class="flex items-center justify-between gap-3">
      <h3 class="text-[16px] font-semibold text-slate-900">{{ t('categories.title') }}</h3>
      <button v-if="closable" type="button" class="btn-quiet py-1.5 text-[14px]" @click="emit('close')">{{ t('categories.done') }}</button>
    </div>
    <p class="hint mt-1">{{ t('categories.hint') }}</p>
    <p v-if="error" class="notice-error mt-3" role="alert">{{ error }}</p>

    <ul class="mt-3 space-y-2">
      <li v-for="group in tree.groups" :key="group.name" class="rounded-xl bg-white p-3">
        <!-- Group row -->
        <div class="flex flex-wrap items-center gap-2">
          <template v-if="editing === group.name">
            <input
              v-model="editLabel"
              dir="auto"
              class="field min-w-0 flex-1 py-2 text-[15px]"
              :aria-label="t('categories.newName')"
              @keydown.enter.prevent="rename(group.name, '')"
              @keydown.esc="editing = ''"
            />
            <button type="button" class="btn-primary py-2" :disabled="busy" @click="rename(group.name, '')">{{ t('categories.save') }}</button>
            <button type="button" class="btn-secondary py-2" @click="editing = ''">{{ t('categories.cancel') }}</button>
          </template>
          <template v-else>
            <span class="min-w-0 flex-1 truncate font-medium text-slate-900" dir="auto">{{ group.name }}</span>
            <span class="badge-neutral">{{ t('categories.products', { count: group.items }, group.items) }}</span>
            <button v-if="tree.can_create" type="button" class="btn-quiet px-2.5 py-1 text-[13px]" @click="startAdd(group.name)">
              + {{ t('categories.addSubgroup') }}
            </button>
            <button v-if="canEdit()" type="button" class="btn-quiet px-2.5 py-1 text-[13px]" @click="startRename(group.name)">
              {{ t('categories.rename') }}
            </button>
            <button
              v-if="tree.can_delete && !group.items && !group.children.length"
              type="button"
              class="btn-danger px-2.5 py-1 text-[13px]"
              :disabled="busy"
              @click="remove(group.name)"
            >
              {{ t('categories.delete') }}
            </button>
          </template>
        </div>

        <!-- Subgroups -->
        <ul v-if="group.children.length || addingTo === group.name" class="mt-2 space-y-1.5 border-s-2 border-[var(--hairline)] ps-3">
          <li v-for="child in group.children" :key="child.name" class="flex flex-wrap items-center gap-2">
            <template v-if="editing === child.name">
              <input
                v-model="editLabel"
                dir="auto"
                class="field min-w-0 flex-1 py-1.5 text-[14px]"
                :aria-label="t('categories.newName')"
                @keydown.enter.prevent="rename(child.name, group.name)"
                @keydown.esc="editing = ''"
              />
              <button type="button" class="btn-primary py-1.5" :disabled="busy" @click="rename(child.name, group.name)">{{ t('categories.save') }}</button>
              <button type="button" class="btn-secondary py-1.5" @click="editing = ''">{{ t('categories.cancel') }}</button>
            </template>
            <template v-else>
              <span class="min-w-0 flex-1 truncate text-[14px] text-slate-700" dir="auto">{{ child.name }}</span>
              <span class="badge-neutral">{{ t('categories.products', { count: child.items }, child.items) }}</span>
              <select
                v-if="canEdit() && tree.groups.length > 1"
                class="field w-auto py-1 text-[13px]"
                :value="group.name"
                :aria-label="t('categories.moveTo', { name: child.name })"
                :disabled="busy"
                @change="move(child.name, ($event.target as HTMLSelectElement).value)"
              >
                <option v-for="g in tree.groups" :key="g.name" :value="g.name">{{ g.name }}</option>
              </select>
              <button v-if="canEdit()" type="button" class="btn-quiet px-2.5 py-1 text-[13px]" @click="startRename(child.name)">
                {{ t('categories.rename') }}
              </button>
              <button
                v-if="tree.can_delete && !child.items"
                type="button"
                class="btn-danger px-2.5 py-1 text-[13px]"
                :disabled="busy"
                @click="remove(child.name)"
              >
                {{ t('categories.delete') }}
              </button>
            </template>
          </li>
          <li v-if="addingTo === group.name" class="flex flex-wrap items-center gap-2">
            <input
              v-model="newLabel"
              dir="auto"
              class="field min-w-0 flex-1 py-1.5 text-[14px]"
              :placeholder="t('categories.subgroupName')"
              :aria-label="t('categories.subgroupName')"
              @keydown.enter.prevent="add"
              @keydown.esc="addingTo = null"
            />
            <button type="button" class="btn-primary py-1.5" :disabled="busy || !newLabel.trim()" @click="add">{{ t('categories.add') }}</button>
            <button type="button" class="btn-secondary py-1.5" @click="addingTo = null">{{ t('categories.cancel') }}</button>
          </li>
        </ul>
      </li>
    </ul>

    <!-- New group -->
    <div v-if="tree.can_create" class="mt-3">
      <div v-if="addingTo === ''" class="flex flex-wrap items-center gap-2">
        <input
          v-model="newLabel"
          dir="auto"
          class="field min-w-0 flex-1 bg-white py-2 text-[15px]"
          :placeholder="t('categories.groupName')"
          :aria-label="t('categories.groupName')"
          @keydown.enter.prevent="add"
          @keydown.esc="addingTo = null"
        />
        <button type="button" class="btn-primary py-2" :disabled="busy || !newLabel.trim()" @click="add">{{ t('categories.add') }}</button>
        <button type="button" class="btn-secondary py-2" @click="addingTo = null">{{ t('categories.cancel') }}</button>
      </div>
      <button v-else type="button" class="btn-secondary py-2" @click="startAdd('')">+ {{ t('categories.addGroup') }}</button>
    </div>
  </section>
</template>
