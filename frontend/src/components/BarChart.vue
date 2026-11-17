<script setup lang="ts">
// Rounded bar chart drawn in SVG (no chart library). One segment per bar
// gives a simple chart; several segments stack (e.g. one per shop). The
// highest bar, or the hovered one, is solid and shows its value; the others
// are striped.
import { computed, onBeforeUnmount, onMounted, ref, useId } from 'vue'

export interface BarSegment {
  value: number
  color: string
  name?: string
}
export interface Bar {
  key: string
  label: string
  title: string
  segments: BarSegment[]
}

const props = withDefaults(
  defineProps<{
    bars: Bar[]
    formatValue: (value: number) => string
    formatAxis: (value: number) => string
    height?: number
    striped?: boolean
    /** Show every n-th label under the bars (for long series). */
    labelEvery?: number
    label: string
  }>(),
  { height: 280, striped: true, labelEvery: 1 },
)

const box = ref<HTMLDivElement | null>(null)
const width = ref(320)
let observer: ResizeObserver | undefined
onMounted(() => {
  // Measure once now; the observer then follows window and layout changes.
  if (box.value?.clientWidth) width.value = Math.max(240, box.value.clientWidth)
  observer = new ResizeObserver(([entry]) => (width.value = Math.max(240, entry.contentRect.width)))
  if (box.value) observer.observe(box.value)
})
onBeforeUnmount(() => observer?.disconnect())

const id = useId()
const hovered = ref<number | null>(null)

const PAD = { top: 44, right: 4, bottom: 30, left: 44 }
const GAP = 3

const totals = computed(() => props.bars.map((bar) => bar.segments.reduce((sum, s) => sum + Math.max(0, s.value), 0)))

/** Round the axis up to 1, 2, 2.5 or 5 times a power of ten. */
const axisMax = computed(() => {
  const max = Math.max(...totals.value, 0)
  if (max <= 0) return 100
  const step = max / 5
  const power = 10 ** Math.floor(Math.log10(step))
  const nice = [1, 2, 2.5, 5, 10].find((n) => n * power >= step) ?? 10
  return nice * power * 5
})
const ticks = computed(() => Array.from({ length: 6 }, (_, i) => (axisMax.value / 5) * i))

const plot = computed(() => ({
  width: width.value - PAD.left - PAD.right,
  height: props.height - PAD.top - PAD.bottom,
}))
const slot = computed(() => plot.value.width / Math.max(1, props.bars.length))
const barWidth = computed(() => Math.max(4, Math.min(slot.value * 0.6, 52)))

// Skip labels when they would not fit under their bars (long day names,
// narrow screens). About 6.5 px per character at 12 px.
const every = computed(() => {
  const longest = Math.max(1, ...props.bars.map((bar) => bar.label.length))
  return Math.max(props.labelEvery, Math.ceil((longest * 6.5 + 8) / slot.value))
})

const y = (value: number) => PAD.top + plot.value.height - (value / axisMax.value) * plot.value.height

const peak = computed(() => {
  let best = -1
  totals.value.forEach((total, i) => {
    if (total > 0 && (best < 0 || total > totals.value[best])) best = i
  })
  return best
})
const active = computed(() => hovered.value ?? peak.value)

const layout = computed(() =>
  props.bars.map((bar, i) => {
    const x = PAD.left + i * slot.value + (slot.value - barWidth.value) / 2
    let base = PAD.top + plot.value.height
    const pieces = bar.segments
      .filter((s) => s.value > 0)
      .map((segment) => {
        const h = (segment.value / axisMax.value) * plot.value.height
        const piece = { x, y: base - h, height: Math.max(0, h - GAP), color: segment.color }
        base -= h
        return piece
      })
    return { x, center: x + barWidth.value / 2, top: y(totals.value[i]), pieces }
  }),
)

