const serializeUnknownError = (error: unknown) => {
  if (error instanceof Error) {
    return {
      name: error.name,
      message: error.message,
      stack: error.stack
    }
  }

  if (typeof error === 'object' && error !== null) {
    try {
      return JSON.parse(JSON.stringify(error))
    } catch {
      return String(error)
    }
  }

  return error
}

const writeBootstrapLog = (event: string, data?: unknown) => {
  const timestamp = new Date().toISOString()
  let line = `[${timestamp}] [BOOTSTRAP] ${event}`
  if (data !== undefined) {
    try {
      line += `\n${JSON.stringify(data, null, 2)}`
    } catch {
      line += `\n${String(data)}`
    }
  }

  console.info(line)

  const invoke = (window as any).__TAURI_INTERNALS__?.invoke
  if (typeof invoke === 'function') {
    void invoke('append_frontend_log', { line }).catch((error: unknown) => {
      console.error('[bootstrap] append_frontend_log failed')
      console.error(error)
    })
  }
}

window.addEventListener('error', (event) => {
  writeBootstrapLog('window_error', {
    message: event.message,
    filename: event.filename,
    lineno: event.lineno,
    colno: event.colno,
    error: serializeUnknownError(event.error)
  })
})

window.addEventListener('unhandledrejection', (event) => {
  writeBootstrapLog('window_unhandledrejection', {
    reason: serializeUnknownError(event.reason)
  })
})

void (async () => {
  writeBootstrapLog('frontend_bootstrap_loaded', {
    href: typeof window.location?.href === 'string' ? window.location.href : undefined,
    tauri: '__TAURI_INTERNALS__' in window
  })

  const { startApp } = await import('./main-app')
  writeBootstrapLog('main_app_import_succeeded')
  await startApp()
})().catch((error) => {
  writeBootstrapLog('main_app_import_or_start_failed', {
    error: serializeUnknownError(error)
  })
})
