import { describe, expect, it } from 'vitest'
import { resolveWorkbenchLayoutVariant } from '@/features/plugin-dev-workbench/services/workbenchLayoutVariant'

describe('workbenchLayoutVariant', () => {
  it('assistant_compact 优先级最高', () => {
    const variant = resolveWorkbenchLayoutVariant({
      isAssistantCompactSurface: true,
      isAgentPreviewLayout: true,
      hasIwpRequirements: true,
    })
    expect(variant).toBe('compact')
  })

  it('agent_preview 次高优先级', () => {
    const variant = resolveWorkbenchLayoutVariant({
      isAssistantCompactSurface: false,
      isAgentPreviewLayout: true,
      hasIwpRequirements: true,
    })
    expect(variant).toBe('agent_preview')
  })

  it('普通分栏根据 IWP 能力切分', () => {
    const withIwp = resolveWorkbenchLayoutVariant({
      isAssistantCompactSurface: false,
      isAgentPreviewLayout: false,
      hasIwpRequirements: true,
    })
    const withoutIwp = resolveWorkbenchLayoutVariant({
      isAssistantCompactSurface: false,
      isAgentPreviewLayout: false,
      hasIwpRequirements: false,
    })
    expect(withIwp).toBe('split_with_iwp')
    expect(withoutIwp).toBe('split_no_iwp')
  })
})
