import { defineAsyncComponent } from 'vue'
import type { Component } from 'vue'
import type { SpaceType } from '@/shared/types/common'

import { WorkbenchView } from '@/features/workbench'
import { SettingsView } from '@/features/settings'
const AppsView = defineAsyncComponent(() => import('@/features/plugin/views/AppsView.vue'))

import WorkbenchNavigator from '@/app/navigators/WorkbenchNavigator.vue'
import AppsNavigator from '@/app/navigators/AppsNavigator.vue'
import SettingsNavigator from '@/app/navigators/SettingsNavigator.vue'

export interface SpaceManifestItem {
  defaultSection: string
  titleKey: string
  navigatorComponent: Component
  viewComponent: Component
}

const workbenchManifest: SpaceManifestItem = {
  defaultSection: 'new',
  titleKey: 'nav.workbench',
  navigatorComponent: WorkbenchNavigator,
  viewComponent: WorkbenchView
}

export const spaceManifest: Record<SpaceType, SpaceManifestItem> = {
  workbench: workbenchManifest,
  mindcore: workbenchManifest,
  agents: workbenchManifest,
  workflows: workbenchManifest,
  pipeline: workbenchManifest,
  tools: workbenchManifest,
  models: workbenchManifest,
  apps: {
    defaultSection: 'hub',
    titleKey: 'nav.apps',
    navigatorComponent: AppsNavigator,
    viewComponent: AppsView
  },
  settings: {
    defaultSection: 'general',
    titleKey: 'nav.settings',
    navigatorComponent: SettingsNavigator,
    viewComponent: SettingsView
  }
}

export const getSpaceManifest = (space: SpaceType): SpaceManifestItem => {
  return spaceManifest[space] || workbenchManifest
}

export const getSpaceDefaultSection = (space: SpaceType): string => {
  return (spaceManifest[space] || workbenchManifest).defaultSection
}
