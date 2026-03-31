# DawnChat Frontend

基于 Vue 3 + TypeScript + Vite 构建的前端应用，作为 DawnChat 项目的用户界面层。

## 技术栈

- **框架**: Vue 3.6 + TypeScript 5.9
- **构建工具**: Vite 7.1
- **状态管理**: Vue Composition API + Pinia (如需)
- **HTTP 客户端**: fetch/axios
- **UI 组件**: 原生 Vue 组件（轻量级设计）

## Python 环境配置

项目使用统一的 Python 环境配置：
- **Python 解释器**: `/Users/zhutao/Library/Python/3.10/bin/python3` (用户目录安装)
- **Poetry 工具**: `/Users/zhutao/Library/Python/3.10/bin/poetry` (用户目录安装)
- **依赖管理**: 使用 Poetry 管理后端依赖

## 开发指南

### 快速开始

```bash
# 安装依赖
pnpm install

# 启动开发服务器
pnpm run dev

# 构建生产版本
pnpm run build

# 运行类型检查
pnpm run type-check
```

### 开发规范

- 使用 Composition API (`<script setup>`)
- Props 必须有类型定义和默认值
- Emits 必须显式声明
- 使用 `ref` 和 `reactive` 管理响应式状态

### API 调用规范

```typescript
// 统一封装 API 调用
const fetchData = async () => {
  try {
    const response = await fetch(`${API_BASE}/endpoint`)
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
    const data = await response.json()
    // 处理数据
  } catch (error) {
    console.error('Failed to fetch:', error)
    // 用户友好的错误提示
  }
}
```

### 用户交互规范

**禁止使用浏览器原生弹窗**：
- ❌ 不要使用 `window.confirm()`
- ❌ 不要使用 `window.alert()`
- ❌ 不要使用 `window.prompt()`

**必须使用自定义组件**：
```vue
<script setup lang="ts">
import ConfirmDialog from '@/components/ConfirmDialog.vue'

const confirmDialog = ref({
  visible: false,
  // ... 其他状态
})

const showConfirm = () => {
  confirmDialog.value.visible = true
}

const handleConfirm = async () => {
  confirmDialog.value.visible = false
  // 执行操作
}
</script>

<template>
  <ConfirmDialog
    v-model:visible="confirmDialog.visible"
    type="danger"
    title="删除确认"
    message="确定要执行此操作吗？"
    detail="详细信息"
    icon="⚠️"
    @confirm="handleConfirm"
  />
</template>
```

## 项目结构

```
src/
├── main.ts              # 应用入口
├── App.vue             # 根组件
├── components/         # 可复用组件
│   ├── ModelManager.vue
│   └── ConfirmDialog.vue
├── views/              # 页面视图
├── api/                # API 客户端
├── types/              # TypeScript 类型定义
└── assets/             # 静态资源
```

## 相关文档

- [Vue 3 官方文档](https://v3.vuejs.org/)
- [TypeScript 官方文档](https://www.typescriptlang.org/)
- [Vite 官方文档](https://vitejs.dev/)
- [DawnChat 项目开发规范](../../.cursorrules)
