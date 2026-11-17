// Small motion helpers. Everything here respects the device's "reduce
// motion" setting: numbers then jump straight to their value.
import { onBeforeUnmount, ref, watch } from 'vue'

const reduceQuery = window.matchMedia('(prefers-reduced-motion: reduce)')

export function reducedMotion(): boolean {
  return reduceQuery.matches
}

const easeOutCubic = (t: number) => 1 - (1 - t) ** 3

/**
 * A number that counts from its previous value to the new one whenever the
 * source changes (whole numbers while moving, the exact value at the end).
 */
export function useCountUp(source: () => number, duration = 900) {
  const value = ref(0)
  let frame = 0

  watch(
    source,
    (to) => {
      cancelAnimationFrame(frame)
      const from = value.value
      if (reducedMotion() || from === to || document.hidden) {
        value.value = to
        return
      }
      const start = performance.now()
      const step = (now: number) => {
        const t = Math.min(1, (now - start) / duration)
        value.value = t < 1 ? Math.round(from + (to - from) * easeOutCubic(t)) : to
        if (t < 1) frame = requestAnimationFrame(step)
      }
      frame = requestAnimationFrame(step)
    },
    { immediate: true },
  )
  onBeforeUnmount(() => cancelAnimationFrame(frame))
  return value
}
