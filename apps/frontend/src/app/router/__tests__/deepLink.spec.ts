import { describe, it, expect } from 'vitest'
import { parseDeepLink, resolveFullscreenBackTarget } from '../deepLink'

describe('deepLink parser', () => {
  it('parses plugin deep link', () => {
    const parsed = parseDeepLink('dawnchat://apps/demo-plugin')
    expect(parsed.status).toBe('valid')
    expect(parsed.route).toEqual({
      name: 'plugin-fullscreen',
      params: { pluginId: 'demo-plugin' }
    })
  })

  it('returns unsupported for unknown host', () => {
    const parsed = parseDeepLink('dawnchat://unknown/path')
    expect(parsed.status).toBe('unsupported')
    expect(parsed.route).toBeNull()
  })

  it('returns invalid for malformed deep link', () => {
    const parsed = parseDeepLink('this is not an url')
    expect(parsed.status).toBe('invalid')
    expect(parsed.route).toBeNull()
  })

  it('parses pipeline task deep link as valid route result', () => {
    const parsed = parseDeepLink('dawnchat://pipeline/task_001')
    expect(parsed.status).toBe('valid')
    expect(parsed.route).toEqual({
      name: 'pipeline-task-detail',
      params: { taskId: 'task_001' }
    })
  })
})

describe('fullscreen back target resolver', () => {
  it('accepts in-app safe path', () => {
    expect(resolveFullscreenBackTarget('/app/apps/market')).toBe('/app/apps/market')
  })

  it('falls back for unsafe path', () => {
    expect(resolveFullscreenBackTarget('https://example.com')).toBe('/app/apps/hub')
  })
})
