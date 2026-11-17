<script setup lang="ts">
// Two series per column: stacked (a soft body under a striped brand top) or,
// in "pair" mode, side by side (soft first series, solid brand second).
// Columns grow in from the axis. Hovering (or tapping) a column lights up its
// slot, dims the others and shows a box with each value and, if given, the total.
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
    mode?: 'stack' | 'pair'
  }>(),
  { height: 240, axis: true, thickness: 0.42, initial: -1, mode: 'stack' },
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
  const max = Math.max(
    ...props.columns.map((c) => (props.mode === 'pair' ? Math.max(c.values[0], c.values[1]) : c.values[0] + c.values[1])),
    1,
  )
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
    if (props.mode === 'pair') {
      const half = colW.value / 2 - 1
      return {
        x,
        center: x + colW.value / 2,
        rects: [
          { x, y: y(base), w: half, h: Math.max(0, y(0) - y(base)), kind: 'soft' },
          { x: x + half + 2, y: y(top), w: half, h: Math.max(0, y(0) - y(top)), kind: 'solid' },
        ],
      }
    }
    return {
      x,
      center: x + colW.value / 2,
      rects: [
        { x, y: y(base), w: colW.value, h: Math.max(0, y(0) - y(base)), kind: 'soft' },
        { x, y: y(base + top), w: colW.value, h: Math.max(0, y(base) - y(base + top) - 2), kind: 'striped' },
      ],
    }
  }),
)

// Show every n-th label when they would not fit.
const every = computed(() => {
  const longest = Math.max(1, ...props.columns.map((c) => c.label.length))
  return Math.max(1, Math.ceil((longest * 6.2 + 8) / slot.value))
})

// Replays the grow-in when the data itself changes (another shop chosen).
const drawKey = computed(() => props.columns.map((c) => c.values.join(':')).join(','))

const tip = computed(() => {
  const i = active.value
  if (i < 0 || !bars.value[i]) return null
  const leftPct = (bars.value[i].center / width.value) * 100
  return { i, leftPct, column: props.columns[i] }
})
</script>

<template>
  <div ref="box" class="relative w-full min-w-0" dir="ltr" @pointerleave="hovered = null">
    <svg :width="width" :height="height" role="img" :aria-label="label" class="block touch-pan-y">
      <defs>
        <pattern :id="`${id}-lines`" width="6" height="5" patternUnits="userSpaceOnUse">
          <rect width="6" height="3" fill="var(--color-brand-600)" />
        </pattern>
      </defs>
      <template v-if="axis">
        <line
          v-for="tick in ticks"
          :key="`grid-${tick}`"
          :x1="pad.left"
          :x2="width - pad.right"
          :y1="y(tick)"
          :y2="y(tick)"
          stroke="var(--hairline)"
          :stroke-dasharray="tick === 0 ? undefined : '2 4'"
        />
        <template v-for="tick in ticks" :key="tick">
          <text :x="pad.left - 10" :y="y(tick) + 4" text-anchor="end" class="fill-slate-500 text-[11px] tabular-nums">
            {{ formatAxis ? formatAxis(tick) : tick }}
          </text>
        </template>
      </template>
      <!-- Hover band behind the active column -->
      <rect
        v-if="tip"
        :x="pad.left + tip.i * slot + 2"
        :y="pad.top"
        :width="Math.max(0, slot - 4)"
        :height="plotH"
        rx="8"
        fill="var(--color-brand-tint)"
        class="pointer-events-none transition-[x] duration-200 ease-out"
      />
      <g
        v-for="(bar, i) in bars"
        :key="`${drawKey}-${i}`"
        class="transition-opacity duration-200"
        :style="{ opacity: hovered === null ? (active < 0 || active === i ? 1 : 0.85) : active === i ? 1 : 0.45 }"
      >
        <rect
          v-for="(r, k) in bar.rects"
          :key="k"
          :x="r.x"
          :y="r.y"
          :width="r.w"
          :height="r.h"
          :rx="r.kind === 'striped' ? 0 : 3"
          :fill="r.kind === 'soft' ? 'var(--color-brand-200)' : r.kind === 'solid' ? 'var(--color-brand-600)' : `url(#${id}-lines)`"
          class="chart-grow"
          :style="{ animationDelay: `${Math.min(i * 28, 600) + k * 60}ms` }"
        />
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
          @pointerenter="hovered = i"
          @pointerdown="hovered = i"
        />
      </g>
    </svg>

    <!-- Value box -->
    <div
      v-if="tip"
      class="chart-tip pointer-events-none absolute top-0 z-10 w-44 -translate-x-1/2 rounded-xl p-3 text-[13px]"
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
