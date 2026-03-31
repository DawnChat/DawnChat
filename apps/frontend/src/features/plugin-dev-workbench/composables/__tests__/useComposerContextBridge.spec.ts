import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useComposerContextBridge } from '@/features/plugin-dev-workbench/composables/useComposerContextBridge'

vi.mock('@/services/plugin-ui-bridge/contextToken', () => ({
  encodeContextToken: vi.fn((preview: string, fullText: string) => `[[${preview}]]\n${fullText}`)
}))

vi.mock('@/services/plugin-ui-bridge/contextInbox', () => ({
  contextPayloadToComposerToken: vi.fn(() => ({
    preview: 'CTX_PREVIEW',
    fullText: 'CTX_FULL',
  }))
}))

describe('useComposerContextBridge', () => {
  it('失焦时会在末尾追加 inspector token', () => {
    const chatInput = ref('已有内容')
    const bridge = useComposerContextBridge({ chatInput })

    bridge.handleComposerSelectionChange({ start: 0, end: 0, focused: false })
    bridge.handleInspectorSelect({
      pluginId: 'com.test.app',
      file: '/tmp/src/App.vue',
      range: {
        start: { line: 12, column: 8 },
      },
      textSnippet: 'hello world',
    } as any)

    expect(chatInput.value).toContain('已有内容\n')
    expect(chatInput.value).toContain('[[App.vue(L12:C8)]]')
  })

  it('聚焦选区时会替换选区内容', () => {
    const chatInput = ref('hello world')
    const bridge = useComposerContextBridge({ chatInput })

    bridge.handleComposerSelectionChange({ start: 6, end: 11, focused: true })
    bridge.handleContextPush({} as any)

    expect(chatInput.value).toBe('hello [[CTX_PREVIEW]]\nCTX_FULL')
  })
})
