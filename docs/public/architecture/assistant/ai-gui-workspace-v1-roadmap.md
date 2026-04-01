# AI Assistant Architecture and Roadmap

## 1. Purpose

This document describes the public north star for DawnChat AI Assistant.

It does not enumerate current progress or implementation status. Instead, it explains:

- what the long-term architecture is trying to become,
- what the major runtime layers are,
- how the system is expected to evolve over time.

The core idea is simple:

> The goal is not a better chat box. The goal is a shared AI workspace where the user and the agent can see, act, explain, pause, and resume work together.

---

## 2. North Star

Traditional software treats UI as a human surface and AI as an external helper.

DawnChat is moving toward a different model:

- the workspace becomes the primary surface,
- chat becomes only one interaction channel,
- the agent can explain, operate, and observe within the same task space,
- state, events, and checkpoints become first-class parts of the product.

In the long run, the assistant should feel less like a chatbot calling tools and more like a collaborative runtime living inside a structured application environment.

---

## 3. Architecture Overview

The target architecture can be understood as six cooperating runtime layers plus four cross-cutting planes.

```text
User
  │
  ▼
Guide Runtime  ───── explains, prompts, confirms, teaches
  │
  ▼
Flow Runtime   ───── decides what happens next
  │
  ├──────────────► View Runtime ───── opens and manages task-facing views
  │                       │
  │                       ▼
  ├──────────────► Capability Runtime ─ structured actions on resources and views
  │
  ▼
Workspace Runtime ───── shared task state, artifacts, anchors, progress
  │
  ▼
Session Kernel ───── lifecycle, start/stop/status, timeout, cancel, observability

Cross-cutting planes:
- State Plane
- Event Plane
- Operation Plane
- Checkpoint Plane
```

---

## 4. Runtime Layers

### 4.1 Session Kernel

The Session Kernel is the control plane.

It manages:

- session lifecycle,
- concurrency and cancellation,
- timeouts and observability,
- waiting for new interaction signals without owning business meaning.

### 4.2 Workspace Runtime

The Workspace Runtime is the semantic center of the system.

It tracks the shared task reality, such as:

- the current resource,
- the active view,
- the current semantic anchor,
- generated notes, highlights, summaries, and other artifacts,
- task stage and resumable context.

### 4.3 View Runtime

The View Runtime renders and manages task-facing interfaces.

A resource may have multiple views, and views may be:

- static product views,
- structured work panels,
- dynamically composed AI-assisted interfaces.

### 4.4 Capability Runtime

The Capability Runtime gives the agent structured ways to act.

Instead of relying on fragile UI guessing, the system should expose semantic capabilities with:

- clear names,
- explicit input and output shapes,
- well-bounded side effects.

### 4.5 Guide Runtime

The Guide Runtime is responsible for explanation and human-facing interaction.

Typical responsibilities include:

- hints and overlays,
- confirmations and approvals,
- lightweight teaching flows,
- narration and assistive guidance.

### 4.6 Flow Runtime

The Flow Runtime is the orchestration layer.

It organizes:

- sequencing,
- waiting,
- branching,
- interruption,
- recovery and return-to-mainline behavior.

It should guide the task, not become a giant workflow DSL.

---

## 5. Cross-Cutting Planes

### 5.1 State Plane

The State Plane describes what is true now.

Only durable, shareable, and resumable state should become part of the core workspace state.

### 5.2 Event Plane

The Event Plane describes what just happened.

Events are used for:

- runtime coordination,
- flow progression,
- debugging and observability.

The transport should remain flexible. Early implementations may use timeout-based long polling to consume new events by sequence, while later versions may adopt streaming channels.

### 5.3 Operation Plane

The Operation Plane records meaningful actions for auditability, explainability, and partial recovery.

### 5.4 Checkpoint Plane

The Checkpoint Plane defines where work can safely resume.

For complex AI-assisted interfaces, checkpoint and resume are usually more valuable than trying to make every action perfectly undoable.

