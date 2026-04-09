export type CreateAppType = 'desktop' | 'web' | 'mobile'
export type CreateAssistantPlatformType = 'desktop' | 'web'
export type AppTemplateDescriptionKey =
  | 'desktopTemplateDescription'
  | 'webTemplateDescription'
  | 'mobileTemplateDescription'

export interface AppTemplateCatalogItem {
  appType: CreateAppType
  templateId: string
  templateName: string
  stack: string
  descriptionKey: AppTemplateDescriptionKey
}

export const DESKTOP_AI_ASSISTANT_TEMPLATE_ID = 'com.dawnchat.desktop-ai-assistant'
export const WEB_AI_ASSISTANT_TEMPLATE_ID = 'com.dawnchat.web-ai-assistant'
export const AI_ASSISTANT_TEMPLATE_ID = DESKTOP_AI_ASSISTANT_TEMPLATE_ID
export const MAIN_AI_ASSISTANT_ID_SUFFIX = 'dawnchat-ai-assistant'

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

export const ASSISTANT_TEMPLATE_CATALOG: Record<CreateAssistantPlatformType, AppTemplateCatalogItem> = {
  desktop: {
    appType: 'desktop',
    templateId: DESKTOP_AI_ASSISTANT_TEMPLATE_ID,
    templateName: 'desktop-ai-assistant',
    stack: 'Vue + Bun + Python Runtime',
    descriptionKey: 'desktopTemplateDescription'
  },
  web: {
    appType: 'web',
    templateId: WEB_AI_ASSISTANT_TEMPLATE_ID,
    templateName: 'web-ai-assistant',
    stack: 'Vue 3 + TypeScript + Vite',
    descriptionKey: 'webTemplateDescription'
  }
}

export function getAssistantTemplateCatalog(appType: CreateAssistantPlatformType): AppTemplateCatalogItem {
  return ASSISTANT_TEMPLATE_CATALOG[appType]
}
