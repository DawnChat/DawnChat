# DawnChat 晓话 AI

[!\[Rust\](https://img.shields.io/badge/Rust-1.90+-orange?style=flat-square\&logo=rust null)](https://www.rust-lang.org/)
[!\[Tauri\](https://img.shields.io/badge/Tauri-2.8+-blue?style=flat-square\&logo=tauri null)](https://tauri.app/)
[!\[Vue\](https://img.shields.io/badge/Vue-3.6+-green?style=flat-square\&logo=vue.js null)](https://vuejs.org/)
[!\[Python\](https://img.shields.io/badge/Python-3.11+-yellow?style=flat-square\&logo=python null)](https://www.python.org/)

DawnChat，构建可持续进化的 App。

传统软件的生命周期在点击“编译”和“发布”的那一刻就定型了。但 DawnChat 想打破这个边界。

这是一个本地优先的 AI 桌面运行时。在这里，创造一个 App 不需要折腾环境，**会打字就能开始**；App 也不再是写完就定型的死代码，你可以和 Agent 聊天，看着它在工作台里**实时重写代码、重塑界面**。

而这其中最激进的探索，是我们的官方 AI Assistant——它不仅能和你对话，还能在运行中持续进化自己的能力和界面。

[下载桌面端体验](https://github.com/chaxiu/ZenMind/releases) · [AI Assistant 路线图](./docs/public/architecture/assistant/ai-gui-workspace-v1-roadmap.md) · [查看架构文档](./docs/public/architecture/assistant/visual-voice-session-architecture.md) · [从源码开始](#从源码开始)

***

## 为什么做 DawnChat？

我们不想再做一个“套壳”的 AI 对话框，也不想做一个厚重的低代码平台。DawnChat 试图把这三件事无缝融合在一个桌面宿主里：

1. **极低门槛的 App 创造**：支持桌面端、Web 端、移动端。少一点环境配置的阻力，多一点直接创造。
2. **Agent As Builder**：Agent 不是浮在表面的助手，它能读取上下文，直接修改 App 的底层代码，让你立刻看到界面的变化。
3. **永远在进化的 App**：App 在运行中可以被持续迭代，打破了传统的“开发 -> 编译 -> 发布”的死循环。

***

## 核心看点

如果你刚来到这个仓库，我们建议你重点关注以下三个部分：

### 1. 见证 AI Assistant 的自我进化

官方 AI Assistant 不是一个简单的附带 Demo，而是 DawnChat 愿景的最强体现。
它不只回答问题。它会根据你的需求，实时调用新的页面能力，甚至在交互中改变自己的形态。我们正在把它打造成一个未来 AI GUI 工作空间的样板。

### 2. 在工作台里“边聊边造”

DawnChat 内置了一个强大的开发工作台。
你可以圈选界面上的任何元素，定位到源码，然后把这些上下文扔给 Agent。告诉它“把这个按钮改成红色，加个动画”，然后看着右边的预览区实时生效。

### 3. 多种形态的 App 创造

DawnChat 的底层架构不仅服务于单一场景，它支持你创建三种完全不同形态的 App：

- **Desktop**：原生的桌面窗口体验。
- **Web**：开发完成后，可一键发布到 DawnChat 官网。
- **Mobile**：在桌面端写代码，用手机扫码直接预览和安装。

***

## 最快体验路径

不想看枯燥的文档？跟着这个顺序来体验 DawnChat 最核心的魅力（演示视频即将上线）：

1. **下载安装**：获取最新的桌面端 App。
2. **把玩 Assistant**：先试用官方 AI Assistant，感受它如何在运行中持续进化自己。
3. **一句话建 App**：在工作台里，用自然语言快速生成一个新的 App。
4. **让 Agent 改代码**：对 Agent 提出修改需求，观察右侧预览的即时变化。

这套从“使用”到“创造”再到“进化”的连贯体验，就是 DawnChat 最大的不同。

***

## 当前核心能力

### App 运行与分发

- 支持桌面端、Web 端、移动端三类 App 形态
- 支持在线分发、安装、更新、卸载官方 App
- 支持运行时创建 App
- 支持 Web 预览热更新与 Python 热重启
- 支持前后端分层运行
- 支持 Web App 发布到 DawnChat 官网
- 支持移动端扫码预览与安装

### 开发工作台

- 支持实时预览 App UI
- 支持圈选定位源码
- 支持把定位上下文回填给 Agent
- 支持围绕同一个 App 进行持续开发循环

### Coding Agent

- 支持多引擎并行接入
- 通过统一 adapter 归约事件与会话状态
- 为更多 Agent/runtime 接入保留稳定边界

### 官方 AI Assistant

- 作为官方参考 App 开放
- 用于验证 AI 原生交互形态
- 用于探索 visual + voice session、workspace、page capability 与自我进化 runtime

***

## 适合谁

### 想立即体验的人

如果你想先感受 DawnChat 的产品形态，优先下载桌面端 App。

### 想构建自己 App 的人

如果你想创建桌面端、Web 端或移动端 App，并让 Agent 参与开发循环，DawnChat 提供了一个很独特的起点。

### 想研究下一代 AI 软件形态的人

如果你关心：

- AI Native Desktop Runtime
- 可进化 App
- Agent 参与软件生成与迭代
- 工作空间型 AI GUI

那么这个仓库可以作为一个开放的实验平台。

***

## 文档入口

- App 开发快速入口：[`docs/public/architecture/plugins/frontend-plugins-agent-quick-start.md`](./docs/public/architecture/plugins/frontend-plugins-agent-quick-start.md)
- AI Assistant 视觉 + 语音会话架构：[`docs/public/architecture/assistant/visual-voice-session-architecture.md`](./docs/public/architecture/assistant/visual-voice-session-architecture.md)
- AI GUI Workspace V1 路线图：[`docs/public/architecture/assistant/ai-gui-workspace-v1-roadmap.md`](./docs/public/architecture/assistant/ai-gui-workspace-v1-roadmap.md)
- 官方 AI Assistant 参考实现：[`dawnchat-plugins/official-plugins/desktop-ai-assistant`](./dawnchat-plugins/official-plugins/desktop-ai-assistant)

***

## 技术架构

### 宿主层

- `apps/desktop/src-tauri`
- 基于 Rust / Tauri
- 负责桌面生命周期、窗口、进程与宿主桥接

### 移动宿主层

- `apps/dawnchat-ios`
- `apps/dawnchat-android`
- 负责移动端 App 的运行、扫码预览与安装体验

### 前端应用层

- `apps/frontend`
- 基于 Vue 3 + TypeScript + Pinia
- 负责桌面应用 UI、开发工作台与运行时交互

### 后端内核层

- `packages/backend-kernel`
- 基于 Python / FastAPI
- 负责 App 进程管理、Agent 能力编排、工具系统与服务接口

### 插件生态层 (Under the hood)

- `dawnchat-plugins`
- 在底层架构中，所有 App 皆为插件。本目录包含官方 App、SDK 与发布相关内容

***

## 从源码开始

如果你想深入参与 DawnChat 平台本身，而不仅仅是下载桌面端 App 体验，可以从源码启动。

### 环境要求

- Node.js / pnpm
- Python 3.11+
- Poetry
- Rust toolchain

### 安装依赖

```bash
pnpm install
cd packages/backend-kernel && poetry install
cd ../..
```

### 准备运行时资源

仓库运行依赖一部分预置运行时资源，默认放在根目录 `runtime-assets/` 下，供开发脚本与构建脚本复用。

如果希望自动下载这些资源，可以运行：

```bash
./scripts/download-runtime-assets.sh --all
```

如果只想下载 TTS 模型，可以运行：

```bash
./scripts/download-runtime-assets.sh --tts
```

Kokoro TTS 模型默认使用 sherpa-onnx 官方公开链接。  
对于 Bun / uv / OpenCode，脚本默认已经指向官方 GitHub Release 稳定版（可通过版本变量覆盖）：

```bash
export DAWNCHAT_BUN_VERSION=bun-v1.3.11
export DAWNCHAT_UV_VERSION=0.11.2
export DAWNCHAT_OPENCODE_VERSION=v1.3.10
```

### 启动开发环境

推荐统一通过根目录脚本启动：

```bash
./dev.sh
```

如果只想查看可用参数：

```bash
./dev.sh --help
```

***

## 常用开发命令

### 测试

```bash
# 后端
./dev.sh --pytest
./dev.sh --pytest unit
./dev.sh --pytest-file tests/unit/test_agentv3_api.py

# 前端
./dev.sh --vitest run
./dev.sh --vitest-file src/stores/__tests__/codingAgentStore.spec.ts

# E2E
./dev.sh --e2e
./dev.sh --e2e-mock
```

### 质量检查

```bash
pnpm run lint
pnpm run lint:backend
pnpm run typecheck:backend
pnpm --filter @dawnchat/frontend run typecheck
cd apps/desktop/src-tauri && cargo fmt --all -- --check
```

***

## 项目状态

当前仓库适合以下使用方式：

- 作为 DawnChat 平台源码进行本地开发与研究
- 作为 app / 插件平台与开发工作台进行扩展
- 作为官方 AI Assistant 的参考实现进行架构探索

当前仍处于持续演进阶段。\
仓库中的部分能力已可稳定使用，部分能力仍处于实验性或架构探索阶段，尤其包括：

- AI Assistant 的终极 GUI / workspace 方向
- 任务自动化与多 Agent 方向
- 更高层的意图治理与持续演进机制

如果你希望参与，请优先把它理解为一个持续演进中的平台，而不是冻结不变的成品。

***

## 贡献

欢迎通过以下方式参与：

- 提交 issue
- 提交 app / 插件样板实现
- 改进平台能力
- 参与 AI Assistant 与 app 生态的架构讨论

在大规模提交前，建议先阅读仓库中的现有结构、脚本入口与质量检查命令，确保贡献方向与当前主线一致。

***

## License

本项目采用 Apache License 2.0 许可证。详见 [LICENSE](./LICENSE)。

## 商标说明

DawnChat 及相关名称、Logo 属于 DawnChat 项目商标资产。
名称、Logo 与品牌素材的使用规则请参阅 [TRADEMARK.md](./TRADEMARK.md)。
