# DawnChat Frontend

`apps/frontend` 是 DawnChat 的前端应用层，负责：
- Build Hub（插件发现/创建/启动）
- Plugin Runtime（全屏运行态）
- Plugin Dev Workbench（开发工作台：预览、发布、上下文回填、IWP Build）

技术栈：Vue 3 + TypeScript + Vite + Pinia。

---

## 核心页面（建议先读）

### 1) 首页 / Build Hub
- 页面：`src/features/plugin/views/AppsView.vue`
- 角色：统一入口，承接新建应用、最近项目快速恢复、应用列表运营流。
- 边界：页面层只做模板绑定与事件转发，创建/启动/Fork 生命周期调用统一通过 `buildHubLifecycleFacade`。

### 2) 开发页 / Dev Workbench
- 页面：`src/features/plugin-dev-workbench/views/PluginDevWorkbenchPage.vue`
- 角色：开发主工作台，承接编辑区、预览区、发布弹层、IWP 文件与 Build 会话。
- 边界：页面层仅消费 orchestration 输出，不直接访问 `usePluginStore`，所有 store 访问经 `devWorkbenchFacade`。

---

## 前端插件架构总览

三大 feature 页面分层：
- `features/plugin`：AppsView / Build Hub
- `features/plugin-runtime`：全屏运行态
- `features/plugin-dev-workbench`：开发工作台

统一原则：
- 单一状态源：跨页面状态统一在 `stores/plugin`（`usePluginStore`）。
- 页面容器轻量：View 只做参数解析、模板渲染、事件转发。
- 副作用下沉：生命周期、轮询、发布流程、会话注入放在 composable / domain。
- 访问边界清晰：runtime/workbench 通过 facade 访问 store，不跨层直连。

推荐单向链路：

```text
Page -> Orchestration -> Capability Composable -> Facade -> Store
```

---

## 目录速查（与插件开发最相关）

```text
src/
├── features/
│   ├── plugin/                          # Build Hub（首页）
│   │   ├── views/AppsView.vue
│   │   ├── composables/useBuildHub*.ts
│   │   └── services/buildHubLifecycleFacade.ts
│   ├── plugin-runtime/                  # 全屏运行态
│   │   ├── views/PluginRuntimeFullscreenPage.vue
│   │   └── services/runtimeFacade.ts
│   └── plugin-dev-workbench/            # 开发页
│       ├── views/PluginDevWorkbenchPage.vue
│       ├── composables/usePluginDevWorkbenchOrchestration.ts
│       └── services/devWorkbenchFacade.ts
├── features/plugin/store/               # 插件领域单一状态源
└── components/                          # 通用 UI 组件
```

---

## 快速开始

```bash
# 在仓库根目录安装依赖
pnpm install

# 启动前端开发服务（在 apps/frontend 目录）
pnpm run dev

# 生产构建
pnpm run build

# 前端类型检查
pnpm run typecheck
```

---

## 测试与质量检查

在仓库根目录执行（推荐）：

```bash
# 前端测试
./dev.sh --vitest run
./dev.sh --vitest-file src/**/__tests__/xxx.spec.ts

# 全仓 lint
pnpm run lint

# 前端 typecheck
pnpm --filter @dawnchat/frontend run typecheck
```

---

## 开发约束（前端）

- 使用 Composition API（`<script setup>`）与 TypeScript。
- 业务副作用不要回流页面层：优先放入 composable。
- 禁止在页面与 `Workbench*` 子容器中直接访问底层 store（走 facade）。
- 禁止使用浏览器原生弹窗（`window.alert/confirm/prompt`），统一使用自定义对话框组件。
- 前端日志统一走 `src/utils/logger.ts`，避免直接 `console.log`。

---

## 关键参考文档

- 仓库总览：`/README.md`
- 插件前端架构（内部）：`/docs/internal/architecture/plugins/frontend-plugins-architecture.md`
