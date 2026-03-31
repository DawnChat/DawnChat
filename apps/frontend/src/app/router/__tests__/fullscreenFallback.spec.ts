import { describe, it, expect } from 'vitest'
import { resolveFullscreenBackTarget } from '../deepLink'

describe('resolveFullscreenBackTarget', () => {
  it('falls back when from is missing', () => {
    expect(resolveFullscreenBackTarget(undefined)).toBe('/app/apps/hub')
  })

  it('falls back when from is cross-origin like path', () => {
    expect(resolveFullscreenBackTarget('//evil.example/path')).toBe('/app/apps/hub')
  })

  it('keeps fullscreen internal route when valid', () => {
    expect(resolveFullscreenBackTarget('/fullscreen/plugin/demo')).toBe('/fullscreen/plugin/demo')
  })
})
