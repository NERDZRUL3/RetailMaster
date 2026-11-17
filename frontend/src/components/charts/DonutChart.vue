<script setup lang="ts">
// Donut with the percentage written on each slice. It sweeps in clockwise;
// hovering (or tapping) a slice pushes it out, dims the others and shows its
// name, value and share in the middle. With no slice hovered, the middle
// shows the total. `v-model:active` lets a legend light up a slice too.
import { computed, useId } from 'vue'

const props = withDefaults(
  defineProps<{
    slices: { label: string; value: number; color: string; dark?: boolean }[]
    label: string
    size?: number
    format?: (value: number) => string
    /** Caption under the total in the middle. */
    totalLabel?: string
  }>(),
  { size: 180, format: (value: number) => String(value), totalLabel: '' },
)
const active = defineModel<number | null>('active', { default: null })

const id = useId()
const total = computed(() => props.slices.reduce((sum, s) => sum + s.value, 0) || 1)
const c = computed(() => props.size / 2)
const outer = computed(() => c.value - 10)
const inner = computed(() => outer.value * 0.6)

const arcs = computed(() => {
  let angle = -Math.PI / 2
  return props.slices.map((slice) => {
    const sweep = (slice.value / total.value) * Math.PI * 2
    const start = angle
    const end = angle + sweep
    angle = end
    const mid = (start + end) / 2
    const point = (r: number, a: number) => `${c.value + r * Math.cos(a)} ${c.value + r * Math.sin(a)}`
    const large = sweep > Math.PI ? 1 : 0
    const gap = props.slices.length > 1 ? 0.014 : 0
    // A single full slice cannot be one arc; stop just short of the circle.
    const stop = props.slices.length > 1 ? end - gap : end - 0.0001
    const d = [
      `M ${point(outer.value, start + gap)}`,
      `A ${outer.value} ${outer.value} 0 ${large} 1 ${point(outer.value, stop)}`,
      `L ${point(inner.value, stop)}`,
      `A ${inner.value} ${inner.value} 0 ${large} 0 ${point(inner.value, start + gap)}`,
      'Z',
    ].join(' ')
    const labelR = (outer.value + inner.value) / 2
    return {
      d,
      color: slice.color,
      dark: slice.dark,
      percent: Math.round((slice.value / total.value) * 100),
      // Direction the slice moves out when it is hovered.
      dx: Math.cos(mid) * 7,
      dy: Math.sin(mid) * 7,
      lx: c.value + labelR * Math.cos(mid),
      ly: c.value + labelR * Math.sin(mid) + 4,
    }
  })
})

const drawKey = computed(() => props.slices.map((s) => `${s.label}:${s.value}`).join('|'))
const current = computed(() => (active.value === null ? null : (props.slices[active.value] ?? null)))
</script>

<template>
  <div class="relative mx-auto" :style="{ width: `${size}px`, height: `${size}px` }" @pointerleave="active = null">
    <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`" role="img" :aria-label="label" class="block overflow-visible" dir="ltr">
      <defs>
        <!-- Clockwise reveal from the top -->
        <mask :id="`${id}-sweep`" maskUnits="userSpaceOnUse" x="0" y="0" :width="size" :height="size">
          <circle
            :key="drawKey"
            :cx="c"
            :cy="c"
            :r="c / 2"
            fill="none"
            stroke="white"
            :stroke-width="c"
            pathLength="1"
            :transform="`rotate(-90 ${c} ${c})`"
            class="chart-sweep"
          />
        </mask>
      </defs>
      <g :mask="`url(#${id}-sweep)`">
        <g
          v-for="(arc, i) in arcs"
          :key="i"
          class="cursor-pointer transition-[transform,opacity] duration-300 ease-[var(--ease-spring)]"
          :style="{
            transform: active === i ? `translate(${arc.dx}px, ${arc.dy}px)` : 'none',
            opacity: active === null || active === i ? 1 : 0.4,
          }"
          @pointerenter="active = i"
          @pointerdown="active = i"
        >
          <path :d="arc.d" :fill="arc.color">
            <title>{{ slices[i].label }}: {{ format(slices[i].value) }} ({{ arc.percent }}%)</title>
          </path>
          <text
            v-if="arc.percent >= 6"
            :x="arc.lx"
            :y="arc.ly"
            text-anchor="middle"
            class="pointer-events-none text-[11px] font-semibold"
            :fill="arc.dark ? '#1a1a1a' : '#ffffff'"
          >
            {{ arc.percent }}%
          </text>
        </g>
      </g>
    </svg>

    <!-- Middle readout -->
    <div
      class="pointer-events-none absolute inset-0 grid place-items-center text-center"
      aria-hidden="true"
    >
      <Transition name="fade" mode="out-in">
        <div :key="current?.label ?? '__total'" class="max-w-[58%] leading-tight">
          <template v-if="current">
            <div class="truncate text-[11px] text-slate-500"><bdi>{{ current.label }}</bdi></div>
            <div class="text-[15px] font-semibold text-slate-900 tabular-nums">{{ format(current.value) }}</div>
            <div class="text-[11px] font-medium text-brand-ink tabular-nums">{{ arcs[active!]?.percent }}%</div>
          </template>
          <template v-else>
            <div class="text-[15px] font-semibold text-slate-900 tabular-nums">{{ format(total) }}</div>
            <div v-if="totalLabel" class="truncate text-[11px] text-slate-500">{{ totalLabel }}</div>
          </template>
        </div>
      </Transition>
    </div>
  </div>
</template>
