import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

import CloudModelsContent from '../CloudModelsContent.vue'

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
        configured: 'Configured',
        notConfigured: 'Not configured',
        save: 'Save',
        saving: 'Saving...',
        cancel: 'Cancel',
        deleteConfig: 'Delete',
      },
      models: {
        cloud: {
          title: 'Cloud Models',
          configuredCount: '{count} configured',
          noConfigured: 'No configured',
        },
      },
      settings: {
        cloudModels: {
          title: 'Cloud Models',
          desc: 'Configure provider keys',
          apiKeyPlaceholder: 'Enter API key',
          apiKeyPlaceholderConfigured: 'Configured, enter to update',
          securityNote: 'Security note',
          saveApiKeyFailed: 'save api key failed',
          saveSuccess: 'save {provider}',
          saveConfigFailed: 'save failed {provider}',
          confirmDelete: 'delete {name}?',
          deleteSuccess: 'deleted {provider}',
          deleteConfigFailed: 'delete failed {provider}',
        },
      },
    }),
  }),
}))

const flushPromises = async () => {
  await Promise.resolve()
  await Promise.resolve()
}

describe('CloudModelsContent', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
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

    const wrapper = mount(CloudModelsContent, { attachTo: document.body })
    await flushPromises()

    await wrapper.find('.provider-header').trigger('click')
    await flushPromises()

    await wrapper.find('input.config-input').setValue('sk-test-openai-12345')
    await wrapper.find('button.save-btn').trigger('click')
    await flushPromises()
    await flushPromises()

    const calls = vi.mocked(window.fetch).mock.calls.map(([url, init]) => ({
      url: String(url),
      method: init?.method ?? 'GET',
    }))
    expect(calls).toContainEqual({ url: '/api/cloud/providers/openai', method: 'POST' })
    expect(calls).not.toContainEqual({ url: '/api/cloud/providers/openai/models', method: 'POST' })
    wrapper.unmount()
  })
})