---

## 6. Core Product Abstractions

The architecture revolves around a few durable concepts:

- **Resource**: the thing being worked on, such as a word, paper, note, code file, or task artifact.
- **View**: a visual and interactive presentation of a resource.
- **Anchor**: a semantic focus point inside a resource or view.
- **Artifact**: a durable output produced during work, such as a note, highlight, summary, or quiz result.

These abstractions matter because they allow the assistant to operate on shared meaning rather than only on transient UI pixels.

---

## 7. Interaction Model

At a high level, DawnChat AI Assistant is moving toward this model:

- the host controls session lifecycle,
- the workspace holds shared task state,
- views render the task surface,
- capabilities provide structured actions,
- guide handles explanation and approvals,
- flow coordinates progress,
- events and checkpoints make interruption and resume practical.

This is intentionally broader than plain tool calling, but more bounded than an OS-level autonomous agent.

---

## 8. Roadmap

### Phase 1: Reliable Session Foundation

Establish a stable control plane for assistant sessions.

Focus:

- lifecycle management,
- async execution,
- cancellation and timeout semantics,
- basic event consumption and observability.

### Phase 2: View-First Interaction

Move from isolated responses to durable task-facing views.

Focus:

- view registration and switching,
- structured view descriptions,
- guide experiences that are attached to views rather than floating separately.

### Phase 3: Semantic Capabilities

Make the assistant act through semantic interfaces instead of fragile UI heuristics.

Focus:

- discoverable capabilities,
- capability schemas,
- resource- and view-scoped actions,
- clearer side-effect boundaries.

### Phase 4: Shared Workspace State

Upgrade from step execution to shared task reality.

Focus:

- workspace snapshots,
- resource-owned state slices,
- artifacts and anchors,
- durable context that survives interruption.

### Phase 5: Event-Driven Orchestration

Introduce stronger coordination between runtimes.

Focus:

- event-based flow progression,
- wait/continue patterns,
- human-in-the-loop approvals,
- better interruption handling.

### Phase 6: Checkpoint and Resume

Turn sessions into resumable collaboration.

Focus:

- checkpoint strategy,
- resumable task stages,
- recovery after interruption,
- clearer takeover and handback semantics.

### Phase 7: Task-Scale Runtime

Evolve from guided sessions into longer-running collaborative task execution.

Focus:

- multi-step task progression,
- background task awareness,
- artifact accumulation,
- richer task workspaces with stronger structure.

---

## 9. What This Roadmap Is Not

This roadmap does not aim to build:

- a universal OS automation layer,
- a giant workflow language,
- a system where the agent invents runtime structure on its own,
- a chat product that only adds more tools without improving shared task state.

The architecture is intentionally application-level, workspace-native, and human-in-the-loop.

---

## 10. Destination

The end state is an assistant that can:

- understand what the user and the system are working on,
- present the right task surface,
- act through structured capabilities,
- explain its actions,
- request approval when needed,
- recover from interruption,
- continue work across sessions.

That is the long-term direction for DawnChat AI Assistant: not just agent-powered UI, but a durable AI workspace runtime.

上述条件成立时，系统即可视为从“卡片讲解型 assistant”进入“AI GUI Runtime V1”。

---

## 13. 最终结论

当前基于 step 的 MCP 流程不是错误方向，它已经是一个非常重要的正确起点：

- 宿主管控制平面
- 插件管业务执行
- Agent 通过 `steps[]` 驱动连续交互

真正需要演进的，不是推翻它，而是让它从：

- 卡片驱动的讲解执行器

逐步演进为：

- 具备 guide / view / app / flow 分层
- 具备 workspace state 与 event 协作
- 具备 checkpoint 与恢复能力
- 具备 Agent 可模仿、可扩展、可自我进化骨架

的 V1 AI GUI Runtime。

V1 的目标不是到达终局，而是确保后续每一步演进都向终极工作空间形态收敛，避免回到临时拼装路径。
