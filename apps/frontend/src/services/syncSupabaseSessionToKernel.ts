/**
 * Push Supabase session to the local Python kernel (for Edge-backed tools e.g. image search).
 * Failures are non-fatal; callers should log only.
 */
import { logger } from '@/utils/logger'
import { buildBackendUrl } from '@/utils/backendUrl'

export type KernelSupabaseSessionPayload = {
  access_token: string
  refresh_token: string
  expires_at?: number | null
  supabase_user_id?: string | null
}

export const syncSupabaseSessionToKernel = async (
  payload: KernelSupabaseSessionPayload
): Promise<void> => {
  const access = String(payload.access_token || '').trim()
  if (!access) {
    return
  }
  const url = buildBackendUrl('/api/supabase-session')
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        access_token: access,
        refresh_token: String(payload.refresh_token || ''),
        expires_at: payload.expires_at ?? undefined,
        supabase_user_id: payload.supabase_user_id ?? undefined
      })
    })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      logger.warn('[syncSupabaseSessionToKernel] POST failed', {
        status: res.status,
        body: text.slice(0, 200)
      })
    }
  } catch (err) {
    logger.warn('[syncSupabaseSessionToKernel] request error', err)
  }
}

export const clearSupabaseSessionOnKernel = async (): Promise<void> => {
  const url = buildBackendUrl('/api/supabase-session')
  try {
    const res = await fetch(url, { method: 'DELETE' })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      logger.warn('[clearSupabaseSessionOnKernel] DELETE failed', {
        status: res.status,
        body: text.slice(0, 200)
      })
    }
  } catch (err) {
    logger.warn('[clearSupabaseSessionOnKernel] request error', err)
  }
}
