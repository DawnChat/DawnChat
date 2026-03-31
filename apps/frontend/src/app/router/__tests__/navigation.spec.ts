import { describe, it, expect, vi } from 'vitest'
import type { Router } from 'vue-router'
import { goToSection, goToSpace, openPluginFullscreen } from '../navigation'

const createRouterMock = () => {
  const push = vi.fn()
  return {
    push
  } as unknown as Router & { push: ReturnType<typeof vi.fn> }
}

describe('router navigation helpers', () => {
  it('navigates to workbench room by route name', async () => {
    const router = createRouterMock()
    await goToSpace(router, 'workbench', undefined, 'room_1')

    expect(router.push).toHaveBeenCalledWith({
      name: 'workbench-room',
      params: { roomId: 'room_1' }
    })
  })

  it('navigates pipeline dashboard fallback to workbench route', async () => {
    const router = createRouterMock()
    await goToSection(router, 'pipeline', 'dashboard')
    expect(router.push).toHaveBeenCalledWith({ name: 'workbench' })
  })

  it('opens plugin fullscreen with from query', async () => {
    const router = createRouterMock()
    await openPluginFullscreen(router, 'plugin-a', '/app/apps/market')

    expect(router.push).toHaveBeenCalledWith({
      name: 'plugin-fullscreen',
      params: { pluginId: 'plugin-a' },
      query: { from: '/app/apps/market', mode: 'normal' }
    })
  })
})