const tooltip = computed(() => {
  const i = active.value
  if (i < 0 || i >= props.bars.length) return null
  const text = props.formatValue(totals.value[i])
  const w = Math.max(56, text.length * 7.4 + 22)
  const cx = layout.value[i].center
  const left = Math.min(Math.max(cx - w / 2, PAD.left - 30), width.value - w)
  return { text, w, left, cx, top: layout.value[i].top }
})
</script>

<template>
  <div ref="box" class="w-full min-w-0 overflow-hidden" dir="ltr">
    <svg :width="width" :height="height" role="img" :aria-label="label" class="block overflow-visible">
      <defs>
        <pattern :id="`${id}-stripes`" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="7" height="7" fill="transparent" />
          <line x1="0" y1="0" x2="0" y2="7" stroke="white" stroke-opacity="0.22" stroke-width="3" />
        </pattern>
      </defs>

      <!-- Grid and axis -->
      <g>
        <template v-for="tick in ticks" :key="tick">
          <line
            :x1="PAD.left"
            :x2="width - PAD.right"
            :y1="y(tick)"
            :y2="y(tick)"
            stroke="var(--hairline)"
            stroke-dasharray="4 5"
          />
          <text :x="PAD.left - 10" :y="y(tick) + 4" text-anchor="end" class="fill-slate-400 text-[11px] tabular-nums">
            {{ formatAxis(tick) }}
          </text>
        </template>
      </g>

      <!-- Bars -->
      <g v-for="(bar, i) in layout" :key="bars[i].key">
        <g :opacity="active === i || active < 0 ? 1 : 0.92">
          <template v-for="(piece, p) in bar.pieces" :key="p">
            <rect
              :x="piece.x"
              :y="piece.y"
              :width="barWidth"
              :height="piece.height"
              :rx="Math.min(barWidth / 2, piece.height / 2, 14)"
              :fill="piece.color"
            />
            <rect
              v-if="striped && active !== i"
              :x="piece.x"
              :y="piece.y"
              :width="barWidth"
              :height="piece.height"
              :rx="Math.min(barWidth / 2, piece.height / 2, 14)"
              :fill="`url(#${id}-stripes)`"
            />
          </template>
        </g>
        <text
          v-if="(bars.length - 1 - i) % every === 0"
          :x="bar.center"
          :y="height - 8"
          text-anchor="middle"
          class="text-[12px]"
          :class="active === i ? 'fill-slate-900 font-medium' : 'fill-slate-500'"
        >
          {{ bars[i].label }}
        </text>
        <!-- Hover / tap target covering the whole column -->
        <rect
          :x="PAD.left + i * slot"
          :y="PAD.top - 20"
          :width="slot"
          :height="plot.height + 20"
          fill="transparent"
          class="cursor-pointer"
          @mouseenter="hovered = i"
          @mouseleave="hovered = null"
          @click="hovered = i"
        >
          <title>{{ bars[i].title }}: {{ formatValue(totals[i]) }}</title>
        </rect>
      </g>

      <!-- Value bubble over the highlighted bar -->
      <g v-if="tooltip" class="pointer-events-none">
        <rect :x="tooltip.left" :y="tooltip.top - 40" :width="tooltip.w" height="28" rx="9" class="fill-slate-900" />
        <text
          :x="tooltip.left + tooltip.w / 2"
          :y="tooltip.top - 21"
          text-anchor="middle"
          class="fill-white text-[13px] font-semibold tabular-nums"
          style="fill: var(--color-slate-50)"
        >
          {{ tooltip.text }}
        </text>
        <circle :cx="tooltip.cx" :cy="tooltip.top" r="5" class="fill-white" stroke="var(--color-slate-900)" stroke-width="2.5" />
      </g>
    </svg>

    <!-- The same figures as a table for screen readers. -->
    <div class="sr-only">
    <table>
      <caption>{{ label }}</caption>
      <tbody>
        <tr v-for="(bar, i) in bars" :key="bar.key">
          <th scope="row">{{ bar.title }}</th>
          <td>{{ formatValue(totals[i]) }}</td>
        </tr>
      </tbody>
    </table>
    </div>
  </div>
</template>
