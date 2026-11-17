<script setup lang="ts">
// Smooth line with a fading fill. It draws itself in; moving the pointer (or a
// finger) along it shows a guide line and a box with the date and value of
// the nearest point. With no pointer, the box sits on the `highlight` point.
import { computed, onBeforeUnmount, onMounted, ref, useId } from 'vue'

const props = withDefaults(
  defineProps<{
    points: { label: string; title?: string; value: number }[]
    format: (value: number) => string
    label: string
    /** Name of the series, shown in the hover box. */
    series?: string
    highlight?: number
    height?: number
  }>(),
  { highlight: -1, height: 150, series: '' },
)

const box = ref<HTMLDivElement | null>(null)
const width = ref(280)
let observer: ResizeObserver | undefined
onMounted(() => {
  if (box.value?.clientWidth) width.value = box.value.clientWidth
  observer = new ResizeObserver(([entry]) => (width.value = Math.max(160, entry.contentRect.width)))
  if (box.value) observer.observe(box.value)
})
onBeforeUnmount(() => observer?.disconnect())

const id = useId()
const PAD = { top: 38, bottom: 26, side: 8 }

const geometry = computed(() => {
  const values = props.points.map((p) => p.value)
  const max = Math.max(...values, 1) * 1.08
  const min = Math.min(...values, 0) * 0.75
  const plotH = props.height - PAD.top - PAD.bottom
  const step = (width.value - PAD.side * 2) / Math.max(1, props.points.length - 1)
  const xy = props.points.map((p, i) => ({
    x: PAD.side + i * step,
    y: PAD.top + (1 - (p.value - min) / (max - min || 1)) * plotH,
  }))
  // Smooth curve through every point (cardinal spline as cubic Béziers).
  let line = `M ${xy[0]?.x ?? 0} ${xy[0]?.y ?? 0}`
  for (let i = 0; i < xy.length - 1; i++) {
    const p0 = xy[i - 1] ?? xy[i]
    const p1 = xy[i]
    const p2 = xy[i + 1]
    const p3 = xy[i + 2] ?? p2
    const t = 0.18
    line += ` C ${p1.x + (p2.x - p0.x) * t} ${p1.y + (p2.y - p0.y) * t}, ${p2.x - (p3.x - p1.x) * t} ${p2.y - (p3.y - p1.y) * t}, ${p2.x} ${p2.y}`
  }
  const bottom = PAD.top + plotH
  const area = `${line} L ${xy.at(-1)?.x ?? 0} ${bottom} L ${xy[0]?.x ?? 0} ${bottom} Z`
  return { xy, line, area, step, bottom }
})

// Replays the draw-in when the data itself changes (another shop chosen).
const drawKey = computed(() => props.points.map((p) => p.value).join(','))

// Label every n-th point, as often as the width allows (about 6 px per character).
const every = computed(() => {
  const longest = Math.max(1, ...props.points.map((p) => p.label.length))
  return Math.max(2, Math.ceil((longest * 7 + 16) / geometry.value.step))
})

const hovered = ref<number | null>(null)
const active = computed(() => hovered.value ?? props.highlight)

function track(event: PointerEvent) {
  const rect = (event.currentTarget as SVGElement).getBoundingClientRect()
  const x = event.clientX - rect.left
  const i = Math.round((x - PAD.side) / (geometry.value.step || 1))
  hovered.value = Math.min(props.points.length - 1, Math.max(0, i))
}

const tip = computed(() => {
  const i = active.value
  const point = geometry.value.xy[i]
  if (!point) return null
  // Above the point, or below it when the point is near the top.
  const below = point.y < (hovered.value === null ? 30 : 64)
  return {
    i,
    x: point.x,
    y: point.y,
    below,
    title: props.points[i].title ?? props.points[i].label,
    value: props.format(props.points[i].value),
  }
})
</script>

