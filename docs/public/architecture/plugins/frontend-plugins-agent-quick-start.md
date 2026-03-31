# Frontend Plugins Agent Quick Start

## 1. 先读这三块

- 架构总览：`docs/architecture/plugins/frontend-plugins-architecture.md`
- Workbench 入口：`apps/frontend/src/features/plugin-dev-workbench/views/PluginDevWorkbenchPage.vue`
- Apps 入口：`apps/frontend/src/features/plugin/views/AppsView.vue`

---

## 2. 三个 Feature 的一句话定位

- `features/plugin`：Apps / Build Hub 入口编排与列表交互。
- `features/plugin-runtime`：插件全屏运行态容器与会话守卫。
- `features/plugin-dev-workbench`：开发工作台（预览、发布、上下文注入）主战场。

---

## 3. 必须遵守的分层链路

```text
View(Page) -> Orchestration -> Capability Composable -> Facade -> pluginStore domains
```

- 页面只做模板绑定和事件转发。
- 副作用（watch、轮询、会话控制、发布流程）放在 composable/domain。
- store 访问优先通过 facade，不在页面和子组件直接写复杂 store 逻辑。

---

## 4. Workbench 迭代黄金规则（最高优先级）

- 新增业务能力时，优先在 `features/plugin-dev-workbench/composables` 新建能力模块。
- `PluginDevWorkbenchPage.vue` 不新增复杂业务分支，不新增网络与轮询副作用。
- 子容器组件（`Workbench*`）保持“展示 + emit”，不直连 store/router。
- 所有新能力都要挂到 orchestration 做统一收口。

---

## 5. 代码组织建议（新增功能时）

- 新增“页面级流程”：
  - 放 `usePluginDevWorkbenchOrchestration.ts`
- 新增“单一业务能力”（如某发布流程、某上下文策略）：
  - 新建 `useXxxFlow.ts` 或 `useXxxGuard.ts`
- 新增“store 边界动作”：
  - 先扩展 `devWorkbenchFacade.ts` / `buildHubLifecycleFacade.ts`
- 新增“纯展示区块”：
  - 在 `components/Workbench*.vue` 承载，避免回流到 page

---

## 6. 不要做的事（反模式）

- 不要在 page 里直接写 `pluginStore.runLifecycleOperation` 细节拼装。
- 不要把临时逻辑塞回 `AppsView.vue` 或 `PluginDevWorkbenchPage.vue`。
- 不要在组件层新增“隐式导航 + 隐式副作用”。
- 不要扩大 `pluginStore` 低层 API 的对外暴露面。

---

## 7. 提交前最小检查清单

- 是否仍是单向分层链路（Page -> Orchestration -> Composable -> Facade -> Store）？
- 是否把新增副作用放进了 composable/domain？
- 是否避免了页面直接调用低层 lifecycle 原子 API？
- 是否补了对应测试（能力单测 / 页面集成测试）？
- 是否通过 `pnpm --filter @dawnchat/frontend run typecheck`？

---

## 8. 快速定位表

- AppsView：`apps/frontend/src/features/plugin/views/AppsView.vue`
- Runtime：`apps/frontend/src/features/plugin-runtime/views/PluginRuntimeFullscreenPage.vue`
- Workbench：`apps/frontend/src/features/plugin-dev-workbench/views/PluginDevWorkbenchPage.vue`
- Store 聚合：`apps/frontend/src/stores/plugin/index.ts`
- Workbench facade：`apps/frontend/src/features/plugin-dev-workbench/services/devWorkbenchFacade.ts`
- BuildHub facade：`apps/frontend/src/features/plugin/services/buildHubLifecycleFacade.ts`

