import { isTauri } from '../adapters/env'
import { listen } from '../adapters/events'

const defaultUrl =
  (import.meta as any).env?.VITE_API_BASE_URL ||
  (typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1')
let backendUrl = String(defaultUrl).replace(/\/$/, '')

export const setBackendUrl = (url: string) => {
  if (!url) return
  backendUrl = url.replace(/\/$/, '')
}

export const getBackendUrl = (): string => backendUrl

export const buildBackendUrl = (path: string): string => {
  const base = getBackendUrl()
  if (!path) return base
  if (path.startsWith('http://') || path.startsWith('https://')) return path
  if (path.startsWith('/')) return `${base}${path}`
  return `${base}/${path}`
}

export const getBackendWsUrl = (): string => {
  const url = new URL(getBackendUrl())
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${url.toString().replace(/\/$/, '')}/ws/zmp`
}

export const initBackendUrl = async () => {
  if (!isTauri()) return
  const invoke = (window as any).__TAURI_INTERNALS__?.invoke
  if (typeof invoke === 'function') {
    try {
      const url = await invoke('get_backend_url')
      setBackendUrl(String(url))
    } catch {
    }
  }
  await listen<string>('backend-url-updated', (event) => {
    setBackendUrl(String(event.payload))
  })
}
