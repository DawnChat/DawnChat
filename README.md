# DawnChat

[![Rust](https://img.shields.io/badge/Rust-1.90+-orange?style=flat-square&logo=rust)](https://www.rust-lang.org/)
[![Tauri](https://img.shields.io/badge/Tauri-2.8+-blue?style=flat-square&logo=tauri)](https://tauri.app/)
[![Vue](https://img.shields.io/badge/Vue-3.6+-green?style=flat-square&logo=vue.js)](https://vuejs.org/)
[![Python](https://img.shields.io/badge/Python-3.11+-yellow?style=flat-square&logo=python)](https://www.python.org/)

[简体中文](./README.zh.md) | English

DawnChat is built for apps that keep evolving.

Traditionally, software's lifecycle freezes the moment you hit "compile" and "publish". DawnChat breaks this boundary.

It is a local-first AI desktop runtime. Here, building an app requires zero environment wrestling—**if you can type, you can start creating**. Apps are no longer static, dead code. You can chat with an Agent and watch it **rewrite code and reshape the UI in real-time** right inside the workbench.

The most radical exploration of this vision is our official AI Assistant—it doesn't just chat with you; it continuously evolves its own capabilities and UI while running.

[Download for Desktop](https://github.com/DawnChat/DawnChat/releases) · [AI Assistant Roadmap](./docs/public/architecture/assistant/ai-gui-workspace-v1-roadmap.md) · [Architecture Docs](./docs/public/architecture/assistant/visual-voice-session-architecture.md) · [Build from Source](#build-from-source)

---

## Why DawnChat?

We don't want to build just another AI chat wrapper, nor another heavy low-code platform. DawnChat seamlessly blends three things into one desktop host:

1. **Frictionless App Creation**: Build for desktop, web, or mobile. Less setup friction, more direct creation.
2. **Agent As Builder**: The Agent isn't just a surface-level assistant. It reads the context, modifies the underlying code of your App, and lets you see UI changes instantly.
3. **Apps That Never Stop Evolving**: Apps can be continuously iterated while running, breaking the traditional "develop -> compile -> publish" dead loop.

---

## Core Highlights

If you're new to this repository, we recommend focusing on these three parts:

### 1. Witness the Self-Evolving AI Assistant
The official AI Assistant isn't just a side demo; it's the ultimate manifestation of DawnChat's vision.
It doesn't just answer questions. It dynamically calls new page capabilities based on your needs and even changes its own form during interactions. We are building it as the prototype for future AI GUI workspaces.

### 2. "Chat & Build" in the Workbench
DawnChat comes with a powerful built-in dev workbench.
You can select any element on the UI, trace it to the source code, and throw that context to the Agent. Tell it "make this button red and add an animation," and watch the preview panel on the right update instantly.

### 3. Create Multiple App Forms
DawnChat's underlying architecture isn't limited to a single use case. It allows you to create three entirely different forms of Apps:
- **Desktop**: Native windowed desktop experience.
- **Web**: One-click publish to the DawnChat website once developed.
- **Mobile**: Write code on your desktop, scan a QR code with your phone to preview and install instantly.

---

## The Fastest Way to Experience

Tired of reading docs? Follow this path to experience the core magic of DawnChat (Demo videos coming soon):

1. **Download & Install**: Get the latest Desktop App.
2. **Play with the Assistant**: Try the official AI Assistant first to see how it calls page capabilities.
3. **Build an App with One Prompt**: In the workbench, use natural language to quickly generate a new App.
4. **Let the Agent Code**: Ask the Agent to make modifications and watch the live preview update instantly.

This seamless flow from "using" to "creating" to "evolving" is what makes DawnChat truly different.

---

## Core Capabilities

### App Runtime & Distribution
- Supports three App forms: Desktop, Web, and Mobile.
- Online distribution, installation, updates, and uninstallation of official Apps.
- Create Apps at runtime.
- Web preview HMR (Hot Module Replacement) and Python hot-restarts.
- Frontend/Backend separated execution.
- Publish Web Apps to the DawnChat website.
- Mobile QR code scanning for preview and installation.

### Dev Workbench
- Live preview of App UI.
- UI element selection mapped to source code.
- Feed selected context back to the Agent.
- Continuous development loop around a single App.

### Coding Agent
- Supports parallel integration of multiple engines.
- Unified adapter for event and session state reduction.
- Stable boundaries reserved for future Agent/runtime integrations.

### Official AI Assistant
- Open-sourced as the official reference App.
- Used to validate AI-native interaction paradigms.
- Explores visual + voice sessions, workspaces, page capabilities, and self-evolving runtimes.

---

## Who is this for?

### For those who want to try it right now
If you just want to feel what DawnChat is, download the Desktop App first.

### For those who want to build their own Apps
If you want to create Desktop, Web, or Mobile apps and have an Agent assist in your dev loop, DawnChat provides a very unique starting point.

### For researchers of next-gen AI software paradigms
If you care about:
- AI Native Desktop Runtimes
- Evolvable Apps
- Agents participating in software generation and iteration
- Workspace-style AI GUIs

Then this repository serves as an open experimental platform.

---

## Documentation Map

- App Dev Quick Start: [`docs/public/architecture/plugins/frontend-plugins-agent-quick-start.md`](./docs/public/architecture/plugins/frontend-plugins-agent-quick-start.md)
- AI Assistant Visual + Voice Architecture: [`docs/public/architecture/assistant/visual-voice-session-architecture.md`](./docs/public/architecture/assistant/visual-voice-session-architecture.md)
- AI GUI Workspace V1 Roadmap: [`docs/public/architecture/assistant/ai-gui-workspace-v1-roadmap.md`](./docs/public/architecture/assistant/ai-gui-workspace-v1-roadmap.md)
- Official AI Assistant Reference Implementation: [`dawnchat-plugins/official-plugins/desktop-ai-assistant`](./dawnchat-plugins/official-plugins/desktop-ai-assistant)

---

## Architecture

### Host Layer
- `apps/desktop/src-tauri`
- Built on Rust / Tauri.
- Manages desktop lifecycle, windows, processes, and host bridging.

### Mobile Host Layer
- `apps/dawnchat-ios`
- `apps/dawnchat-android`
- Handles the execution, QR preview, and installation of mobile Apps.

### Frontend Application Layer
- `apps/frontend`
- Built on Vue 3 + TypeScript + Pinia.
- Handles desktop UI, dev workbench, and runtime interactions.

### Backend Kernel Layer
- `packages/backend-kernel`
- Built on Python / FastAPI.
- Manages App processes, Agent capability orchestration, tool systems, and service APIs.

### Plugin Ecosystem Layer (Under the hood)
- `dawnchat-plugins`
- In the underlying architecture, all Apps are plugins. This directory contains official Apps, SDKs, and release workflows.

---

## Build from Source

If you want to dive deep into the DawnChat platform itself, rather than just downloading the Desktop App, you can build it from source.

### Prerequisites
- Node.js / pnpm
- Python 3.11+
- Poetry
- Rust toolchain

### Install Dependencies

```bash
pnpm install
cd packages/backend-kernel && poetry install
cd ../..
```

### Prepare Runtime Assets

The repository relies on several pre-built runtime assets, which are placed in the `runtime-assets/` root directory by default. These are shared across development and build scripts.

To download all assets automatically:

```bash
./scripts/download-runtime-assets.sh --all
```

If you only want to download the TTS models:

```bash
./scripts/download-runtime-assets.sh --tts
```

The Kokoro TTS model uses the official public link from `sherpa-onnx`.
For Bun / uv / OpenCode, the script points to their official GitHub Release stable versions by default (can be overridden via environment variables):

```bash
export DAWNCHAT_BUN_VERSION=bun-v1.3.11
export DAWNCHAT_UV_VERSION=0.11.2
export DAWNCHAT_OPENCODE_VERSION=v1.3.10
```

### Start Development Environment

We recommend starting the environment using the unified script in the root directory:

```bash
./dev.sh
```

To see available options:

```bash
./dev.sh --help
```

---

## Common Dev Commands

### Testing

```bash
# Backend
./dev.sh --pytest
./dev.sh --pytest unit
./dev.sh --pytest-file tests/unit/test_agentv3_api.py

# Frontend
./dev.sh --vitest run
./dev.sh --vitest-file src/stores/__tests__/codingAgentStore.spec.ts

# E2E
./dev.sh --e2e
./dev.sh --e2e-mock
```

### Quality Checks

```bash
pnpm run lint
pnpm run lint:backend
pnpm run typecheck:backend
pnpm --filter @dawnchat/frontend run typecheck
cd apps/desktop/src-tauri && cargo fmt --all -- --check
```

### Logging Policy

```bash
# Development: backend logs can be redirected via DAWNCHAT_LOGS_DIR
DAWNCHAT_LOGS_DIR="$HOME/Desktop/DawnChatLogs" ./dev.sh
```

- Frontend logs are forwarded to backend for unified ingestion.
- In development, `./dev.sh` supports backend log path overrides through environment variables.
- In build/release, `./build.sh` enforces dedicated app log directories and ignores external log-dir overrides.

---

## Project Status

This repository is currently suited for:
- Local development and research using the DawnChat platform source.
- Extending the App / plugin platform and dev workbench.
- Architecture exploration using the official AI Assistant as a reference.

It is still in a phase of **continuous evolution**.
While some capabilities in the repository are stable, others are still experimental or in the architecture exploration phase, notably:
- The ultimate GUI / workspace direction for the AI Assistant.
- Task automation and multi-Agent orchestration.
- Higher-level intent governance and continuous evolution mechanisms.

If you wish to contribute, please treat this as an evolving platform rather than a frozen, finished product.

---

## Contributing

We welcome contributions in the following ways:
- Submitting issues.
- Submitting App / plugin boilerplate implementations.
- Improving platform capabilities.
- Participating in architecture discussions around the AI Assistant and App ecosystem.

Before making large-scale commits, we recommend reviewing the existing structure, script entry points, and quality check commands in the repository to ensure your contribution aligns with the main branch.

---

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](./LICENSE) for details.

## Trademark

DawnChat and related names/logos are trademarks of the DawnChat project.
Use of names, logos, and brand assets is subject to [TRADEMARK.md](./TRADEMARK.md).
