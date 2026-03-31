import type { RouteLocationRaw } from 'vue-router'
import { APPS_HUB_PATH } from './paths'
import { isSafeRedirectPath } from '@/shared/auth/redirect'

const toHashRoute = (path: string): string => {
  if (!path.startsWith('/')) {
    return `/${path}`
  }
  return path
}

export type DeepLinkParseStatus = 'valid' | 'invalid' | 'unsupported'

export interface DeepLinkParseResult {
  status: DeepLinkParseStatus
  route: RouteLocationRaw | null
  reason?: string
}

const extractRedirectFromHash = (hash: string): string | null => {
  if (!hash.startsWith('#/')) {
    return null
  }
  const raw = hash.slice(1)
  const queryStart = raw.indexOf('?')
  if (queryStart < 0) {
    return null
  }
  const params = new URLSearchParams(raw.slice(queryStart + 1))
  const redirect = params.get('redirect')
  if (!redirect) {
    return null
  }
  return isSafeRedirectPath(redirect) ? redirect : null
}

export const resolveFullscreenBackTarget = (
  value: unknown,
  fallback = APPS_HUB_PATH
): string => {
  if (typeof value !== 'string') {
    return fallback
  }
  return isSafeRedirectPath(value) ? value : fallback
}

export const parseDeepLink = (url: string): DeepLinkParseResult => {
  try {
    const parsed = new URL(url)
    if (parsed.protocol !== 'dawnchat:') {
      return {
        status: 'unsupported',
        route: null,
        reason: 'unsupported_protocol'
      }
    }

    const host = parsed.hostname
    const segments = parsed.pathname.split('/').filter(Boolean)

    if (host === 'apps' && segments.length > 0) {
      return {
        status: 'valid',
        route: { name: 'plugin-fullscreen', params: { pluginId: segments[0] } }
      }
    }

    if (host === 'pipeline' && segments.length > 0 && segments[0].startsWith('task_')) {
      return {
        status: 'valid',
        route: { name: 'pipeline-task-detail', params: { taskId: segments[0] } }
      }
    }

    if (host === 'workbench' && segments.length > 0) {
      return {
        status: 'valid',
        route: { name: 'workbench-room', params: { roomId: segments[0] } }
      }
    }

    return {
      status: 'unsupported',
      route: null,
      reason: 'unsupported_target'
    }
  } catch {
    return {
      status: 'invalid',
      route: null,
      reason: 'invalid_url'
    }
  }
}

export const normalizeAuthCallbackHash = (): boolean => {
  if (window.location.pathname !== '/auth/callback') {
    return false
  }
  if (window.location.hash.startsWith('#/auth/callback')) {
    return false
  }

  const current = new URL(window.location.href)
  const recoveredRedirect = extractRedirectFromHash(window.location.hash)
  if (recoveredRedirect && !current.searchParams.get('redirect')) {
    current.searchParams.set('redirect', recoveredRedirect)
  }
  const search = current.searchParams.toString()
  const target = `/#${toHashRoute('/auth/callback')}${search ? `?${search}` : ''}`
  window.location.replace(target)
  return true
}
