<script setup lang="ts">
// Smooth line with a fading fill and a value bubble on one point.
import { computed, onBeforeUnmount, onMounted, ref, useId } from 'vue'

const props = withDefaults(
  defineProps<{
    points: { label: string; value: number }[]
    format: (value: number) => string
    label: string
    highlight?: number
    height?: number
  }>(),
  { highlight: -1, height: 150 },
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
  return { xy, line, area }
})

// Label every n-th point, as often as the width allows (about 6 px per character).
const every = computed(() => {
  const step = (width.value - PAD.side * 2) / Math.max(1, props.points.length - 1)
  const longest = Math.max(1, ...props.points.map((p) => p.label.length))
  return Math.max(2, Math.ceil((longest * 7 + 16) / step))
})

const bubble = computed(() => {
  const i = props.highlight
  const point = geometry.value.xy[i]
  if (!point) return null
  const text = props.format(props.points[i].value)
  const w = text.length * 7 + 18
  const left = Math.min(Math.max(point.x - w / 2, 0), width.value - w)
  return { text, w, left, x: point.x, y: point.y }
})
</script>

<template>
  <div ref="box" class="w-full min-w-0 overflow-hidden" dir="ltr">
    <svg :width="width" :height="height" role="img" :aria-label="label" class="block">
      <defs>
        <linearGradient :id="`${id}-fill`" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="var(--color-brand-600)" stop-opacity="0.45" />
          <stop offset="100%" stop-color="var(--color-brand-600)" stop-opacity="0" />
        </linearGradient>
      </defs>
      <path :d="geometry.area" :fill="`url(#${id}-fill)`" />
      <path :d="geometry.line" fill="none" stroke="var(--color-brand-600)" stroke-width="2.5" stroke-linecap="round" />
      <template v-for="(p, i) in geometry.xy" :key="i">
        <circle
          v-if="i % 2 === 1 || i === highlight"
          :cx="p.x"
          :cy="p.y"
          :r="i === highlight ? 5 : 4"
          fill="var(--color-brand-600)"
          stroke="var(--color-white)"
          stroke-width="2"
        />
        <text
          v-if="(points.length - 1 - i) % every === 0"
          :x="p.x"
          :y="height - 6"
          :text-anchor="i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'"
          class="fill-slate-500 text-[11px]"
        >
          {{ points[i].label }}
        </text>
      </template>
      <g v-if="bubble">
        <rect :x="bubble.left" :y="bubble.y - 34" :width="bubble.w" height="22" rx="6" fill="var(--color-brand-200)" />
        <text :x="bubble.left + bubble.w / 2" :y="bubble.y - 19" text-anchor="middle" class="text-[11px] font-semibold" fill="#1a1a1a">
          {{ bubble.text }}
        </text>
      </g>
    </svg>
  </div>
</template>
