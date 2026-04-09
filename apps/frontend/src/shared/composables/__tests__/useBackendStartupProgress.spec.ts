import { describe, expect, it } from 'vitest'
import {
  computeStartupTargetForElapsed,
  EXPECTED_BOOT_MS,
} from '@/shared/composables/useBackendStartupProgress'

describe('computeStartupTargetForElapsed', () => {
  it('returns 0 for non-positive elapsed', () => {
    expect(computeStartupTargetForElapsed(0)).toBe(0)
    expect(computeStartupTargetForElapsed(-100)).toBe(0)
  })

  it('ramps with ease-out toward 95% by EXPECTED_BOOT_MS', () => {
    const mid = computeStartupTargetForElapsed(EXPECTED_BOOT_MS / 2)
    expect(mid).toBeGreaterThan(40)
    expect(mid).toBeLessThan(95)
    const end = computeStartupTargetForElapsed(EXPECTED_BOOT_MS)
    expect(end).toBe(95)
  })

  it('idle-creeps above 95% after EXPECTED_BOOT_MS', () => {
    const t = computeStartupTargetForElapsed(EXPECTED_BOOT_MS + 30_000)
    expect(t).toBeGreaterThan(95)
    expect(t).toBeLessThanOrEqual(98)
  })
})
