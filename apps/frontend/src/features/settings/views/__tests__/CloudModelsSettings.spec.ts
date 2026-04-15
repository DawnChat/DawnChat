import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

import CloudModelsSettings from '../CloudModelsSettings.vue'
import { SETTINGS_SECTION_RESELECTED } from '../../settingsNavigationEvents'

const loadModels = vi.fn()

vi.mock('@/stores/llmSelectionStore', () => ({
  useLlmSelectionStore: () => ({
    loadModels,
  }),
}))

vi.mock('@/utils/backendUrl', () => ({
  buildBackendUrl: (path = '') => path,
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    info: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('@/composables/useI18n', () => ({
  useI18n: () => ({
    t: ref({
      common: {
        installed: 'Installed',
        save: 'Save',
        saving: 'Saving...',
        cancel: 'Cancel',
        deleteConfig: 'Delete',
      },
      models: {
        noInstalled: 'Not installed',
      },
      settings: {
        cloudModels: {
          title: 'Cloud Models',
          desc: 'Configure provider keys',
          keychainPermissionTitle: 'Allow Keychain Access',
          keychainPermissionHint: 'Choose Always Allow in Keychain prompt.',
          keychainPermissionConfirm: 'Got it',
          apiKey: 'API Key',
          apiKeyPlaceholder: 'Enter API key',
          apiKeyPlaceholderConfigured: 'Configured, enter to update',
          confirmDelete: 'Delete {name}?',
          securityNote: 'Security note',
        },
      },
      errors: {
        saveApiKeyFailed: 'save api key failed',
      },
    }),
  }),
}))

const flushPromises = async () => {
  await Promise.resolve()
  await Promise.resolve()
}

describe('CloudModelsSettings', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    loadModels.mockReset()
    Object.defineProperty(window.navigator, 'platform', {
      configurable: true,
      value: 'MacIntel',
    })
  })

  it('保存时仅提交 API Key 且不再请求 models 接口', async () => {
    vi.spyOn(window, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (url === '/api/cloud/providers' && !init) {
        return {
          ok: true,
          json: async () => ({
            providers: [
              {
                id: 'openai',
                name: 'OpenAI',
                is_configured: false,
                model_count: 0,
              },
            ],
          }),
        } as Response
      }
      if (url === '/api/cloud/providers/openai' && !init) {
        return { ok: true, json: async () => ({ provider: { id: 'openai' } }) } as Response
      }
      if (url === '/api/cloud/providers/openai' && init?.method === 'POST') {
        return { ok: true, json: async () => ({ status: 'success' }) } as Response
      }
      throw new Error(`Unexpected fetch: ${url} ${String(init?.method || 'GET')}`)
    })

    const wrapper = mount(CloudModelsSettings, { attachTo: document.body })
    await flushPromises()

    await wrapper.find('.provider-header').trigger('click')
    await flushPromises()

    const input = wrapper.find('input.config-input')
    await input.setValue('sk-test-openai-12345')
    await wrapper.find('button.save-btn').trigger('click')
    await flushPromises()
    const confirmButton = document.body.querySelector('.dialog-btn-confirm') as HTMLButtonElement | null
    expect(confirmButton).toBeTruthy()
    confirmButton?.click()
    await flushPromises()
    await flushPromises()

    const calls = vi.mocked(window.fetch).mock.calls.map(([url, init]) => ({
      url: String(url),
      method: init?.method ?? 'GET',
    }))
    expect(calls).toContainEqual({ url: '/api/cloud/providers/openai', method: 'POST' })
    expect(calls).not.toContainEqual({ url: '/api/cloud/providers/openai/models', method: 'POST' })
    expect(loadModels).toHaveBeenCalledWith(true)
    wrapper.unmount()
  })
  it('再次选中云端模型设置时分发事件会重新拉取厂商列表', async () => {
    vi.spyOn(window, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (url === '/api/cloud/providers' && !init) {
        return {
          ok: true,
          json: async () => ({
            providers: [
              {
                id: 'openai',
                name: 'OpenAI',
                is_configured: false,
                model_count: 0,
              },
            ],
          }),
        } as Response
      }
      throw new Error(`Unexpected fetch: ${url}`)
    })

    const wrapper = mount(CloudModelsSettings, { attachTo: document.body })
    await flushPromises()

    const listCallsBefore = vi.mocked(window.fetch).mock.calls.filter(
      ([url, init]) => String(url) === '/api/cloud/providers' && !init
    ).length
    expect(listCallsBefore).toBeGreaterThanOrEqual(1)

    window.dispatchEvent(
      new CustomEvent(SETTINGS_SECTION_RESELECTED, { detail: { section: 'cloud-models' } })
    )
    await flushPromises()

    const listCallsAfter = vi.mocked(window.fetch).mock.calls.filter(
      ([url, init]) => String(url) === '/api/cloud/providers' && !init
    ).length
    expect(listCallsAfter).toBeGreaterThan(listCallsBefore)

    wrapper.unmount()
  })

})
