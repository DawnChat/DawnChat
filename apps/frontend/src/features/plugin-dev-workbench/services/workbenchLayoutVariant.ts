export type WorkbenchLayoutVariant =
  | 'split_with_iwp'
  | 'split_no_iwp'
  | 'agent_preview'
  | 'compact'

interface ResolveWorkbenchLayoutVariantInput {
  isAssistantCompactSurface: boolean
  isAgentPreviewLayout: boolean
  hasIwpRequirements: boolean
}

export const resolveWorkbenchLayoutVariant = (
  input: ResolveWorkbenchLayoutVariantInput
): WorkbenchLayoutVariant => {
  if (input.isAssistantCompactSurface) {
    return 'compact'
  }
  if (input.isAgentPreviewLayout) {
    return 'agent_preview'
  }
  if (input.hasIwpRequirements) {
    return 'split_with_iwp'
  }
  return 'split_no_iwp'
}
