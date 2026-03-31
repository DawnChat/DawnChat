import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  
  // 路径别名配置（与 vitest.config.ts 保持一致）
  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
      '@test': resolve(__dirname, './src/test'),
      '@mocks': resolve(__dirname, './src/test/mocks'),
      '@fixtures': resolve(__dirname, './src/test/mocks/fixtures'),
      '@utils': resolve(__dirname, './src/test/utils'),
      '@dawnchat/auth-bridge': resolve(__dirname, '../../dawnchat-plugins/auth-bridge/src'),
    },
  },
  
  // 开发服务器配置
  server: {
    port: 5173,
    host: true,
    // 代理 API 请求到 Python 后端
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true
      }
    }
  },
  
  build: {
    rollupOptions: {
      external: [
        '@tauri-apps/plugin-shell',
        '@tauri-apps/plugin-deep-link'
      ]
    }
  }
})
