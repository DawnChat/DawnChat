# AI GUI Workspace V1 落地规划

## 1. 文档目标

- 基于当前 AI assistant 架构，给出一份可执行的 V1 演进规划。
- 说明当前基于 step 的 MCP 流程已经解决了什么问题、还存在哪些结构性不足。
- 说明为什么 V1 不追求终极形态，而是优先建立稳定骨架，为后续自我进化打基础。
- 给未来 Agent 提供一致的架构演进心智模型，避免在扩展页面、能力、状态时反复推翻。

相关总纲可参考 [ai-gui-workspace-architecture.md](file:///Users/zhutao/Cursor/ZenMind/docs/architecture/assistant/ai-gui-workspace-architecture.md)。

---

## 2. 当前架构现状

当前 assistant 已经具备一个非常重要的基础闭环：

- 宿主提供 `dawnchat.ui.session.start/status/stop`，统一会话生命周期管理。
- `session.start` 可快速 ACK，后台异步推进 step，降低阻塞与超时风险。
- 宿主不解析 step 业务字段，step 细节保持在插件域自治。
- 插件前端已拥有一个最小 step 执行器，可执行 `card.show` 并串联宿主 TTS。

这些能力已经在 [visual-voice-session-architecture.md](file:///Users/zhutao/Cursor/ZenMind/docs/architecture/assistant/visual-voice-session-architecture.md) 中明确，其意义在于：

- 会话级调度与插件业务执行已经成功解耦。
- Agent 已经可以一边改插件，一边调用插件进行视觉 + 语音交互。
- 当前链路已经从“单次页面渲染”进化到“多 step 会话执行”。

从代码现状看，[sessionStepExecutor.ts](file:///Users/zhutao/Cursor/ZenMind/dawnchat-plugins/official-plugins/desktop-ai-assistant/_ir/frontend/web-src/src/runtime/sessionStepExecutor.ts#L32-L117) 是一个明确的 MVP 执行器：

- 它通过 `action.type` 分发 handler。
- 目前只支持 `card.show`。
- `card.show` 会直接设置主卡片，并在 payload 中读取 `voice`，然后等待 TTS 完成。
- step 完成语义目前隐式绑定在 `await hostVoiceSpeakOrThrow(...)` 上。

这说明：当前架构已经跑通闭环，但还停留在“卡片讲解型会话”的早期阶段。

---

## 3. 当前基于 step 的 MCP 流程解决了什么

### 3.1 已解决的问题

- 把视觉 + 语音交互收敛到统一 session 生命周期。
- 让宿主只负责控制平面，不侵入 step 业务 payload。
- 让插件拥有 step 内自治能力，可在前端自行决定何时完成 step。
- 让 Agent 可以通过结构化 `steps[]` 驱动一个连续交互过程，而不是每次独立发起零散调用。

### 3.2 现有模式的价值

当前模式的核心价值不是“支持了卡片”，而是建立了一个非常重要的宿主/插件边界：

- 宿主负责：
  - 会话准入
  - 状态观测
  - 取消与超时
- 插件负责：
  - 业务动作
  - 页面渲染
  - 讲解节奏
  - 宿主语音调用

这条边界在 V1 必须保留，不能为了扩展能力又把业务语义拉回宿主。

---

## 4. 当前架构的核心问题

V1 规划的前提，不是否定当前方案，而是识别当前方案在哪些地方会阻碍长期演进。

### 4.1 step 仍然过于“卡片中心”

当前执行器虽然对外暴露的是 `action.type`，但实际实现仍然是：

- `card.show` 负责主页面展示
- `voice` 作为 `card.show` 的附属字段出现
- 完成时机隐式跟随 voice

这使得当前 step 语义更像“卡片讲解命令”，而不是“通用 AI GUI 工作单元”。

### 4.2 完成语义尚未抽象

目前 step 的 finish 语义主要依赖：

- 渲染卡片
- 如果有 voice，就等待 TTS 完成

这对讲解型卡片成立，但对未来场景会迅速失效，例如：

- 需要用户点击提交的交互卡片
- 需要先切 view 再讲解
- 需要高亮后等待用户继续
- 需要纯 view 操作而没有任何 TTS

### 4.3 页面能力与讲解能力混在一起

当前 `card.show` 同时承担了两件事：

- 页面内容切换 / 主视图呈现
- 讲解过程中的表达载体

这在 MVP 阶段是合理的，但长期看会导致：

- 页面本体能力无法稳定沉淀
- Guide 能力与 View 能力边界模糊
- 未来 Agent 难以扩展复杂页面能力

### 4.4 缺少工作空间状态模型

当前 session 能推进 step，但系统还没有一个明确的 workspace state 抽象去描述：

- 当前正在处理哪个资源
- 当前激活哪个 view
- 当前聚焦哪个 anchor
- 当前已有的 notes / highlights / artifacts
- 当前主线任务进度到哪里

这意味着当前系统更像“执行步骤”，还不像“维护共享工作空间”。

### 4.5 缺少事件协作面

当前 step 执行更像“等待 Promise 完成”，而不是“由语义事件驱动 runtime 协作”。

缺少统一事件面，会带来几个问题：

- view 与 guide 协作点难以标准化
- flow 难以基于事件推进
- 中断、恢复、分支都只能靠局部硬编码

### 4.6 缺少面向 Agent 的稳定扩展骨架

如果未来 Agent 要自我进化实现一个新页面，当前系统还缺少这些稳定约定：

- workspace state 如何组织
- view 如何注册
- capability 如何声明
- anchor 如何命名
- runtime 如何感知新能力

没有这些骨架，Agent 每次新增一个复杂场景都容易从零发明一套结构，长期不可控。

---

## 5. V1 的定位

V1 不是终极 AI GUI，也不是一次性实现 6 层模型。  
V1 的任务只有一句话：

> 在不破坏当前宿主/插件边界的前提下，把“基于 step 的讲解会话”升级为“具备工作空间雏形的 AI GUI Runtime”。

V1 不解决所有问题，它优先解决的是：

- step 类型分层
- workspace state 雏形
- event bus 雏形
- view capability 注册雏形
- guide / view / flow 的职责分工

V1 的成功标准不是“已经拥有终极体验”，而是：

- 未来新增场景时不需要推翻 runtime 核心
- Agent 可以在稳定骨架上做受约束扩展
- 当前单词讲解场景可以作为平台样板工程

---

## 6. V1 的目标状态

V1 建议将当前单一 step 执行器演进为以下结构：

- `guide.*`
- `view.*`
- `app.*`
- `flow.*`

但注意，V1 的重点不是命名空间本身，而是借此完成职责收敛。

### 6.1 `guide.*`

职责：

- 面向用户的讲解、提示、轻交互
- TTS、tip、overlay、轻量 quiz、确认继续

它是讲解表达层，不是页面本体能力层。

### 6.2 `view.*`

职责：

- 面向具体 view 的能力调用
- 打开 view、聚焦 anchor、局部高亮、打开 modal、切换 section

它是页面能力层，不应混入过多讲解逻辑。

### 6.3 `app.*`

职责：

- 工作空间级或插件级的全局能力
- 模式切换、全局资源绑定、全局状态调整

V1 可以很轻，但命名空间最好先保留。

### 6.4 `flow.*`

职责：

- 编排顺序、等待、简单分支、中断恢复

它不是巨型 DSL，只是 V1 的最小 orchestrator 抽象。

---

## 7. V1 核心原则

### 7.1 宿主边界不变

V1 必须继续坚持：

- 宿主只管理 session lifecycle
- 宿主不解析 step 业务字段
- 业务协议演进发生在插件域

### 7.2 Step 仍然是统一执行单元

V1 不建议把 Scene、Capability、Flow 拆成多个顶层协议入口。  
仍然应保持：

- 一个 `session.start`
- 一个 `steps[]`
- 每个 step 用 `action.type` 区分职责

这样对宿主、Agent、运行时都更稳定。

### 7.3 先统一 envelope，再细化内部语义

V1 要稳定的是：

- `step_id`
- `action.type`
- `action.payload`
- `timeout_ms`

而不是一开始就试图设计完美 DSL。

### 7.4 页面不是唯一真相

V1 就应该开始建立这个意识：

- 页面是状态投影
- workspace state 才是长期真相

即使 V1 还不会完整实现恢复与 undo，也要为后续留出正确方向。

### 7.5 Agent 只做场景增量，不做 runtime 发明

V1 的平台责任是给 Agent 稳定骨架。  
Agent 的责任是：

- 新资源
- 新 view
- 新 capability
- 新 guide 模式

而不是每次都重写 runtime 规则。

---

## 8. V1 建议引入的核心抽象

### 8.1 Workspace Store（雏形）

V1 可以先将 workspace state 设计为可序列化的 JS Store，但必须分层：

- Workspace Core State
- Resource-owned Slice
- Session Runtime State
- Ephemeral UI State

V1 的重点是：

- 先让 AI 能读取结构化 snapshot
- 先让 view / guide / flow 有共享语义状态
- 不要求一次性把所有局部 UI 状态都纳入 durable state

### 8.2 Event Bus（雏形）

V1 需要一个 typed event bus，负责：

- runtime 间协作
- flow 等待触发
- 调试与可观测

V1 事件不必复杂，但建议至少覆盖：

- `flow.*`
- `guide.*`
- `view.*`
- `app.*`

### 8.3 View Manifest

V1 需要让每个 view 具备基础自描述能力。

最小 manifest 应至少说明：

- `view_id`
- `resource_type`
- `capabilities`
- `anchors`
- `state_summary`

这样 Agent 在面对新页面时，不只是看截图和 DOM tree 猜页面结构，也能读到页面主动暴露的语义能力。

### 8.4 Resource-owned State Slice

V1 不需要一个万能通用资源模板，但必须统一资源的组织方式：

- 平台提供稳定 envelope
- 具体资源扩展自己的 slice

例如：

- 单词场景拥有自己的 word slice
- 论文场景拥有自己的 paper slice

关键不是字段相同，而是扩展方式相同。

### 8.5 Checkpoint

V1 建议优先做 checkpoint，而不是一开始就追求完整 undo。

优先级原因：

- Resume 比 perfect undo 更现实
- 长流程协作更需要恢复能力
- 复杂 GUI 的全量可逆很昂贵

---

## 9. 当前 step 流程如何演进到 V1

这里给出一条建议路线，强调“渐进演化”，而不是“推倒重写”。

### 阶段 0：保留现有 session 宿主链路

保留现有：

- `dawnchat.ui.session.start/status/stop`
- 宿主快速 ACK
- 前端异步执行 step
- 插件侧 `assistant.session_step_execute`

这是 V1 的稳定控制平面，不建议推翻。

### 阶段 1：把当前执行器从“单 action”升级为“命名空间分发器”

当前 [sessionStepExecutor.ts](file:///Users/zhutao/Cursor/ZenMind/dawnchat-plugins/official-plugins/desktop-ai-assistant/_ir/frontend/web-src/src/runtime/sessionStepExecutor.ts#L32-L88) 里，`actionHandlers` 仍然是单层 map。

V1 目标不是简单增加更多 action，而是让执行器具备这种心智：

- 识别 `guide.*`
- 识别 `view.*`
- 识别 `app.*`
- 识别 `flow.*`
- 分发到对应 runtime handler

这样执行器从“业务实现容器”升级为“runtime dispatcher”。

### 阶段 2：抽出 Guide Runtime

先把当前 `card.show + voice` 路径收敛到 guide runtime。

V1 初始 guide 能力可以非常小：

- `guide.card.show`
- `guide.tip.show`
- `guide.quiz.popup`
- `guide.confirm.ask`

重点不是动作数量，而是：

- 让 Guide 负责讲解表达
- 不再让 View 能力偷偷藏在 `card.show` 里

### 阶段 3：引入最小 View Runtime

V1 的 view runtime 不需要很复杂，但至少应具备：

- 打开 view
- 聚焦 anchor
- 触发 view capability
- 对外提供 manifest

这样“单词解释页”“论文阅读页”才会有长期沉淀空间。

### 阶段 4：引入 Workspace Store 雏形

先不要设计完整终局状态，只需要：

- 当前资源
- 当前 view
- 当前 anchor
- 当前任务进度
- 当前核心 artifacts

并提供结构化 snapshot 给 AI 消费。

### 阶段 5：引入 Event Bus

让 flow、guide、view 开始通过语义事件协作，而不是全部通过嵌套 Promise 或局部回调串起来。

### 阶段 6：引入最小 Flow Runtime

V1 不做复杂图式工作流，只支持：

- 顺序执行
- 等待
- 简单分支
- 中断后回主线

它的目标不是“强工作流引擎”，而是让 step session 从线性脚本升级为最小编排系统。

### 阶段 7：加入 Checkpoint / Resume

在关键节点加入恢复点：

- 打开资源后
- 进入关键讲解阶段前
- quiz 前后
- 会话总结前

这样系统会从“能跑一次”进化为“能协作一段时间”。

---

## 10. V1 不该做什么

为了避免过度设计，V1 明确不建议做以下事情：

### 10.1 不做全能 DSL

V1 不要追求任意组合、任意图结构、任意触发器表达式。  
先用有限命名空间与有限动作把骨架搭起来。

### 10.2 不做全量 Undo

V1 优先级应是：

- state
- event
- checkpoint
- resume

而不是对每一个动作设计完整反向操作。

### 10.3 不把 Guide 做成页面控制器

Guide 应聚焦：

- 讲解
- 提示
- 轻交互

真正页面控制应归 View。

### 10.4 不让 Agent 自由发明状态结构

V1 必须由平台定义：

- workspace 顶层结构
- resource slice 组织方式
- manifest 格式
- event 命名规则

否则 Agent 在新场景下极易失控。

---

## 11. V1 的样板工程策略

V1 最重要的场景，不是“业务上最有价值的场景”，而是“最适合作为平台母版的场景”。

建议选择一个较小但完整的场景作为 reference implementation，例如单词解释。

这个样板应完整覆盖：

- 一个 resource slice
- 一个主 view
- 一组基础 capability
- 一组 guide 行为
- 一条 flow 序列
- 一份 workspace snapshot
- 一份 view manifest

它的目标不是做一个单词功能，而是定义：

- 新场景以后应该如何扩展平台

在样板稳定后，再进入更复杂场景，例如：

- document-like resource
- markdown / article 阅读
- 最终再进入 PDF

这样 PDF 才是在“沿着平台骨架扩展”，而不是“首个复杂场景倒逼架构发明”。

---

## 12. V1 的成功标准

V1 达标，不代表终局完成；V1 达标意味着以下几点成立：

- 当前 step 会话模型仍然稳定可用
- `guide / view / app / flow` 的职责边界已经建立
- 执行器已从单动作实现演进为 runtime dispatcher
- workspace state 已有最小结构化抽象
- event bus 已能支撑 runtime 协作
- Agent 扩展新 view / capability 时有明确模板可依赖
- 样板场景可以在不修改 runtime 核心的情况下扩展第二个场景

如果这些条件成立，就说明系统已经从“卡片讲解型 assistant”进入“AI GUI Runtime V1”。

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

V1 的任务不是到达终局，而是保证从今天开始的每一步演进，都朝着终极工作空间形态收敛，而不是再次回到临时拼装。
