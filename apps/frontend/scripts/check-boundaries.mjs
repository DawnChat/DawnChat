import fs from 'node:fs'
import path from 'node:path'

const root = process.cwd()
const srcDir = path.join(root, 'src')
const featuresDir = path.join(srcDir, 'features')
const importRegex = /from\s+['"]([^'"]+)['"]|import\(\s*['"]([^'"]+)['"]\s*\)/g
const strictFeatures = new Set([
  'workbench',
  'coding-agent',
  'plugin',
  'settings',
  'environment',
  'auth'
])
const legacyImportPrefixes = [
  '@/views/',
  '@/components/apps/',
  '@/stores/',
  '@/composables/',
  '@/layouts/',
  '@/router/'
]
const allowedLegacyImports = {
  workbench: [
    '@/stores/workbenchProjectsStore',
    '@/stores/workbenchProjectsApi',
    '@/composables/useI18n'
  ],
  'coding-agent': [
    '@/stores/workbenchProjectsApi',
    '@/composables/useI18n',
    '@/composables/useEngineHealth'
  ],
  plugin: [
    '@/stores/plugin',
    '@/stores/plugin/types',
    '@/composables/useI18n',
    '@/composables/useTheme',
    '@/composables/useAppsView',
    '@/composables/usePluginUiBridge'
  ],
  settings: [
    '@/stores/llmSelectionStore',
    '@/composables/useI18n',
    '@/composables/useTheme'
  ],
  environment: [
    '@/stores/modelHubStore',
    '@/stores/llmSelectionStore',
    '@/stores/toolsStore',
    '@/stores/imageGenStore',
    '@/stores/scoringStore',
    '@/stores/nltkStore',
    '@/composables/useResourceAccessMirror',
    '@/composables/useI18n'
  ]
}

function walk(dir, files = []) {
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name)
    const stat = fs.statSync(full)
    if (stat.isDirectory()) {
      walk(full, files)
      continue
    }
    if (full.endsWith('.ts') || full.endsWith('.vue')) {
      files.push(full)
    }
  }
  return files
}

function toFeatureName(filePath) {
  const rel = path.relative(featuresDir, filePath).replace(/\\/g, '/')
  return rel.split('/')[0] || ''
}

function isAllowedCrossFeatureImport(source, targetFeature) {
  return (
    source === `@/features/${targetFeature}` ||
    source === `@/features/${targetFeature}/index` ||
    source === `@/features/${targetFeature}/types` ||
    source.startsWith('@/shared/')
  )
}

const errors = []
const files = walk(featuresDir)

for (const file of files) {
  const ownerFeature = toFeatureName(file)
  const content = fs.readFileSync(file, 'utf8')
  importRegex.lastIndex = 0
  let match
  while ((match = importRegex.exec(content))) {
    const source = match[1] || match[2] || ''
    const isLegacyImport = legacyImportPrefixes.some((prefix) => source.startsWith(prefix))
    if (strictFeatures.has(ownerFeature) && isLegacyImport) {
      const allowed = (allowedLegacyImports[ownerFeature] || []).some(
        (allowedSource) => source === allowedSource || source.startsWith(`${allowedSource}/`)
      )
      if (allowed) {
        continue
      }
      const relFile = path.relative(root, file)
      errors.push(`${relFile}: ${ownerFeature} 不允许引用 legacy 目录 -> ${source}`)
      continue
    }
    if (!source.startsWith('@/features/')) {
      continue
    }
    const targetFeature = source.replace('@/features/', '').split('/')[0]
    if (!targetFeature || targetFeature === ownerFeature) {
      continue
    }
    if (!isAllowedCrossFeatureImport(source, targetFeature)) {
      const relFile = path.relative(root, file)
      errors.push(`${relFile}: 不允许跨 feature 直接引用内部模块 -> ${source}`)
    }
  }
}

if (errors.length > 0) {
  console.error('Feature boundary check failed:\n')
  for (const line of errors) {
    console.error(`- ${line}`)
  }
  process.exit(1)
}

console.log('Feature boundary check passed.')
