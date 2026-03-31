import { beforeEach, describe, expect, it, vi } from 'vitest'
import { checkForAppUpdate, compareSemver } from '@/features/update/services/updateService'

let mockedVersion = '2.0.0'

vi.mock('@tauri-apps/api/app', () => ({
  getVersion: vi.fn(async () => mockedVersion)
}))

describe('updateService', () => {
  beforeEach(() => {
    mockedVersion = '2.0.0'
    ;(window as any).__TAURI_INTERNALS__ = {}
  })

  it('支持 semver 比较', () => {
    expect(compareSemver('2.0.0', '2.0.0')).toBe(0)
    expect(compareSemver('v2.1.0', '2.0.9')).toBe(1)
    expect(compareSemver('1.9.9', '2.0.0')).toBe(-1)
  })

  it('平台版本更高时返回建议更新', async () => {
    const result = await checkForAppUpdate(async () => {
      return {
        ok: true,
        json: async () => ({
          channels: {
            stable: {
              latest_version: '2.0.0',
              min_supported_version: '2.0.0',
              downloads: { fallback: 'https://plugins.dawnchat.com/download' },
              platforms: {
                'darwin-aarch64': {
                  latest_version: '2.1.0',
                  min_supported_version: '2.0.0',
                  download_url: 'https://plugins.dawnchat.com/downloads/mac.dmg'
                }
              }
            }
          }
        })
      } as Response
    })

    expect(result.mode).toBe('recommended')
    expect(result.downloadUrl).toBe('https://plugins.dawnchat.com/downloads/mac.dmg')
  })

  it('当前版本低于最小支持版本时返回强制更新', async () => {
    mockedVersion = '1.9.0'
    const result = await checkForAppUpdate(async () => {
      return {
        ok: true,
        json: async () => ({
          channels: {
            stable: {
              latest_version: '2.1.0',
              min_supported_version: '2.0.0',
              downloads: { fallback: 'https://plugins.dawnchat.com/download' }
            }
          }
        })
      } as Response
    })

    expect(result.mode).toBe('forced')
    expect(result.downloadUrl).toBe('https://plugins.dawnchat.com/download')
  })

  it('当前版本已是最新时不提示更新', async () => {
    const result = await checkForAppUpdate(async () => {
      return {
        ok: true,
        json: async () => ({
          channels: {
            stable: {
              latest_version: '2.0.0',
              min_supported_version: '2.0.0',
              downloads: { fallback: 'https://plugins.dawnchat.com/download' }
            }
          }
        })
      } as Response
    })

    expect(result.mode).toBe('none')
  })
})
