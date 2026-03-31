import type { RouteRecordRaw } from 'vue-router'
import type { SpaceType } from '@/shared/types/common'

import AppShellLayout from '@/app/layouts/AppShellLayout.vue'
import FullscreenLayout from '@/app/layouts/FullscreenLayout.vue'
import LoginView from '@/views/LoginView.vue'
import AuthCallback from '@/views/AuthCallback.vue'
import { APPS_HUB_PATH } from '@/app/router/paths'

export interface AppRouteMeta extends Record<string, unknown> {
  [key: symbol]: unknown
  requiresAuth?: boolean
  layout?: 'app' | 'fullscreen' | 'public'
  space?: SpaceType
  section?: string
  navigatorTitleKey?: string
  trackEvent?: string
  feature?: string
  pageType?: 'page' | 'detail' | 'fullscreen'
  entityType?: 'plugin' | 'task' | 'room' | 'workflow' | 'none'
  entityIdParam?: string
  fullscreen?: boolean
  projectSettings?: boolean
}

const appRoute = (
  path: string,
  name: string,
  meta: AppRouteMeta
): RouteRecordRaw => ({
  path,
  name,
  component: AppShellLayout,
  meta: {
    requiresAuth: true,
    layout: 'app',
    pageType: 'page',
    entityType: 'none',
    ...meta
  }
})

export const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: LoginView,
    meta: {
      requiresAuth: false,
      layout: 'public',
      trackEvent: 'page_login',
      feature: 'auth',
      pageType: 'page',
      entityType: 'none'
    } as AppRouteMeta
  },
  {
    path: '/auth/callback',
    name: 'auth-callback',
    component: AuthCallback,
    meta: {
      requiresAuth: false,
      layout: 'public',
      trackEvent: 'page_auth_callback',
      feature: 'auth',
      pageType: 'page',
      entityType: 'none'
    } as AppRouteMeta
  },
  {
    path: '/app',
    redirect: APPS_HUB_PATH
  },
  appRoute('/app/workbench', 'workbench', {
    space: 'workbench',
    navigatorTitleKey: 'nav.workbench',
    trackEvent: 'page_workbench',
    feature: 'workbench'
  }),
  appRoute('/app/workbench/:roomId', 'workbench-room', {
    space: 'workbench',
    navigatorTitleKey: 'nav.workbench',
    trackEvent: 'page_workbench_room',
    feature: 'workbench',
    pageType: 'detail',
    entityType: 'room',
    entityIdParam: 'roomId'
  }),
  appRoute('/app/workbench/project-settings/:roomId?', 'project-settings', {
    space: 'workbench',
    navigatorTitleKey: 'nav.workbench',
    projectSettings: true,
    trackEvent: 'page_project_settings',
    feature: 'workbench'
  }),
  appRoute('/app/apps/:section(hub|market|installed)?', 'apps', {
    space: 'apps',
    section: 'hub',
    navigatorTitleKey: 'nav.apps',
    trackEvent: 'page_apps',
    feature: 'apps'
  }),
  appRoute('/app/settings/:section(general|cloud-models|network|about)?', 'settings', {
    space: 'settings',
    section: 'general',
    navigatorTitleKey: 'nav.settings',
    trackEvent: 'page_settings',
    feature: 'settings'
  }),
  {
    path: '/fullscreen',
    component: FullscreenLayout,
    meta: {
      requiresAuth: true,
      layout: 'fullscreen'
    } as AppRouteMeta,
    children: [
      {
        path: 'plugin/:pluginId',
        name: 'plugin-fullscreen',
        component: () => import('@/features/plugin-runtime/views/PluginRuntimeFullscreenPage.vue'),
        meta: {
          requiresAuth: true,
          layout: 'fullscreen',
          fullscreen: true,
          trackEvent: 'plugin_fullscreen_enter',
          feature: 'apps',
          pageType: 'fullscreen',
          entityType: 'plugin',
          entityIdParam: 'pluginId'
        } as AppRouteMeta
      },
      {
        path: 'plugin-dev/:pluginId',
        name: 'plugin-dev-workbench',
        component: () => import('@/features/plugin-dev-workbench/views/PluginDevWorkbenchPage.vue'),
        meta: {
          requiresAuth: true,
          layout: 'fullscreen',
          fullscreen: true,
          trackEvent: 'plugin_dev_workbench_enter',
          feature: 'apps',
          pageType: 'fullscreen',
          entityType: 'plugin',
          entityIdParam: 'pluginId'
        } as AppRouteMeta
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: APPS_HUB_PATH
  }
]
