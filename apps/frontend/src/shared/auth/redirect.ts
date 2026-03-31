import { APPS_HUB_PATH } from '@/app/router/paths'

export const DEFAULT_AUTH_ROUTE = APPS_HUB_PATH

export const isSafeRedirectPath = (value: unknown): value is string => {
  if (typeof value !== 'string') {
    return false
  }
  if (!value.startsWith('/') || value.startsWith('//')) {
    return false
  }
  return /^\/(app|fullscreen)(\/|$)/.test(value)
}

export const resolveSafeRedirectPath = (
  value: unknown,
  fallback: string = DEFAULT_AUTH_ROUTE
): string => {
  if (Array.isArray(value)) {
    return isSafeRedirectPath(value[0]) ? value[0] : fallback
  }
  return isSafeRedirectPath(value) ? value : fallback
}
