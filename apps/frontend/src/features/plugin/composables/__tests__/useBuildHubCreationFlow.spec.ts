import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { useBuildHubCreationFlow } from '@/features/plugin/composables/useBuildHubCreationFlow'

vi.mock('@/composables/useI18n', () => ({
  useI18n: () => ({
    t: {
      value: {
        apps: {
          quickCreateDesktopName: '桌面应用',
          quickCreateWebName: '网页应用',
          quickCreateMobileName: '移动应用',
        },
      },
    },
  }),
}))

describe('useBuildHubCreationFlow', () => {
  it('按选择模板快速创建 desktop 应用', async () => {
    const createDevSession = vi.fn(async () => ({ task_id: 'task_1' }))
    const flow = useBuildHubCreationFlow({
      user: ref({ id: 'uid_1', email: 'demo@example.com' }),
      openCreateWizard: vi.fn(),
      closeCreateWizard: vi.fn(),
      createDevSession,
      ensureTemplateCache: vi.fn(async () => ({})),
    })

    await flow.handleQuickCreateDesktopByTemplate('com.dawnchat.desktop-ai-assistant')

    expect(createDevSession).toHaveBeenCalledTimes(1)
    const payload = createDevSession.mock.calls[0][0]
    expect(payload.template_id).toBe('com.dawnchat.desktop-ai-assistant')
    expect(payload.app_type).toBe('desktop')
    expect(payload.owner_email).toBe('demo@example.com')
    expect(payload.owner_user_id).toBe('uid_1')
  })

  it('不支持的模板 id 不会触发创建', async () => {
    const createDevSession = vi.fn(async () => ({ task_id: 'task_1' }))
    const flow = useBuildHubCreationFlow({
      user: ref({ id: 'uid_1', email: 'demo@example.com' }),
      openCreateWizard: vi.fn(),
      closeCreateWizard: vi.fn(),
      createDevSession,
      ensureTemplateCache: vi.fn(async () => ({})),
    })

    await flow.handleQuickCreateDesktopByTemplate('com.dawnchat.desktop-unknown')

    expect(createDevSession).not.toHaveBeenCalled()
  })
})
