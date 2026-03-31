import type { Plugin } from '@/types'
import type { EnvironmentRequirements, RequirementLevel } from '@/types/environment'

export function parseEnvironmentRequirements(app: Plugin): EnvironmentRequirements {
  const requirements: EnvironmentRequirements = {}

  const manifest = app.manifest
  if (!manifest?.requires) {
    return requirements
  }

  const requires = manifest.requires
  const parseLevel = (value: boolean | { level?: string }): RequirementLevel => {
    if (typeof value === 'boolean') {
      return value ? 'required' : false
    }
    const level = value.level
    if (level === 'required' || level === 'optional' || level === 'local_only' || level === 'cloud_only') {
      return level
    }
    return 'required'
  }

  if (requires.ai) {
    requirements.ai = parseLevel(requires.ai)
  }
  if (requires.local_ai) {
    requirements.local_ai = parseLevel(requires.local_ai)
  }
  if (requires.cloud_ai) {
    requirements.cloud_ai = parseLevel(requires.cloud_ai)
  }
  if (requires.tts) {
    requirements.tts = parseLevel(requires.tts)
  }
  if (requires.asr) {
    requirements.asr = parseLevel(requires.asr)
  }
  if (requires.ffmpeg) {
    requirements.ffmpeg = parseLevel(requires.ffmpeg)
  }

  return requirements
}
