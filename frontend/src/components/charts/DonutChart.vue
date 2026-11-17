<script setup lang="ts">
// Donut with the percentage written on each slice; the largest slice is
// pushed out slightly.
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    slices: { label: string; value: number; color: string; dark?: boolean }[]
    label: string
    size?: number
  }>(),
  { size: 180 },
)

const total = computed(() => props.slices.reduce((sum, s) => sum + s.value, 0) || 1)
const biggest = computed(() => props.slices.reduce((best, s, i, all) => (s.value > all[best].value ? i : best), 0))

const arcs = computed(() => {
  const c = props.size / 2
  const outer = c - 8
  const inner = outer * 0.45
  let angle = -Math.PI / 2
  return props.slices.map((slice, i) => {
    const sweep = (slice.value / total.value) * Math.PI * 2
    const start = angle
    const end = angle + sweep
    angle = end
    const mid = (start + end) / 2
    const push = i === biggest.value ? 6 : 0
    const dx = Math.cos(mid) * push
    const dy = Math.sin(mid) * push
    const point = (r: number, a: number) => `${c + dx + r * Math.cos(a)} ${c + dy + r * Math.sin(a)}`
    const large = sweep > Math.PI ? 1 : 0
    const gap = 0.012
    const d = [
      `M ${point(outer, start + gap)}`,
      `A ${outer} ${outer} 0 ${large} 1 ${point(outer, end - gap)}`,
      `L ${point(inner, end - gap)}`,
      `A ${inner} ${inner} 0 ${large} 0 ${point(inner, start + gap)}`,
      'Z',
    ].join(' ')
    const labelR = (outer + inner) / 2
    return {
      d,
      color: slice.color,
      dark: slice.dark,
      percent: Math.round((slice.value / total.value) * 100),
      lx: c + dx + labelR * Math.cos(mid),
      ly: c + dy + labelR * Math.sin(mid) + 4,
    }
  })
})
</script>

<template>
  <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`" role="img" :aria-label="label" class="mx-auto block overflow-visible" dir="ltr">
    <g v-for="(arc, i) in arcs" :key="i">
      <path :d="arc.d" :fill="arc.color">
        <title>{{ slices[i].label }}: {{ arc.percent }}%</title>
      </path>
      <text
        v-if="arc.percent >= 5"
        :x="arc.lx"
        :y="arc.ly"
        text-anchor="middle"
        class="pointer-events-none text-[12px] font-semibold"
        :fill="arc.dark ? '#1a1a1a' : '#ffffff'"
      >
        {{ arc.percent }}%
      </text>
    </g>
  </svg>
</template>
