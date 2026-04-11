import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { useBuildHubCreationFlow } from '@/features/plugin/composables/useBuildHubCreationFlow'
import {
  AI_ASSISTANT_TEMPLATE_ID,
  MOBILE_AI_ASSISTANT_TEMPLATE_ID,
  WEB_AI_ASSISTANT_TEMPLATE_ID
} from '@/config/appTemplates'

vi.mock('@/composables/useI18n', () => ({
  useI18n: () => ({
    t: {
      value: {
        apps: {
          quickCreateDesktopName: '桌面应用',
          quickCreateWebName: '网页应用',
          quickCreateMobileName: '移动应用',
          quickCreateAssistantName: '我的 AI 助手',
        },
      },
    },
  }),
}))

describe('useBuildHubCreationFlow', () => {
  it('打开 assistant 新建弹窗时会预填下一个名称', () => {
    const flow = useBuildHubCreationFlow({
      user: ref({ id: 'uid_1', email: 'demo@example.com' }),
      installedApps: ref([
        { id: 'com.demo.a1', name: '我的 AI 助手' },
        { id: 'com.demo.a2', name: '我的 AI 助手 2' },
      ] as any),
      openCreateWizard: vi.fn(),
      closeCreateWizard: vi.fn(),
      createDevSession: vi.fn(async () => ({ task_id: 'task_1' })),
      openAppDevWorkbench: vi.fn(async () => {}),
      startAppDevSession: vi.fn(async () => {}),
      ensureTemplateCache: vi.fn(async () => ({})),
    })

    flow.openCreateAssistantDialog()

    expect(flow.createAssistantDialogVisible.value).toBe(true)
    expect(flow.createAssistantDraftName.value).toBe('我的 AI 助手 3')
    expect(flow.createAssistantDraftPlatform.value).toBe('desktop')
  })

  it('从首页创建 assistant 时会创建桌面 assistant 实例', async () => {
    const createDevSession = vi.fn(async () => ({ task_id: 'task_1' }))
    const ensureTemplateCache = vi.fn(async () => ({}))
    const flow = useBuildHubCreationFlow({
      user: ref({ id: 'uid_1', email: 'demo@example.com' }),
      installedApps: ref([]),
      openCreateWizard: vi.fn(),
      closeCreateWizard: vi.fn(),
      createDevSession,
      openAppDevWorkbench: vi.fn(async () => {}),
      startAppDevSession: vi.fn(async () => {}),
      ensureTemplateCache,
    })

    flow.openCreateAssistantDialog()
    await flow.createAssistant('新的助手')

    expect(flow.createAssistantDialogVisible.value).toBe(false)
    expect(createDevSession).toHaveBeenCalledTimes(1)
    expect(createDevSession).toHaveBeenCalledWith(expect.objectContaining({
      template_id: AI_ASSISTANT_TEMPLATE_ID,
      app_type: 'desktop',
      name: '新的助手',
      owner_email: 'demo@example.com',
      owner_user_id: 'uid_1',
      is_main_assistant: false,
    }))
    expect(ensureTemplateCache).toHaveBeenCalledWith(AI_ASSISTANT_TEMPLATE_ID, false)
  })

  it('从首页创建 web assistant 时会使用 web assistant 模板', async () => {
    const createDevSession = vi.fn(async () => ({ task_id: 'task_1' }))
    const ensureTemplateCache = vi.fn(async () => ({}))
    const flow = useBuildHubCreationFlow({
      user: ref({ id: 'uid_1', email: 'demo@example.com' }),
      installedApps: ref([]),
      openCreateWizard: vi.fn(),
      closeCreateWizard: vi.fn(),
      createDevSession,
      openAppDevWorkbench: vi.fn(async () => {}),
      startAppDevSession: vi.fn(async () => {}),
      ensureTemplateCache,
    })

    flow.openCreateAssistantDialog()
    await flow.createAssistant('新的 Web 助手', 'web')

    expect(createDevSession).toHaveBeenCalledWith(expect.objectContaining({
      template_id: WEB_AI_ASSISTANT_TEMPLATE_ID,
      app_type: 'web',
      name: '新的 Web 助手',
      owner_email: 'demo@example.com',
      owner_user_id: 'uid_1',
      is_main_assistant: false,
    }))
    expect(ensureTemplateCache).toHaveBeenCalledWith(WEB_AI_ASSISTANT_TEMPLATE_ID, false)
  })

  it('从首页创建 mobile assistant 时会使用 mobile assistant 模板', async () => {
    const createDevSession = vi.fn(async () => ({ task_id: 'task_1' }))
    const ensureTemplateCache = vi.fn(async () => ({}))
    const flow = useBuildHubCreationFlow({
      user: ref({ id: 'uid_1', email: 'demo@example.com' }),
      installedApps: ref([]),
      openCreateWizard: vi.fn(),
      closeCreateWizard: vi.fn(),
      createDevSession,
      openAppDevWorkbench: vi.fn(async () => {}),
      startAppDevSession: vi.fn(async () => {}),
      ensureTemplateCache,
    })

    flow.openCreateAssistantDialog()
    await flow.createAssistant('新的 Mobile 助手', 'mobile')

    expect(createDevSession).toHaveBeenCalledWith(expect.objectContaining({
      template_id: MOBILE_AI_ASSISTANT_TEMPLATE_ID,
      app_type: 'mobile',
      name: '新的 Mobile 助手',
      owner_email: 'demo@example.com',
      owner_user_id: 'uid_1',
      is_main_assistant: false,
    }))
    expect(ensureTemplateCache).toHaveBeenCalledWith(MOBILE_AI_ASSISTANT_TEMPLATE_ID, false)
  })

  it('主 assistant 不存在时自动创建官方主实例', async () => {
    const createDevSession = vi.fn(async () => ({ task_id: 'task_1' }))
    const openAppDevWorkbench = vi.fn(async () => {})
    const startAppDevSession = vi.fn(async () => {})
    const flow = useBuildHubCreationFlow({
      user: ref({ id: 'uid_1', email: 'demo@example.com' }),
      installedApps: ref([]),
      openCreateWizard: vi.fn(),
      closeCreateWizard: vi.fn(),
      createDevSession,
      openAppDevWorkbench,
      startAppDevSession,
      ensureTemplateCache: vi.fn(async () => ({})),
    })

    await flow.openOrCreateMainAssistant()

    expect(createDevSession).toHaveBeenCalledTimes(1)
    const payload = createDevSession.mock.calls[0][0]
    expect(payload.template_id).toBe(AI_ASSISTANT_TEMPLATE_ID)
    expect(payload.app_type).toBe('desktop')
    expect(payload.is_main_assistant).toBe(true)
    expect(String(payload.plugin_id)).toContain('.dawnchat-ai-assistant')
    expect(payload.owner_email).toBe('demo@example.com')
    expect(payload.owner_user_id).toBe('uid_1')
    expect(openAppDevWorkbench).not.toHaveBeenCalled()
    expect(startAppDevSession).not.toHaveBeenCalled()
  })

  it('主 assistant 已运行时直接复用并打开工作台', async () => {
    const createDevSession = vi.fn(async () => ({ task_id: 'task_1' }))
    const openAppDevWorkbench = vi.fn(async () => {})
    const startAppDevSession = vi.fn(async () => {})
    const mainAssistant = {
      id: 'com.example.user.uid_1.dawnchat-ai-assistant',
      name: 'Main Assistant',
      version: '0.1.0',
      description: '',
      author: 'demo',
      icon: 'x',
      tags: [],
      state: 'stopped' as const,
      is_official: false,
      capabilities: { gradio: false, cards: false, chat: false, tools: false },
      runtime: null,
      error_message: null,
      source_type: 'official_user_main_assistant',
      owner_user_id: 'uid_1',
      owner_email: 'demo@example.com',
      template_id: AI_ASSISTANT_TEMPLATE_ID,
      is_main_assistant: true,
      preview: { state: 'running' as const, url: 'http://127.0.0.1', backend_port: null, frontend_port: null, error_message: null },
    }
    const flow = useBuildHubCreationFlow({
      user: ref({ id: 'uid_1', email: 'demo@example.com' }),
      installedApps: ref([mainAssistant]),
      openCreateWizard: vi.fn(),
      closeCreateWizard: vi.fn(),
      createDevSession,
      openAppDevWorkbench,
      startAppDevSession,
      ensureTemplateCache: vi.fn(async () => ({})),
    })

    await flow.openOrCreateMainAssistant()

    expect(openAppDevWorkbench).toHaveBeenCalledTimes(1)
    expect(startAppDevSession).not.toHaveBeenCalled()
    expect(createDevSession).not.toHaveBeenCalled()
  })
})
