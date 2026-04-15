/** 用户在设置侧栏再次点击当前已选中的 section 时派发（Vue Router 同路径 push 不会重挂载子视图） */
export const SETTINGS_SECTION_RESELECTED = 'dawnchat-settings-section-reselected' as const

export type SettingsSectionReselectedDetail = { section: string }
