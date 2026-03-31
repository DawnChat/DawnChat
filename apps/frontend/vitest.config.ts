import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'happy-dom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // 测试文件包含模式
    include: [
      'src/**/*.{test,spec}.{ts,js}',
      'src/**/__tests__/**/*.{test,spec}.{ts,js}',
    ],
    // 测试超时配置
    testTimeout: 10000,
    hookTimeout: 10000,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      // 覆盖率包含的文件
      include: [
        'src/stores/**/*.ts',
        'src/services/**/*.ts',
        'src/components/**/*.vue',
        'src/composables/**/*.ts',
        'src/types/**/*.ts',
      ],
      // 排除的文件
      exclude: [
        'node_modules/',
        'src/test/**',
        '**/*.d.ts',
        '**/*.config.*',
        '**/mockData.ts',
        '**/*.test.{ts,js}',
        '**/*.spec.{ts,js}',
        '**/__tests__/**',
        '**/__examples__/**',
      ],
      // 覆盖率阈值（当 V2 代码实现后启用）
      // 注释掉直到 Phase 5e 完成
      // thresholds: {
      //   statements: 70,
      //   branches: 70,
      //   functions: 70,
      //   lines: 70,
      // },
    },
  },
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
})
