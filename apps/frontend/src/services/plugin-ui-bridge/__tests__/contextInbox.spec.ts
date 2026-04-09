import { describe, expect, it } from 'vitest'
import {
  contextPayloadToComposerText,
  contextPayloadToComposerToken
} from '@dawnchat/host-orchestration-sdk/assistant-client'

describe('contextPayloadToComposerText', () => {
  it('会优先拼接 metadata.preview，再拼接 text/image 项', () => {
    const text = contextPayloadToComposerText({
      metadata: { preview: 'App.vue(L18:C7)' },
      items: [
        { type: 'text', text: '请修改这个按钮文案' },
        { type: 'image', uri: 'file:///tmp/a.png' }
      ]
    })
    expect(text).toBe('App.vue(L18:C7)\n请修改这个按钮文案\n![image](file:///tmp/a.png)')
  })

  it('忽略空 uri 的 image 与空内容', () => {
    const text = contextPayloadToComposerText({
      items: [
        { type: 'text', text: '' },
        { type: 'image', uri: '   ' }
      ]
    })
    expect(text).toBe('')
  })

  it('可生成 preview + fullText token 数据', () => {
    const token = contextPayloadToComposerToken({
      metadata: { preview: 'App.vue(L18:C7)' },
      items: [{ type: 'text', text: '请修改按钮文案' }]
    })
    expect(token?.preview).toBe('App.vue(L18:C7)')
    expect(token?.fullText).toContain('请修改按钮文案')
  })
})
