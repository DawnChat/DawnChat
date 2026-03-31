export type SpaceType =
  | 'workbench'
  | 'mindcore'
  | 'agents'
  | 'workflows'
  | 'tools'
  | 'models'
  | 'apps'
  | 'settings'
  | 'pipeline'

export type ThemeMode = 'light' | 'dark'
export type Locale = 'zh' | 'en'

export interface NavigationItem {
  id: string
  icon: any
  label: string
}
