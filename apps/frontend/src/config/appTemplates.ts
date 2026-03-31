export type CreateAppType = 'desktop' | 'web' | 'mobile'
export type AppTemplateDescriptionKey =
  | 'desktopTemplateDescription'
  | 'desktopHelloWorldTemplateDescription'
  | 'desktopAssistantTemplateDescription'
  | 'webTemplateDescription'
  | 'mobileTemplateDescription'

export interface AppTemplateCatalogItem {
  appType: CreateAppType
  templateId: string
  templateName: string
  stack: string
  descriptionKey: AppTemplateDescriptionKey
}

export interface DesktopQuickTemplateOption {
  templateId: string
  nameKey: 'desktopTemplateHelloWorldName' | 'desktopTemplateAssistantName'
  templateName: string
  stack: string
  descriptionKey: AppTemplateDescriptionKey
}

export const DESKTOP_QUICK_TEMPLATE_OPTIONS: DesktopQuickTemplateOption[] = [
  {
    templateId: 'com.dawnchat.desktop-hello-world',
    nameKey: 'desktopTemplateHelloWorldName',
    templateName: 'desktop-hello-world',
    stack: 'Vue + Bun',
    descriptionKey: 'desktopHelloWorldTemplateDescription'
  },
  {
    templateId: 'com.dawnchat.desktop-ai-assistant',
    nameKey: 'desktopTemplateAssistantName',
    templateName: 'desktop-ai-assistant',
    stack: 'Vue + Bun',
    descriptionKey: 'desktopAssistantTemplateDescription'
  }
]

export const APP_TEMPLATE_CATALOG: Record<CreateAppType, AppTemplateCatalogItem> = {
  desktop: {
    appType: 'desktop',
    templateId: 'com.dawnchat.desktop-starter',
    templateName: 'desktop-starter',
    stack: 'Vue + Bun',
    descriptionKey: 'desktopTemplateDescription'
  },
  web: {
    appType: 'web',
    templateId: 'com.dawnchat.web-starter-vue',
    templateName: 'web-starter-vue',
    stack: 'Vue 3 + TypeScript + Vite',
    descriptionKey: 'webTemplateDescription'
  },
  mobile: {
    appType: 'mobile',
    templateId: 'com.dawnchat.mobile-starter-ionic',
    templateName: 'mobile-starter-ionic',
    stack: 'Ionic Vue + Capacitor + Vite',
    descriptionKey: 'mobileTemplateDescription'
  }
}

export function getAppTemplateCatalog(appType: CreateAppType): AppTemplateCatalogItem {
  return APP_TEMPLATE_CATALOG[appType]
}
