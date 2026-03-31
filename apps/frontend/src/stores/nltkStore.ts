import { defineStore } from 'pinia'
import { ref } from 'vue'
import { logger } from '@/utils/logger'
import { buildBackendUrl } from '@/utils/backendUrl'

export interface NLTKResource {
  id: string
  name: string
  description: string
  installed: boolean
  downloading?: boolean
}

export interface NLTKStatus {
  installed: boolean
  resources: NLTKResource[]
  data_dir: string
}

export const useNLTKStore = defineStore('nltk', () => {
  const API_BASE = () => buildBackendUrl('/api')
  
  const status = ref<NLTKStatus>({
    installed: false,
    resources: [],
    data_dir: ''
  })
  
  const loading = ref(false)
  const downloading = ref<Record<string, boolean>>({})

  async function checkStatus() {
    try {
      loading.value = true
      const response = await fetch(`${API_BASE()}/tools/nltk/status`)
      const data = await response.json()
      status.value = data
    } catch (error) {
      logger.error('Failed to check NLTK status:', error)
    } finally {
      loading.value = false
    }
  }

  async function downloadResource(resourceId: string) {
    if (downloading.value[resourceId]) return
    
    try {
      downloading.value[resourceId] = true
      // 更新本地状态显示为下载中
      const resource = status.value.resources.find(r => r.id === resourceId)
      if (resource) resource.downloading = true
      
      const response = await fetch(`${API_BASE()}/tools/nltk/download/${resourceId}`, {
        method: 'POST'
      })
      
      if (!response.ok) {
        throw new Error(`Download failed: ${response.statusText}`)
      }
      
      // 下载完成后刷新状态
      await checkStatus()
    } catch (error) {
      logger.error(`Failed to download NLTK resource ${resourceId}:`, error)
    } finally {
      downloading.value[resourceId] = false
      const resource = status.value.resources.find(r => r.id === resourceId)
      if (resource) resource.downloading = false
    }
  }

  return {
    status,
    loading,
    downloading,
    checkStatus,
    downloadResource
  }
})
