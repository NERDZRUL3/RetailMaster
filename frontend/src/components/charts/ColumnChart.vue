<script setup lang="ts">
// Stacked columns: a soft body (first series) under a striped brand top
// (second series). Hovering a column shows a box with each value and the total.
import { computed, onBeforeUnmount, onMounted, ref, useId } from 'vue'

const props = withDefaults(
  defineProps<{
    columns: { label: string; title?: string; values: [number, number] }[]
    series: [string, string]
    format: (value: number) => string
    formatAxis?: (value: number) => string
    label: string
    totalLabel?: string
    height?: number
    axis?: boolean
    /** Fraction of each slot used by the column. */
    thickness?: number
    initial?: number
  }>(),
  { height: 240, axis: true, thickness: 0.42, initial: -1 },
)

const box = ref<HTMLDivElement | null>(null)
const width = ref(320)
let observer: ResizeObserver | undefined
onMounted(() => {
  if (box.value?.clientWidth) width.value = box.value.clientWidth
  observer = new ResizeObserver(([entry]) => (width.value = Math.max(160, entry.contentRect.width)))
  if (box.value) observer.observe(box.value)
})
onBeforeUnmount(() => observer?.disconnect())

const id = useId()
const hovered = ref<number | null>(null)
const active = computed(() => hovered.value ?? props.initial)

const pad = computed(() => ({ top: 10, bottom: 24, left: props.axis ? 40 : 2, right: 2 }))

const axisMax = computed(() => {
  const max = Math.max(...props.columns.map((c) => c.values[0] + c.values[1]), 1)
  const step = max / 5
  const power = 10 ** Math.floor(Math.log10(step))
  const nice = [1, 2, 2.5, 5, 10].find((n) => n * power >= step) ?? 10
  return nice * power * 5
})
const ticks = computed(() => Array.from({ length: 6 }, (_, i) => (axisMax.value / 5) * i))

const plotH = computed(() => props.height - pad.value.top - pad.value.bottom)
const slot = computed(() => (width.value - pad.value.left - pad.value.right) / Math.max(1, props.columns.length))
const colW = computed(() => Math.max(4, Math.min(slot.value * props.thickness, 30)))
const y = (value: number) => pad.value.top + plotH.value - (value / axisMax.value) * plotH.value

const bars = computed(() =>
  props.columns.map((column, i) => {
    const x = pad.value.left + i * slot.value + (slot.value - colW.value) / 2
    const [base, top] = column.values
    return {
      x,
      center: x + colW.value / 2,
      baseY: y(base),
      baseH: Math.max(0, y(0) - y(base)),
      topY: y(base + top),
      topH: Math.max(0, y(base) - y(base + top) - 2),
    }
  }),
)

// Show every n-th label when they would not fit.
const every = computed(() => {
  const longest = Math.max(1, ...props.columns.map((c) => c.label.length))
  return Math.max(1, Math.ceil((longest * 6.2 + 8) / slot.value))
})

const tip = computed(() => {
  const i = active.value
  if (i < 0 || !bars.value[i]) return null
  const leftPct = (bars.value[i].center / width.value) * 100
  return { i, leftPct, column: props.columns[i] }
})
</script>

<template>
  <div ref="box" class="relative w-full min-w-0" dir="ltr" @mouseleave="hovered = null">
    <svg :width="width" :height="height" role="img" :aria-label="label" class="block">
      <defs>
        <pattern :id="`${id}-lines`" width="6" height="5" patternUnits="userSpaceOnUse">
          <rect width="6" height="3" fill="var(--color-brand-600)" />
        </pattern>
      </defs>
      <template v-if="axis">
        <template v-for="tick in ticks" :key="tick">
          <text :x="pad.left - 10" :y="y(tick) + 4" text-anchor="end" class="fill-slate-500 text-[11px] tabular-nums">
            {{ formatAxis ? formatAxis(tick) : tick }}
          </text>
        </template>
      </template>
      <g v-for="(bar, i) in bars" :key="i" :opacity="active < 0 || active === i ? 1 : 0.85">
        <rect :x="bar.x" :y="bar.baseY" :width="colW" :height="bar.baseH" rx="2" fill="var(--color-brand-200)" />
        <rect :x="bar.x" :y="bar.topY" :width="colW" :height="bar.topH" :fill="`url(#${id}-lines)`" />
        <text
          v-if="(columns.length - 1 - i) % every === 0"
          :x="bar.center"
          :y="height - 6"
          text-anchor="middle"
          class="text-[11px]"
          :class="active === i ? 'fill-slate-900' : 'fill-slate-500'"
        >
          {{ columns[i].label }}
        </text>
        <rect
          :x="pad.left + i * slot"
          :y="pad.top"
          :width="slot"
          :height="plotH"
          fill="transparent"
          class="cursor-pointer"
          @mouseenter="hovered = i"
          @click="hovered = i"
        />
      </g>
    </svg>

    <!-- Value box -->
    <div
      v-if="tip"
      class="pointer-events-none absolute top-0 z-10 w-44 -translate-x-1/2 rounded-xl bg-white p-3 text-[13px] shadow-lg ring-1 ring-[var(--hairline)]"
      :style="{ left: `clamp(5.5rem, ${tip.leftPct}%, calc(100% - 5.5rem))` }"
    >
      <div class="mb-1.5 font-medium text-slate-900">{{ tip.column.title ?? tip.column.label }}</div>
      <div v-for="(name, s) in series" :key="name" class="flex items-center justify-between gap-3 py-0.5">
        <span class="inline-flex items-center gap-2" :class="s === 1 ? 'text-brand-ink' : 'text-slate-600'">
          <span class="h-2 w-2 rounded-full" :class="s === 1 ? 'bg-brand-600' : 'bg-brand-200'" />{{ name }}
        </span>
        <span class="font-medium text-slate-900 tabular-nums">{{ format(tip.column.values[s]) }}</span>
      </div>
      <div v-if="totalLabel" class="mt-1 flex items-center justify-between gap-3 border-t border-[var(--hairline)] pt-1.5">
        <span class="text-slate-600">{{ totalLabel }}</span>
        <span class="font-semibold text-slate-900 tabular-nums">{{ format(tip.column.values[0] + tip.column.values[1]) }}</span>
      </div>
    </div>

    <div class="sr-only">
    <table>
      <caption>{{ label }}</caption>
      <tbody>
        <tr v-for="column in columns" :key="column.label">
          <th scope="row">{{ column.title ?? column.label }}</th>
          <td>{{ series[0] }} {{ format(column.values[0]) }}, {{ series[1] }} {{ format(column.values[1]) }}</td>
        </tr>
      </tbody>
    </table>
    </div>
  </div>
</template>
