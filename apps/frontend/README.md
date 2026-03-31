# DawnChat Frontend

English | [简体中文](./README.zh.md)

`apps/frontend` is DawnChat’s frontend application layer. It powers:
- Build Hub (plugin discovery, creation, startup)
- Plugin Runtime (fullscreen runtime surface)
- Plugin Dev Workbench (preview, publishing, context bridge, IWP build flow)

Stack: Vue 3 + TypeScript + Vite + Pinia.

---

## Core Pages (Read First)

### 1) Home / Build Hub
- Page: `src/features/plugin/views/AppsView.vue`
- Role: unified entry for app creation, recent project resume, and app feed operations.
- Boundary: page layer stays thin (template + event wiring); create/start/fork lifecycle calls go through `buildHubLifecycleFacade`.

### 2) Dev Page / Dev Workbench
- Page: `src/features/plugin-dev-workbench/views/PluginDevWorkbenchPage.vue`
- Role: main development workspace for center editor, preview pane, publish overlays, IWP files, and build session status.
- Boundary: page only consumes orchestration output, never calls `usePluginStore` directly; store access goes through `devWorkbenchFacade`.

---

## Frontend Plugin Architecture

Three feature surfaces:
- `features/plugin`: AppsView / Build Hub
- `features/plugin-runtime`: fullscreen runtime
- `features/plugin-dev-workbench`: dev workbench

Shared principles:
- Single source of truth: cross-page state lives in `stores/plugin` (`usePluginStore`).
- Thin page containers: views focus on route parsing, rendering, and event forwarding.
- Side effects go down: lifecycle, polling, publish, and session injection belong to composables/domains.
- Clear access boundary: runtime/workbench use facades instead of crossing layers into store internals.

Recommended one-way chain:

```text
Page -> Orchestration -> Capability Composable -> Facade -> Store
```

---

## Directory Map (Plugin Development Focus)

```text
src/
├── features/
│   ├── plugin/                          # Build Hub
│   │   ├── views/AppsView.vue
│   │   ├── composables/useBuildHub*.ts
│   │   └── services/buildHubLifecycleFacade.ts
│   ├── plugin-runtime/                  # Fullscreen runtime
│   │   ├── views/PluginRuntimeFullscreenPage.vue
│   │   └── services/runtimeFacade.ts
│   └── plugin-dev-workbench/            # Dev workbench
│       ├── views/PluginDevWorkbenchPage.vue
│       ├── composables/usePluginDevWorkbenchOrchestration.ts
│       └── services/devWorkbenchFacade.ts
├── features/plugin/store/               # Plugin domain single store
└── components/                          # Shared UI components
```

---

## Quick Start

```bash
# Install dependencies at repository root
pnpm install

# Start frontend dev server (inside apps/frontend)
pnpm run dev

# Production build
pnpm run build

# Frontend typecheck
pnpm run typecheck
```

---

## Tests and Quality Checks

Run from repository root (recommended):

```bash
# Frontend tests
./dev.sh --vitest run
./dev.sh --vitest-file src/**/__tests__/xxx.spec.ts

# Workspace lint
pnpm run lint

# Frontend typecheck
pnpm --filter @dawnchat/frontend run typecheck
```

---

## Frontend Development Constraints

- Use Composition API (`<script setup>`) with TypeScript.
- Keep business side effects out of page views; place them in composables.
- Do not access low-level store APIs directly inside pages and `Workbench*` components; use facades.
- Do not use browser native dialogs (`window.alert/confirm/prompt`); use custom dialog components.
- Route frontend logs through `src/utils/logger.ts` instead of direct `console.log`.

---

## References

- Repository overview: `/README.md`
- Internal plugin frontend architecture: `/docs/internal/architecture/plugins/frontend-plugins-architecture.md`
