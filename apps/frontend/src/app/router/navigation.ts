import type { Router, RouteLocationRaw } from 'vue-router'
import type { SpaceType } from '@/shared/types/common'
import { getSpaceDefaultSection } from './manifest'
import { APPS_HUB_PATH } from './paths'
import { openPluginRuntimeSurface } from './pluginSurfaceNavigation'

const buildSpaceLocation = (
  space: SpaceType,
  section?: string,
  roomId?: string | null
): RouteLocationRaw => {
  const targetSection = section || getSpaceDefaultSection(space)

  if (space === 'workbench') {
    if (roomId) {
      return { name: 'workbench-room', params: { roomId } }
    }
    return { name: 'workbench' }
  }

  if (space === 'apps') {
    return { name: 'apps', params: { section: targetSection } }
  }

  if (space === 'settings') {
    return { name: 'settings', params: { section: targetSection } }
  }

  return { name: 'workbench' }
}

export const goToSpace = async (
  router: Router,
  space: SpaceType,
  section?: string,
  roomId?: string | null
) => {
  await router.push(buildSpaceLocation(space, section, roomId))
}

export const goToSection = async (
  router: Router,
  space: SpaceType,
  section: string,
  roomId?: string | null
) => {
  await router.push(buildSpaceLocation(space, section, roomId))
}

export const openPluginFullscreen = async (
  router: Router,
  pluginId: string,
  from = APPS_HUB_PATH,
  mode: 'normal' | 'preview' = 'normal'
) => {
  await openPluginRuntimeSurface(router, pluginId, from, mode)
}

export const openPluginDevWorkbench = async (
  router: Router,
  pluginId: string,
  from = APPS_HUB_PATH,
  surface: 'dev_split' | 'assistant_compact' = 'dev_split'
) => {
  await router.push({
    name: 'plugin-dev-workbench',
    params: { pluginId },
    query: surface === 'assistant_compact' ? { from, surface } : { from }
  })
}
