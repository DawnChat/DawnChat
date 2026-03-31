import { describe, expect, it } from 'vitest'
import { encodeContextToken, expandContextTokens, parseContextTokens } from '../contextToken'

describe('contextToken', () => {
  it('encode + expand 可还原 preview 与 fullText', () => {
    const token = encodeContextToken('App.vue(L18:C7)', 'App.vue(L18:C7)\n请修改按钮文案')
    const expanded = expandContextTokens(`before ${token} after`)
    expect(expanded).toContain('App.vue(L18:C7)')
    expect(expanded).toContain('请修改按钮文案')
  })

  it('parse 可识别 token 与普通文本段', () => {
    const token = encodeContextToken('A', 'B')
    const segments = parseContextTokens(`x${token}y`)
    expect(segments.length).toBe(3)
    expect(segments[1].type).toBe('token')
    if (segments[1].type === 'token') {
      expect(segments[1].data.preview).toBe('A')
      expect(segments[1].data.fullText).toBe('B')
    }
  })
})
