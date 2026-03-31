import { describe, expect, it } from 'vitest'
import { getWorkbenchLayoutProfile } from '@/features/plugin-dev-workbench/services/workbenchLayoutProfile'

describe('workbenchLayoutProfile', () => {
  it('default profile 保持三段式能力', () => {
    const profile = getWorkbenchLayoutProfile('default')
    expect(profile.isAgentPreview).toBe(false)
    expect(profile.showFileTree).toBe(true)
    expect(profile.showModeSwitch).toBe(true)
    expect(profile.allowRequirementsMode).toBe(true)
    expect(profile.loadIwpFilesOnMount).toBe(true)
    expect(profile.lockLayoutPersistence).toBe(false)
    expect(profile.previewResizeMode).toBe('preview_width')
  })

  it('agent_preview profile 收敛为双栏能力', () => {
    const profile = getWorkbenchLayoutProfile('agent_preview')
    expect(profile.isAgentPreview).toBe(true)
    expect(profile.showFileTree).toBe(false)
    expect(profile.showModeSwitch).toBe(false)
    expect(profile.allowRequirementsMode).toBe(false)
    expect(profile.loadIwpFilesOnMount).toBe(false)
    expect(profile.lockLayoutPersistence).toBe(true)
    expect(profile.previewResizeMode).toBe('agent_width_capped')
  })
})