<template>
  <div ref="box" class="relative w-full min-w-0" dir="ltr" @pointerleave="hovered = null">
    <svg
      :width="width"
      :height="height"
      role="img"
      :aria-label="label"
      class="block touch-pan-y"
      @pointermove="track"
      @pointerdown="track"
    >
      <defs>
        <linearGradient :id="`${id}-fill`" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="var(--color-brand-600)" stop-opacity="0.42" />
          <stop offset="100%" stop-color="var(--color-brand-600)" stop-opacity="0" />
        </linearGradient>
      </defs>
      <!-- Faint baseline grid -->
      <line :x1="PAD.side" :x2="width - PAD.side" :y1="geometry.bottom" :y2="geometry.bottom" stroke="var(--hairline)" />

      <g :key="drawKey">
        <path :d="geometry.area" :fill="`url(#${id}-fill)`" class="chart-fade" />
        <path
          :d="geometry.line"
          pathLength="1"
          fill="none"
          stroke="var(--color-brand-600)"
          stroke-width="2.5"
          stroke-linecap="round"
          class="chart-draw"
        />
      </g>

      <!-- Hover guide -->
      <line
        v-if="tip"
        :x1="tip.x"
        :x2="tip.x"
        :y1="PAD.top - 8"
        :y2="geometry.bottom"
        stroke="var(--color-brand-600)"
        stroke-opacity="0.35"
        stroke-dasharray="3 3"
        class="pointer-events-none"
      />

      <template v-for="(p, i) in geometry.xy" :key="i">
        <circle
          v-if="i % 2 === 1 && i !== active"
          :cx="p.x"
          :cy="p.y"
          r="3"
          fill="var(--color-brand-600)"
          stroke="var(--color-white)"
          stroke-width="1.5"
          class="chart-fade pointer-events-none"
        />
        <text
          v-if="(points.length - 1 - i) % every === 0"
          :x="p.x"
          :y="height - 6"
          :text-anchor="i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'"
          class="text-[11px] transition-colors"
          :class="i === active ? 'fill-slate-900 font-medium' : 'fill-slate-500'"
        >
          {{ points[i].label }}
        </text>
      </template>

      <!-- Active point with a soft halo -->
      <g v-if="tip" class="pointer-events-none">
        <circle :cx="tip.x" :cy="tip.y" r="10" fill="var(--color-brand-600)" fill-opacity="0.16" />
        <circle :cx="tip.x" :cy="tip.y" r="5" fill="var(--color-brand-600)" stroke="var(--color-white)" stroke-width="2" />
      </g>
    </svg>

    <!-- Value box -->
    <div
      v-if="tip"
      class="chart-tip pointer-events-none absolute z-10 text-[12px] leading-tight whitespace-nowrap"
      :class="hovered === null ? 'rounded-lg px-2 py-1' : 'rounded-xl px-3 py-2'"
      :style="{
        left: hovered === null ? `clamp(2rem, ${tip.x}px, calc(100% - 2rem))` : `clamp(3.5rem, ${tip.x}px, calc(100% - 3.5rem))`,
        top: `${tip.y}px`,
        transform: tip.below ? 'translate(-50%, 14px)' : 'translate(-50%, calc(-100% - 14px))',
      }"
      aria-hidden="true"
    >
      <!-- At rest only the value; the date and series appear on hover. -->
      <div v-if="hovered === null" class="text-[12px] font-semibold text-slate-900 tabular-nums">{{ tip.value }}</div>
      <template v-else>
      <div class="text-slate-500">{{ tip.title }}</div>
      <div class="mt-0.5 flex items-center gap-1.5">
        <span class="h-2 w-2 rounded-full bg-brand-600" />
        <span v-if="series" class="text-slate-600">{{ series }}</span>
        <span class="ms-auto ps-2 text-[14px] font-semibold text-slate-900 tabular-nums">{{ tip.value }}</span>
      </div>
      </template>
    </div>

    <div class="sr-only">
      <table>
        <caption>{{ label }}</caption>
        <tbody>
          <tr v-for="p in points" :key="p.label">
            <th scope="row">{{ p.title ?? p.label }}</th>
            <td>{{ format(p.value) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
