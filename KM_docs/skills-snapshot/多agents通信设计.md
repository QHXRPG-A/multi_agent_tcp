# 多 Agents 通信设计

## 1. 统一前提：把控制流从算子里拆出来

无论前端形态叫“蓝图”、DAG，还是可视化工作流，框架内部都建议明确拆成两层：

- 数据流边：谁把什么传给谁，例如 `payload`、`context`、文件引用、共享工作区路径、结构化结果。
- 控制流边：谁在什么时候允许被调度，例如 `ready`、`fire`、`join`、`cancel`、`finish` 条件。

`parallel`、`fan-out`、`fan-in`、`switch`、`nonblocking join` 本质上都是控制流语义。实现上可以有两种路线：

- 图编译时展开成更细的 primitive，例如 `fork`、`join`、`barrier`、`guard`。
- 运行时调度器用少量稳定原语组合出这些模式，例如 ready queue、agent queue、join policy、branch state。

这份文档的核心原则是：Agent 不直接驱动图结构流转，Agent 只提交意图和结果；真正的调度、校验、转发、归档、冲突处理都由框架负责。

## 2. 相关输入文档

- Codex CLI 输出字段说明：`F:\src\ryven_demo\codex cli 输出结果.md`
- Codex 输出样例：`F:\src\Package\Script\Python\multi_agent_tcp\agentnode_codex_output_sample.json`
- 当前 multi-agent 框架主线：`F:\src\Package\Script\Python\multi_agent_tcp`

## 3. 总体运行模型

框架接下来围绕 Codex CLI / GuLiCode / 多 Agent 蓝图形成三层：

- 顶层 Agent：全局唯一，面向用户，理解整张蓝图和所有 Agent 的职责，负责任务拆解、启动建议、状态解释、终止建议。
- 普通 AgentNode：图里的具体执行者，负责代码、文案、图像、测试、评审、汇总等局部任务。
- 框架运行时：唯一可信调度者，负责任务启动、控制流推进、Agent 消息队列、共享工作区、VCS-style changeset、归档、冲突与事件。

推荐链路：

```text
用户输入
  -> 顶层 Agent 理解任务和组织架构
  -> 顶层 Agent 调用框架 start 接口提交启动计划
  -> 框架校验启动计划
  -> 框架写入临时共享工作区和运行 manifest
  -> 框架按控制流调度普通 AgentNode
  -> 普通 AgentNode 返回结构化结果
  -> 框架分发消息、写事件、处理 join / switch / conflict
  -> 顶层 Agent 或用户查询状态 / 发起终止 / 汇总结果
```

## 4. 顶层 Agent：GuLiCode

### 4.1 定位

顶层 Agent 全局唯一，建议以 GuLiCode 为基础。它不是图里某个普通节点，而是蓝图运行的“用户代理”和“组织协调入口”。

它需要具备四类能力：

- 与用户直接对话，理解用户目标、约束、偏好和验收标准。
- 读取当前蓝图组织架构，理解每个 Agent 的职责、skill、rule、提示词和可通信对象。
- 生成启动计划，决定一个或多个启动节点，以及每个启动节点收到的初始任务。
- 查询并解释运行状态，必要时建议用户暂停、继续、重试、改道或结束。

### 4.2 为什么删除显式 Start / End 节点

原有 Start / End 节点能表达最小 runnable graph，但会把蓝图固定成“从某个 Start 到某个 End 的静态路径”。当蓝图变成多 Agent 协作系统后，入口和出口应该由框架运行时管理：

- 用户可以从顶层 Agent 发起任务。
- 用户可以从 UI 的开始按钮发起任务。
- 用户可以双击任意 AgentNode 单独下达局部任务。
- 顶层 Agent 可以根据任务动态选择多个启动节点。
- 蓝图可以因为全部任务完成、部分完成、冲突、超时、用户取消、顶层 Agent 调用结束接口而终止。

因此 Start / End 更适合作为框架运行态接口，而不是用户必须维护的普通节点。

### 4.3 顶层 Agent 要做的事

顶层 Agent 在启动任务前应完成以下步骤：

1. 调用框架接口读取组织架构信息：
   - 图结构。
   - Agent 列表。
   - 每个 Agent 的 skill / rule / 用户提示词摘要。
   - 每个 Agent 的输入输出边、可通信对象和执行模式。
2. 为每个 Agent 生成短小精炼的职责描述，例如：
   - “熟悉该项目网络模块，负责通信层代码修改与验证。”
   - “熟悉自媒体运营，负责文案撰写和口吻统一。”
   - “负责图像生成，偏向写实产品海报风格。”
3. 根据用户任务选择一个或多个启动节点。
4. 为每个启动节点生成任务字典。任务应包含：
   - 目标。
   - 必要上下文。
   - 输入资料位置。
   - 期望输出。
   - 验收条件。
   - 可以继续分发给哪些下游 Agent。
5. 调用框架开始接口，提交：
   - Agent 描述字典。
   - 启动节点列表。
   - 启动任务字典。
   - 用户原始目标摘要。
   - 本轮运行策略，例如是否允许并行、是否允许非阻塞后台任务、是否需要人工确认。

### 4.4 顶层 Agent 不应该做的事

顶层 Agent 不直接做以下事情：

- 不直接写项目工作目录。
- 不直接修改长期共享工作区。
- 不直接启动或杀掉底层 CLI 进程。
- 不绕过框架向普通 Agent 发送私信。
- 不把未校验的节点 id、文件路径、shell 命令透传给普通 Agent。
- 不自行判定蓝图已经成功结束；只能向框架提交“建议结束”或调用结束接口，由框架做最终状态聚合。
- 不把完整 raw stdout / stderr / 大段日志塞给用户或下游 Agent，只引用摘要和必要文件路径。

顶层 Agent 的权力应该大于普通 Agent，但仍受框架约束。它是协调者，不是 root shell。

### 4.5 顶层 Agent 的运行生命周期

顶层 Agent 不应该随每个普通 AgentNode 一起重复创建。推荐把它作为蓝图工程级的常驻协调入口：

1. 蓝图工程打开时，框架加载顶层 Agent profile，包括 rule、skill、组织摘要生成策略和可用接口列表。
2. 用户发起对话时，顶层 Agent 先读取当前组织架构快照，而不是复用旧图记忆。
3. 用户要求启动任务时，顶层 Agent 生成启动计划；框架校验通过后创建 run。
4. run 进行中，顶层 Agent 只通过状态查询接口、事件流和报告引用理解进度。
5. run 结束后，顶层 Agent 读取最终聚合状态和归档索引，向用户解释结果、风险和后续建议。

这意味着顶层 Agent 的“记忆”应分成两类：

- 对话记忆：用于理解用户偏好和本轮意图，可以由 GuLiCode 自身保留。
- 工程事实：图结构、Agent 状态、changeset、conflict、artifact、report、archive，必须以框架状态为准。

当两者冲突时，以框架事实为准。

### 4.6 顶层 Agent 与普通 Agent 的关系

顶层 Agent 可以理解所有普通 Agent 的职责，但不等于它可以直接控制所有普通 Agent 的内部上下文。推荐关系如下：

- 顶层 Agent 面向用户解释组织结构和运行状态。
- 顶层 Agent 给框架提交“启动计划、路由意图、结束建议、修复建议”。
- 框架把这些意图转换为普通 Agent 的消息队列、任务 manifest、Workspace API 上下文和事件。
- 普通 Agent 只接收与自己任务相关的上下文，不接收顶层 Agent 的完整内部推理。

顶层 Agent 可以建议“让 reviewer 等 coder 完成后再审查”，但不能绕过框架直接把 reviewer 的队列改成 running。它可以建议“要求 coder 修复冲突”，但冲突修复仍应通过框架生成的新任务或消息批次进入 coder 队列。

### 4.7 顶层 Agent 的最小上下文包

每次唤起顶层 Agent 时，框架建议提供一个压缩后的上下文包，而不是把全量日志塞进去：

```json
{
  "project": {
    "name": "GuLiCode workspace",
    "root_ref": "project_context",
    "active_blueprint": "main"
  },
  "organization_summary": {
    "agents": {
      "planner": "负责拆解任务和协调下游。",
      "coder": "负责代码实现和提交 changeset。",
      "reviewer": "负责测试、审查和风险报告。"
    },
    "connections": {
      "planner": ["coder", "reviewer"],
      "coder": ["reviewer"]
    },
    "valid_start_nodes": ["planner", "coder"]
  },
  "active_runs": [
    {
      "run_id": "run-20260508-001",
      "status": "running",
      "summary": "coder 正在执行，reviewer 等待 changeset。"
    }
  ],
  "available_interfaces": [
    "organization.read",
    "run.start",
    "run.status",
    "run.end"
  ]
}
```

这个上下文包的目标是让顶层 Agent 快速进入正确角色：它看到的是组织和控制台，不是底层 shell。

### 4.8 顶层 Agent 的输出分层

顶层 Agent 面向不同对象应输出不同层级的信息：

- 面向框架：结构化 JSON，例如启动计划、结束请求、修复建议、状态查询参数。
- 面向用户：自然语言摘要，说明当前判断、推荐动作和风险。
- 面向普通 Agent：不直接输出；需要通过框架生成任务或消息信封。

同一个判断可以同时有两份表达。例如用户说“开始做这个需求”，顶层 Agent 对用户说“我会让 coder 和 doc 并行启动，reviewer 等待它们完成后汇总”；对框架提交的则是严格 JSON 启动计划。

## 5. 框架对顶层 Agent 的约束与启迪

框架需要为顶层 Agent 维护独立的一份 `rule` 和 `skill`。这两份内容和普通 Agent 的 rule / skill 不同：顶层 Agent 关注的是组织认知、任务拆解、启动计划、状态解释和终止治理。

### 5.1 顶层 Agent 的 rule

rule 用来约束顶层 Agent 的行为，建议包含：

- 必须先读取最新组织架构，再生成启动计划。
- 必须为组织架构中的每个 Agent 生成职责描述；描述字典必须和 Agent 列表一一对应。
- 必须只选择存在于当前图结构中的启动节点。
- 启动任务字典必须和启动节点列表一一对应。
- 每个启动任务必须说明目标、上下文、输入、输出、验收条件和下游协作要求。
- 不得要求普通 Agent 绕过框架读写共享工作区或项目工作目录。
- 不得要求普通 Agent 直接向另一个 Agent 私下通信；通信必须走框架消息分发、Agent 队列或共享工作区引用。
- 不得把用户的宽泛目标原样丢给所有 Agent；必须按 Agent 职责拆成可执行任务。
- 不得向普通 Agent 暴露无关 Agent 的私有 scratch 路径、真实 skill 空间路径、token、RPC 密钥或内部实现细节。
- 用户问运行状态时，必须基于框架提供的运行状态、事件、manifest、changeset、conflict、artifact 和 report 来回答。
- 遇到冲突、失败、超时、权限不足时，必须说明当前状态、可选动作和推荐动作，不要假装已经解决。
- 调用结束接口前，必须说明结束原因，例如用户取消、全部完成、部分完成、无法继续、等待人工决策。
- 用户直接要求强制结束时，应调用框架结束接口，而不是继续调度新任务。

顶层 Agent 的输出应优先结构化。建议启动计划使用类似结构：

```json
{
  "agent_descriptions": {
    "agentA": "负责通信模块实现与单元测试。",
    "agentB": "负责接口文档和验收清单。",
    "agentC": "负责回归验证与风险报告。"
  },
  "start_nodes": ["agentA", "agentB"],
  "tasks": {
    "agentA": {
      "goal": "实现通信模块的重连策略。",
      "context_refs": ["reports/requirements.md"],
      "expected_output": "提交 changeset，并发布测试结果。",
      "acceptance": "相关测试通过，说明边界条件。"
    },
    "agentB": {
      "goal": "更新通信模块文档。",
      "context_refs": ["reports/requirements.md"],
      "expected_output": "发布文档草稿到 reports。",
      "acceptance": "覆盖新参数、新错误码和调用示例。"
    }
  },
  "run_policy": {
    "allow_parallel": true,
    "require_user_confirmation": false
  }
}
```

### 5.2 顶层 Agent 的 skill

skill 用来启迪顶层 Agent：让它知道框架能做什么，以及应该如何调用这些能力。建议包含：

- 组织架构读取接口：获取图结构、Agent 列表、边、端口、执行模式、skill / rule 摘要。
- 启动接口：提交 Agent 描述、启动节点、任务字典和运行策略。
- 状态查询接口：读取当前 run 的状态、事件、Agent 状态、队列、后台 job、changeset、conflict、artifact、report。
- 结束接口：请求结束、取消、失败归档或正常归档。
- 共享工作区接口：理解临时共享工作区和长期归档的区别，只通过逻辑接口引用产物。
- VCS-style 工作流接口：理解 `checkout -> edit -> status/diff -> submit -> sync`，知道代码修改不应通过普通 publish 乱写。
- 消息分发接口：理解普通 Agent 间消息由框架转发，框架维护每个 Agent 的可达下游、暂存消息和未投递状态；顶层 Agent 只提交路由意图或任务。
- UI 状态解释能力：把底层运行状态翻译成用户能理解的摘要。

顶层 Agent 的 skill 文档不需要塞入所有底层 CLI 细节，而是应该像“框架控制台说明书”：告诉它有什么按钮、什么接口、什么状态、什么不能越界。

### 5.3 框架对顶层 Agent 输出的校验

框架不能盲信顶层 Agent。开始接口必须校验：

- `agent_descriptions` 是否覆盖所有 Agent，且没有未知 Agent。
- `start_nodes` 是否存在，是否是可启动节点，是否满足当前图的控制流约束。
- `tasks` 是否和 `start_nodes` 对齐。
- 每个任务是否有目标、上下文、输出和验收条件。
- 任务中的文件引用是否位于允许范围内。
- 任务是否请求了越权 skill、越权目录、危险 shell 权限或未授权 Agent。
- 并行策略是否和 Agent 的 `execution_mode`、锁策略、写范围兼容。

如果校验失败，框架应把错误回调给顶层 Agent，让它修正启动计划，而不是静默失败。

### 5.4 框架给顶层 Agent 的启迪方式

框架可以主动给顶层 Agent 提供一份“组织摘要”，降低它每次从 raw graph 推理的成本：

```text
当前蓝图共有 5 个 Agent：
- planner：可接收用户目标，负责拆解计划，可向 coder/doc/reviewer 发消息。
- coder：负责代码修改，写范围 src/** 和 tests/**。
- doc：负责文档，写范围 docs/** 和 reports/**。
- reviewer：负责审查和测试，不直接改代码。
- artist：负责图片资产，写范围 artifacts/images/**。
```

这份摘要不是替代组织架构，而是给顶层 Agent 一个可读的“地图”。顶层 Agent 的智能应该用来做任务判断，而不是浪费在每轮重新猜图。

### 5.5 顶层 Agent profile 文件

建议把顶层 Agent 的配置落成独立 profile，而不是散落在 prompt 拼接代码里。最小结构可以是：

```json
{
  "agent_id": "gulicode",
  "display_name": "GuLiCode",
  "allowed_run_permissions": ["ask", "start", "status", "end"],
  "rule": "# GuLiCode Top Agent Rules\n...",
  "skill": "# GuLiCode Top Agent Framework Console\n..."
}
```

其中 `allowed_run_permissions` 必须由框架解释，而不是只写在自然语言里。自然语言 `rule` / `skill` 负责指导行为，结构化 permission 负责硬校验。

当前代码已落地 `GuLiCodeTopAgentProfile.from_dict()` / `load()` / `save()`，可以从 JSON profile 加载 `agent_id`、`display_name`、`allowed_run_permissions`、`rule` 和 `skill`。`runtime validate-start --top-agent-profile ...` 会使用该 profile 校验启动权限；`runtime top-agent-context --top-agent-profile ...` 会渲染顶层 Agent 可读的 profile + organization context。

### 5.6 rule / skill 的更新原则

顶层 Agent 的 rule / skill 应随框架接口演进而更新。推荐约定：

- 新增框架接口时，同时更新顶层 Agent skill，说明接口用途、输入、输出和失败语义。
- 新增安全边界时，同时更新顶层 Agent rule，说明哪些行为禁止。
- 修改普通 Agent 通信协议时，同时更新顶层 Agent skill，让它知道如何解释消息队列、暂存批次和剩余下游。
- 修改 Workspace API 或 VCS-style 流程时，同时更新顶层 Agent skill，避免它给普通 Agent 下达过时指令。

顶层 Agent 不应该依赖“记住上个版本的接口”。框架每次启动顶层 Agent 会话时，都应注入当前版本的 rule / skill 摘要和接口版本号。

### 5.7 框架给顶层 Agent 的纠错回路

当顶层 Agent 输出不合规时，框架应该把错误变成可修复反馈，而不是只返回 `invalid`。例如：

```json
{
  "ok": false,
  "error": "INVALID_START_PLAN",
  "issues": [
    {
      "field": "start_nodes",
      "message": "agentX 不存在于当前图结构。",
      "allowed_values": ["planner", "coder", "reviewer"]
    },
    {
      "field": "tasks.coder.acceptance",
      "message": "启动任务缺少验收条件。"
    }
  ],
  "retryable": true
}
```

顶层 Agent 收到这类反馈后，应修正原启动计划并重新提交。框架不应替它自动猜测缺失任务，也不应把部分有效计划悄悄启动。

### 5.8 顶层 Agent 的最小提示词骨架

顶层 Agent 的系统上下文建议包含固定骨架：

```text
你是 GuLiCode 顶层 Agent，是蓝图运行的全局协调者。

你可以：
- 读取组织架构。
- 生成启动计划。
- 查询运行状态。
- 请求暂停、取消、结束或归档。
- 向用户解释事件、changeset、conflict、artifact、report。

你不可以：
- 直接写项目文件。
- 绕过框架联系普通 Agent。
- 绕过 Workspace API 或 VCS-style changeset 流程。
- 假装未完成任务已经完成。
- 隐藏冲突、失败、超时或权限不足。

你的结构化输出必须能被框架校验。
```

这段骨架不替代详细 rule / skill，但能保证 GuLiCode 每次启动都站在正确的位置上。

## 6. 框架需要提供的核心接口

### 6.1 开始接口

提供给顶层 Agent 和 UI 开始按钮使用。

输入建议：

```json
{
  "user_goal": "用户原始目标摘要",
  "agent_descriptions": {
    "agentid1": "职责描述",
    "agentid2": "职责描述"
  },
  "start_nodes": ["agentid1", "agentid2"],
  "tasks": {
    "agentid1": {
      "goal": "任务目标",
      "context_refs": [],
      "expected_output": "期望输出",
      "acceptance": "验收条件"
    },
    "agentid2": {
      "goal": "任务目标",
      "context_refs": [],
      "expected_output": "期望输出",
      "acceptance": "验收条件"
    }
  },
  "run_policy": {
    "allow_parallel": true,
    "allow_nonblocking": true,
    "require_user_confirmation": false
  }
}
```

框架动作：

- 校验 Agent 描述、启动节点和任务字典。
- 创建 run。
- 将用户目标、启动计划、组织摘要写入运行 manifest。
- 将任务写入临时共享工作区的 reports 或 task manifest。
- 给对应启动节点投递第一条消息。
- 发出 `RunStarted`、`TaskQueued`、`AgentMessageQueued` 等事件。

当前非 UI 控制面已支持 `run.validate_start` / `run.start`，CLI 对应 `runtime validate-start` / `runtime start`。其中 `runtime validate-start` 支持 `--top-agent-profile`，可以加载持久化 GuLiCode 顶层 Agent profile 做权限和计划校验；`runtime start` 校验通过后会向 `start_nodes` 投递 `top_agent_task` 初始消息，并把 top-agent profile、start plan、organization snapshot、user goal 和 queued initial messages 记录到 runtime run manifest。有 `WorkspaceManifest` 和 `manifest_path` 时，也会写出 workspace JSON。

### 6.2 组织架构接口

提供给顶层 Agent 和普通 Agent 使用，但内容分级：

- 顶层 Agent 可看到全图、所有 Agent、所有边、职责摘要、当前运行状态，并自行选择启动节点。
- 普通 Agent 只看到与自己相关的组织视图：自己是谁、能向谁发消息、谁会向自己发消息、当前框架要求自己给哪些下游发消息、自己读写范围是什么。

组织架构返回建议：

```json
{
  "graph": {
    "nodes": ["agentA", "agentB", "agentC"],
    "edges": [
      {"from": "agentA", "to": "agentB", "edge_type": "exec"},
      {"from": "agentA", "to": "agentC", "edge_type": "exec"}
    ]
  },
  "agent_connections": {
    "agentA": ["agentB", "agentC"]
  },
  "agents": {
    "agentA": {
      "execution_mode": "blocking",
      "skills": ["coding"],
      "write_scope": ["src/**", "tests/**"]
    }
  },
  "start_policy": {
    "selected_by": "top_agent",
    "framework_role": "validate_only",
    "valid_start_nodes": ["agentA", "agentB", "agentC"]
  }
}
```

当前非 UI 入口已落地：

- Python API：`GraphDefinition.agent_organization_view()`、`scoped_organization_view()`。
- Control plane / RPC：`organization.read`。
- CLI thin client：`python -m multi_agent_tcp organization --graph ...` 或 `--rpc-url ...`。

顶层 Agent 上下文入口也已落地为 `top_agent.context` / `runtime top-agent-context`，用于一次性返回当前 profile 的 rule / skill / permissions 与最新组织架构视图。

### 6.3 状态查询接口

顶层 Agent 回答用户“现在跑到哪了”时，需要读框架状态，而不是凭对话猜测。

状态至少包含：

- run 生命周期状态：`created`、`running`、`paused`、`completed`、`failed`、`cancelled`。
- run 最终聚合状态：`success`、`partial_success`、`failed`、`cancelled`、`conflicted`、`timed_out`。
- Agent 状态：`idle`、`queued`、`dispatching`、`running`、`waiting_for_reply`、`processing_reply`、`failed`、`stopped`。
- 队列状态：每个 Agent 的 pending message、dispatching message id 和当前 message id。
- outgoing batch 状态：`required_target_node_ids`、`remaining_targets`、暂存消息、已投递 message id。
- join barrier 状态：policy、required sources、missing sources、贡献数量、成功贡献数量、聚合结果。
- 后台 job 状态：非阻塞任务的开始、完成、失败、超时。
- workspace 状态：jobs、artifacts、reports、accepted changesets、conflicts、archives。
- 最近事件：压缩后的事件流，供 UI 和顶层 Agent 总结。

当前本地核心已落地为 `GraphRuntime.status_snapshot()`。它可以附带 `GraphDefinition.agent_organization_view()`，因此同一个快照既能给顶层 Agent 做全局解释，也能给 UI 状态面板提供 run / Agent / queue / outgoing / join / workspace 的统一视图。`GraphRuntimeControlPlane`、`GraphRuntimeRPCServer` 和 `python -m multi_agent_tcp runtime status` 已提供非 UI 的 RPC / CLI 薄封装；后续 UI 只应消费这些接口，不应复制一套状态聚合逻辑。

### 6.4 结束接口

提供给顶层 Agent 和 UI 结束按钮使用。

结束不只有“成功结束”一种，建议支持：

- `complete`：正常完成。
- `cancel`：用户取消。
- `fail`：不可恢复失败。
- `pause`：保留现场，等待用户继续。
- `archive_only`：不再调度新任务，只归档已有结果。

结束接口必须由框架决定最终状态聚合。顶层 Agent 可以提出理由，但不能单方面覆盖未完成 job、未解决冲突或未提交 changeset。

当前本地核心已落地为 `GraphRuntime.end_run()` 和 `RunEndResult`：

- `complete`：将 run 生命周期置为 `completed`，再由框架计算最终聚合状态。
- `cancel`：将 run 生命周期置为 `cancelled`，最终状态为 `cancelled`。
- `fail`：将 run 生命周期置为 `failed`，最终状态为 `failed`。
- `pause`：将 run 生命周期置为 `paused`，不产生最终状态。
- `archive_only`：只记录归档动作，不改变当前生命周期状态。

`complete` 的最终状态由 `compute_final_status()` 决定：

- 有 timed-out join 或 Agent 超时：`timed_out`。
- 有未解决 conflict：`conflicted`。
- 有失败消息、失败 job 或 failed / disconnected Agent：`failed`。
- 有未完成消息、运行中 job 或等待中的 join，但已有 accepted changeset 或 completed job：`partial_success`。
- 无上述阻塞或风险：`success`。

`GraphRuntimeControlPlane`、`GraphRuntimeRPCServer` 和 `python -m multi_agent_tcp runtime end` 已提供非 UI 的 RPC / CLI 薄封装。当前 `cancel` / `fail` 已能取消未完成 dispatch task、queued / dispatching message、后台 job 和 waiting barrier；`complete` 已能生成 `shared/reports/final_report.json`，并在传入 workspace manager/run 时调用既有 `archive_run()` 写入长期归档 manifest；`archive_only` 也已接入同一归档索引路径。

### 6.5 Fan-in / join 接口

提供给框架调度器使用，普通 Agent 只提交结构化贡献，不直接决定汇聚节点是否继续执行。

当前本地核心已落地为 `JoinBarrier`、`JoinContribution`、`GraphRuntime.create_join_barrier()` 和 `GraphRuntime.submit_join_contribution()`。

支持策略：

- `wait-all`：等待所有 required sources 提交贡献后 ready。
- `wait-any`：任一 required source 提交贡献后 ready。
- `quorum`：达到指定成功贡献数后 ready。
- `timeout`：超过 barrier 的 timeout 后转为 `timed_out`。

贡献内容建议包含：

```json
{
  "join_id": "join-reviewer-001",
  "source_node_id": "coder",
  "source_agent_id": "worker-coder",
  "status": "completed",
  "result": {"summary": "实现已完成。"},
  "accepted_changesets": [{"changeset_id": "cs-001", "files": ["src/a.py"]}],
  "conflicts": [],
  "artifacts": [{"path": "artifacts/build.log"}],
  "reports": [{"path": "reports/coder.md"}],
  "test_results": [{"name": "unit", "status": "passed"}],
  "metadata": {"risk": "low"}
}
```

框架聚合结果应包含：

- required sources 与 missing sources。
- 每个 source 的状态、结果和 metadata。
- accepted changesets、conflicts、artifacts、reports、test results。
- policy、quorum、ready / timed_out 状态和 final reason。

约束：

- 非 required source 必须被拒绝。
- barrier ready、timed_out 或 cancelled 后，不能继续提交贡献。
- barrier ready 前，同一 source 可以覆盖贡献，框架记录 overwrite count。
- 汇聚 Agent 收到的是框架生成的聚合信封，而不是上游 Agent 之间的自由文本拼接。

`GraphRuntimeControlPlane`、`GraphRuntimeRPCServer` 和 `python -m multi_agent_tcp runtime join-create/join-contribute` 已提供非 UI 的 RPC / CLI 薄封装。当前运行时已支持：当 `create_join_barrier()` 获得目标 `AgentNode` 时，barrier ready 后框架会自动生成 `join_aggregate` 信封并放入汇聚 Agent 的消息队列，同时发出 `JoinBarrierAggregateQueued`。后续调度器应基于图上的多入边自动创建 fan-in barrier；timeout、conflict 和 partial completion 必须进入事件流和最终状态聚合。

### 6.6 消息分发接口

提供给普通 Agent 使用，顶层 Agent 只理解其状态，不直接替普通 Agent 调用。

输入建议：

```json
{
  "run_id": "run-001",
  "batch_id": "batch-agentA-001",
  "from": "agentA",
  "to": "agentB",
  "message": "请基于 reports/requirements.md 实现重连策略。",
  "context_refs": ["reports/requirements.md"],
  "allow_empty": true
}
```

框架动作：

- 校验 `from` / `to` 是否存在。
- 校验 `to` 是否属于当前消息信封的 `required_outgoing_targets`。
- 暂存消息，不立即投递。
- 如果同一 target 已暂存消息，则覆盖旧消息并记录 `overwritten=true`。
- 当所有 required targets 补齐后，统一提交批次到目标 Agent 队列。
- 产生 `AgentMessageStaged`、`AgentOutgoingBatchDispatched` 等事件。

返回建议：

```json
{
  "ok": true,
  "staged": true,
  "overwritten": false,
  "ready_to_dispatch": false,
  "remaining_targets": ["agentC"]
}
```

### 6.7 计划校验接口

开始接口可以内置校验，但仍建议提供一个单独的 dry-run 校验接口，供顶层 Agent 在向用户展示计划前自检。

输入与开始接口相同，但不创建 run、不投递消息。

返回建议：

```json
{
  "ok": true,
  "normalized_plan": {
    "start_nodes": ["coder", "doc"],
    "tasks": {}
  },
  "warnings": [
    "reviewer 未作为启动节点，将等待上游消息后运行。"
  ]
}
```

当计划无效时，返回 `issues`，格式同 5.7。这个接口可以让 GuLiCode 先把计划修到合格，再交给开始接口执行。

### 6.8 事件订阅接口

状态查询接口适合快照，事件订阅接口适合 UI 和顶层 Agent 做实时解释。

事件可以按 run、agent、task、workspace 过滤：

```json
{
  "run_id": "run-001",
  "after_event_id": "evt-120",
  "filter": {
    "agent_id": "coder",
    "types": ["AgentStateChanged", "ChangesetAccepted", "ConflictDetected"]
  }
}
```

返回建议：

```json
{
  "events": [
    {
      "event_id": "evt-121",
      "type": "ChangesetAccepted",
      "agent_id": "coder",
      "task_id": "task-coder-001",
      "changeset_id": "cs-003",
      "summary": "通信模块重连策略已合入 integration。"
    }
  ],
  "next_after_event_id": "evt-121"
}
```

UI 可以用事件流展示细节；顶层 Agent 可以用事件流生成自然语言摘要。

### 6.9 工作区与归档接口

顶层 Agent 不直接读物理目录，但需要能引用工作区成果。建议提供逻辑接口：

- `workspace.list_reports(run_id)`
- `workspace.read_report(run_id, path)`
- `workspace.list_artifacts(run_id)`
- `workspace.list_changesets(run_id)`
- `workspace.list_conflicts(run_id)`
- `archive.list(project_id)`
- `archive.extract(archive_id, path, target_agent_id)`

这些接口返回逻辑路径、摘要和引用，不返回可越权写入的真实目录。普通 Agent 如果需要读取历史归档，应由框架提取到它的私有空间。

### 6.10 接口形态建议

同一组核心接口最好同时有三种承载形态：

- Python API：供测试、内部运行时和本地集成使用。
- RPC / broker API：供长生命周期 UI、AgentNode 和跨进程运行时使用。
- CLI thin client：供普通 CLI-backed Agent 在工具调用能力有限时使用。

接口语义必须保持一致。CLI 只是 thin client，不应把核心逻辑复制一份到命令行脚本里。最终可信状态仍归框架运行时所有。

## 7. 框架对单一控制流运行机制的把控

框架需要合理使用 Codex CLI 输出字段：

- 主界面和下游 Agent 优先使用 `reply.body.codex.final_text`。
- `reply.body.codex.last_message` 可作为 `final_text` 的备选来源。
- `reply.body.codex.events` 适合结构化归档和 token / 阶段统计。
- `reply.body.codex.stdout` 适合 debug 和长期原始归档，不适合直接展示。
- `reply.body.codex.stderr` 只适合 debug 面板或错误摘要，应该过滤启动 warning、HTML 噪声、插件同步失败等大段无关内容。
- `usage`、`elapsed_sec`、`returncode`、`timeout` 适合进入运行 manifest 和性能统计。

标准结果视图建议压缩为：

```json
{
  "agent_id": "agentA",
  "node_id": "nodeA",
  "ok": true,
  "status": "success",
  "text": "最终可读结果",
  "elapsed_sec": 6.975,
  "usage": {
    "input_tokens": 12145,
    "cached_input_tokens": 5504,
    "output_tokens": 38,
    "reasoning_output_tokens": 27
  },
  "artifacts": [],
  "reports": [],
  "changesets": [],
  "conflicts": []
}
```

raw 字段只进入 debug 视图或归档：

```json
{
  "raw": {
    "stdout_ref": "logs/agentA/stdout.jsonl",
    "stderr_summary": "Codex plugin sync failed with HTTP 403; ignored for task result."
  }
}
```

### 7.1 一对多消息分发

例如图结构里存在：

```text
agentA -> agentB
agentA -> agentC
```

框架在运行时维护每个 Agent 可连接的下游 Agent 列表，例如：

```json
{
  "agentA": ["agentB", "agentC"]
}
```

agentA 不应该通过 `final_text` 自行约定 `agentB:` / `agentC:` 段落来触发转发，而应该调用框架提供的消息分发接口。接口调用可以是“一次给一个 Agent 暂存消息”，消息内容允许为空；框架负责校验目标、记录或覆盖暂存消息。框架随后实时监控 agentA 的状态；如果 agentA 已经回到 `idle`，但仍有下游没有补齐消息，框架再主动提醒 agentA 还需要给哪些下游发消息。

框架必须先拿到 agentA 面向全部下游的消息后，才把这些消息分发给对应 Agent。也就是说，在 agentA 只提交了给 agentB 的消息、还没有提交给 agentC 的消息时，框架不会立即把 agentB 的消息投递进 agentB 队列，而是先暂存在当前控制流步骤里。

框架在推送消息给 agentA 时，必须在消息信封中显式指定 agentA 本轮需要给哪些下游 Agent 发消息。这个列表来自当前图结构、控制流步骤和 join / switch 等运行策略；Agent 不应该自行从全图猜测本轮下游。

消息信封建议：

```json
{
  "to": "agentA",
  "message": "请处理 reports/requirements.md 中的通信模块需求。",
  "required_outgoing_targets": ["agentB", "agentC"],
  "allow_empty_outgoing_message": true
}
```

这里表示 agentA 本轮必须分别给 agentB 和 agentC 调用消息分发接口，消息内容可以为空。框架根据 `required_outgoing_targets` 初始化本轮暂存消息表和 `remaining_targets`。

建议接口语义：

```json
{
  "from": "agentA",
  "to": "agentB",
  "message": "请阅读 reports/requirements.md，并实现通信模块重连策略。"
}
```

框架处理后先暂存消息，并返回：

```json
{
  "staged": true,
  "overwritten": false,
  "ready_to_dispatch": false,
  "remaining_targets": ["agentC"]
}
```

如果此后 agentA 还没有给 agentC 调用消息分发接口，而框架监控到 agentA 已经回到 `idle`，框架再向 agentA 发送补齐提醒：

```json
{
  "staged": true,
  "overwritten": false,
  "ready_to_dispatch": false,
  "remaining_targets": ["agentC"]
}
```

如果 agentA 在补齐 agentC 前再次给 agentB 调用接口，框架允许覆盖之前暂存给 agentB 的消息：

```json
{
  "from": "agentA",
  "to": "agentB",
  "message": "请阅读 reports/requirements.md，并优先实现重连策略；完成后发布 changeset id。"
}
```

框架返回：

```json
{
  "staged": true,
  "overwritten": true,
  "ready_to_dispatch": false,
  "remaining_targets": ["agentC"]
}
```

如果 agentA 再调用一次接口给 agentC 发空消息：

```json
{
  "from": "agentA",
  "to": "agentC",
  "message": ""
}
```

框架应仍然记录 agentC 的空消息已被暂存，并返回：

```json
{
  "staged": true,
  "overwritten": false,
  "ready_to_dispatch": true,
  "remaining_targets": []
}
```

此时框架才把当前步骤中暂存的完整消息集合统一分发：

```json
{
  "agentB": "请阅读 reports/requirements.md，并优先实现重连策略；完成后发布 changeset id。",
  "agentC": ""
}
```

核心规则：

- 框架从图结构或运行 manifest 中维护 `agent_connections`，例如 `{agentA: [agentB, agentC]}`。
- 框架每次向 Agent 推送消息时，都必须显式携带 `required_outgoing_targets`；该字段表示该 Agent 本轮需要给哪些下游补齐消息。
- `required_outgoing_targets` 必须是该 Agent 在 `agent_connections` 中可达目标的子集；包含未知 Agent id 或不可达 Agent id 时，框架应在生成信封阶段拒绝。
- Agent 只能向本轮信封指定的 `required_outgoing_targets` 发消息；包含未知 Agent id、不可达 Agent id 或本轮未要求的 Agent id 时，框架拒绝调用并返回错误。
- 消息内容可以为空。空消息代表“该下游本轮收到空消息 / 只需继续检查上下文”，而不是跳过该下游。
- 每次成功调用后，框架都更新该 source Agent 在当前控制流步骤中的暂存消息表；接口调用本身不必同步返回 `remaining_targets`。
- 同一个 source Agent 在同一控制流步骤内，可以多次调用接口给同一个 target Agent 写消息；后一次调用覆盖前一次暂存消息。
- `remaining_targets` 是框架对 source Agent 的补齐提醒。只有当框架监控到 source Agent 已经回到 `idle`，且仍有 required target 没有暂存消息时，才需要把 `remaining_targets` 发给 source Agent。
- 只要 `remaining_targets` 不为空，框架就继续暂存消息，不向任何下游 Agent 队列投递这一组消息。
- 当 `remaining_targets` 变为空时，框架把该 source Agent 面向所有下游的暂存消息作为一个完整批次提交，并分别进入对应 Agent 的消息队列。
- 批次提交后，已分发消息不可再通过同一轮接口覆盖；如需修正，应进入新的控制流步骤或发起新的消息批次。
- 转发内容进入对应 Agent 的消息队列，而不是直接调用进程。

当前非 UI 控制面已有两层入口：

- 完整批次入口：`message.create_batch` / `message.stage`，CLI 对应 `runtime message-batch` / `runtime message-stage`，用于显式创建 outgoing batch、逐个 target 暂存消息，并在全部 target 补齐后自动分发。
- 普通 Agent 单步入口：`agent.dispatch`，CLI 对应 `runtime agent-dispatch`，用于校验 source / target 是否按图可达，创建单 target outgoing batch，暂存后立即进入下游队列。

`agent.dispatch` 是普通 Agent 工具接口的当前 MVP。它已经走框架运行时、图可达性校验和消息队列，不绕过调度器；但还没有绑定到当前任务信封中的 `required_outgoing_targets`，后续需要把它收敛到本轮 envelope / batch 上，而不是只按全图可达关系判断。

### 7.2 多对一消息汇聚

例如：

```text
agentB -> agentA
agentC -> agentA
```

框架应使用之前开发的 Agent 消息队列和 join 语义：

- 如果 agentA 空闲，可以按队列顺序投递。
- 如果 agentA 正在运行，消息进入 pending queue。
- 如果需要 fan-in，框架等待全部、任一、quorum 或超时，再把汇总消息投递给 agentA。
- 汇聚消息必须带来源元数据，避免 agentA 分不清哪个结果来自哪个 Agent。

### 7.3 消息分发不合规时的回调

当某个 Agent 调用消息分发接口不满足当前图结构要求时，框架不应自行猜测。推荐回调模板：

```text
你的消息分发请求无法按当前图结构执行。
当前节点 agentA 本轮需要发送消息给：agentB, agentC。
本轮还未补齐消息的下游是：agentC。

请重新调用框架消息分发接口，目标必须来自上述列表。
消息内容可以为空；空消息仍会作为该下游的本轮消息被暂存。
同一个目标可以重复调用，后一次会覆盖前一次暂存消息。

不要包含未知 agent id。
```

这一步是框架控制流治理的一部分，不应依赖 Agent 自觉，也不应依赖解析自由文本来判断是否已经通知下游。

## 8. 框架对每个普通 Agent 的约束与启迪

框架在拉起每个普通 Agent 时，需要给它指定一份 `rule` 和 `skill`。这两份内容应该随代码和接口一起维护，并存盘在项目目录中。

### 8.1 普通 Agent 的 rule

rule 规范普通 Agent 的行为：

- 所有关于共享工作区和项目工作目录的写操作必须通过框架接口实现。
- 代码修改优先走 VCS-style 流程：`checkout -> edit -> status/diff -> submit -> sync`。
- reports / artifacts 等非源码成果走 Workspace API 的 publish 流程。
- 所有 Agent 间通信必须通过框架接口、框架消息队列或共享工作区引用实现。
- 要将消息发给特定 Agent，必须调用框架消息分发接口，并指定目标 `agentid`；不能依赖自由文本里的 `agentid: message` 段落触发转发。
- `agentid` 不能省略，未知 `agentid` 或当前不可达的 `agentid` 不能出现。
- 当前轮次需要给哪些下游发消息，以框架推送消息信封中的 `required_outgoing_targets` 为准；普通 Agent 不应自行扩大或缩小这个列表。
- 消息内容可以为空；当框架在 Agent 回到 `idle` 后发送 `remaining_targets` 提醒时，必须继续补齐尚未提供消息的下游。
- 在本轮消息尚未分发前，可以再次给同一个下游调用接口并覆盖之前暂存的消息；一旦 `remaining_targets` 为空，框架会统一分发完整批次。
- 发给下游 Agent 的内容应尽量精简，优先引用共享工作区中的文件、报告、changeset、artifact。
- 不要把 raw stdout / stderr、大段日志、无关上下文直接转发给下游。
- 遇到冲突、权限不足、测试失败、信息不足时，明确返回状态和需要的下一步，不要编造成功。

### 8.2 普通 Agent 的 skill

skill 告知普通 Agent 自身与框架具备什么能力，约等于接口文档：

- 当前 Agent 的身份、职责、执行模式和本轮任务。
- 当前 Agent 在组织架构中的位置：上游、下游、可通信对象、不可通信对象，以及当前消息信封指定的 `required_outgoing_targets`。
- 当前 Agent 的读范围、写范围、artifact 范围和锁策略。
- 临时共享工作区、长期归档和私有 scratch 的区别。
- Workspace API 的读写方法。
- VCS-style changeset 的代码协作方法。
- 如何发布 reports / artifacts。
- 如何声明测试结果、风险、后续任务和阻塞项。
- 如何调用消息分发接口给 `required_outgoing_targets` 中的下游 Agent 暂存消息，如何覆盖尚未分发的暂存消息，以及如何根据 `remaining_targets` 补齐尚未提供消息的下游。

组织结构视图建议保持简洁，例如：

```text
你是 agentB。

当前组织结构：
agentA -> agentB -> agentD
agentA -> agentC -> agentD

你的上游：
- agentA：会给你分配实现任务和上下文引用。

你的下游：
- agentD：会接收你的实现摘要、changeset id 和测试结果。

你的写范围：
- src/network/**
- tests/network/**
```

## 9. 共享工作区与项目工作目录规则

建议继续采用当前 multi_agent_tcp 的工作区分层：

```text
<project>/.multi_agent_workspace/
  shared/
    archives/
  runs/
    active/<run_id>/
      base/
      integration/
      shared/
        artifacts/
        reports/
      agents/<agent_id>/private/
        checkout/
        state/base/
      changesets/
      conflicts/
      run_manifest.json
```

规则：

- `base/` 是运行开始时的项目快照。
- `integration/` 是框架维护的本轮集成视图。
- `agents/<agent_id>/private/` 是 Agent 私有目录，用于 scratch、cache、CLI state 和授权 skill view。
- Agent 代码修改发生在私有 checkout 中，提交给框架后由框架 merge 到 integration。
- `shared/artifacts` 和 `shared/reports` 是本轮成果区。
- 长期共享空间只保存归档、manifest、历史成果索引，不允许 Agent 直接写。

代码协作推荐流程：

```text
checkout
  -> agent 在私有 checkout 修改
  -> status / diff
  -> submit changeset
  -> accepted 或 conflict
  -> conflict 时 sync + repair + resubmit
```

这能避免多个 Agent 直接改同一个项目工作目录时互相覆盖。

## 10. 事件与状态模型

框架应把关键动作写成事件，供 UI、顶层 Agent 和归档使用：

- `RunStarted`
- `RunPaused`
- `RunCancelled`
- `RunCompleted`
- `RunArchived`
- `RunEnded`
- `AgentStarted`
- `AgentStateChanged`
- `AgentMessageStaged`
- `AgentOutgoingTargetsReminder`
- `AgentMessageQueued`
- `AgentMessageDispatched`
- `AgentQueuedMessageDispatched`
- `AgentQueuedMessageCompleted`
- `AgentReplyReceived`
- `AgentOutgoingBatchCreated`
- `AgentOutgoingBatchDispatched`
- `JoinBarrierCreated`
- `JoinContributionSubmitted`
- `JoinBarrierReady`
- `JoinBarrierAggregateQueued`
- `JoinBarrierTimedOut`
- `JoinBarrierCancelled`
- `TaskStarted`
- `TaskCompleted`
- `TaskFailed`
- `TaskCancelled`
- `CheckoutCreated`
- `ChangesetSubmitted`
- `ChangesetAccepted`
- `ConflictDetected`
- `CheckoutSynced`
- `ArtifactPublished`
- `ReportPublished`
- `ReviewRequested`
- `RunPendingWorkCancelled`

说明：当前 `GraphRuntime.end_run()` 的本地实现统一发出 `RunEnded`，其中 `status` 字段承载最终聚合状态；`pause` 发出 `RunPaused`，`archive_only` 发出 `RunArchived`。`RunCancelled` / `RunCompleted` 可以作为后续 RPC、UI 或归档层的语义化事件名，但不应和运行时核心状态相互矛盾。

顶层 Agent 回答用户状态问题时，应基于这些事件生成摘要，例如：

```text
当前运行还在进行中。coder 已提交 changeset cs-003 并通过测试；doc 正在更新文档；reviewer 等待 coder 和 doc 的结果后开始汇总。目前没有未解决冲突。
```

## 11. UI 交互建议

UI 应同时支持用户直接控制和顶层 Agent 间接控制：

- 开始按钮：用户直接启动蓝图，框架可使用默认启动节点或弹出启动计划确认。
- 结束按钮：用户强制结束或请求归档当前结果。
- 顶层 Agent 对话入口：用户用自然语言描述任务、查询状态、要求暂停或继续。
- AgentNode 双击对话：用户直接给某个具体 Agent 下达局部任务。
- 运行状态面板：展示 run 状态、Agent 状态、队列、changeset、conflict、artifact、report。
- Debug 面板：展示 raw stdout / stderr / events，但默认折叠。

UI 不应该要求用户理解所有底层运行细节。顶层 Agent 和状态面板共同把复杂的运行时变成可解释的协作过程。

## 12. 落地优先级

建议按以下顺序推进：

1. 顶层 Agent 的 rule / skill profile JSON 格式已落地，并可通过 `--top-agent-profile` 加载。
2. 组织架构接口已落地，可返回全图、Agent 列表、边、scope 和普通 Agent scoped view。
3. 开始接口已支持顶层 Agent 提交 `TopAgentStartPlan`、向 start nodes 投递初始任务，并记录 run start manifest。
4. 启动计划校验已落地：Agent 描述、启动节点、任务字典、权限范围。
5. Agent 消息队列和消息分发接口已接入；完整 batch/stage 与 `agent.dispatch` 已可通过非 UI control plane / RPC / CLI 使用，并且普通 Agent 分发已经绑定到当前任务信封的 `required_outgoing_targets`。
6. 统一 Codex 结果视图，压缩 raw 输出，保留 debug 引用。
7. 状态查询接口运行时核心与非 UI RPC / CLI 薄封装已完成；`explain-status` / `top_agent.explain_status` 已提供顶层 Agent 可消费的事件化状态解释，后续 UI 只消费同一接口。
8. 结束接口和最终状态聚合运行时核心与非 UI RPC / CLI 薄封装已完成；`cancel` / `fail` 已能收口未完成消息、job 和 waiting join；`complete` / `archive_only` 已接最终报告与归档索引。
9. fan-in / 状态查询 / 结束接口的 RPC / CLI thin client 已完成；barrier ready 后聚合信封投递已完成；图调度器也已能从多输入 exec 边自动创建 barrier。
10. 普通 Agent 启动/消息上下文已注入当前任务信封、可达下游和 `agent.dispatch` 工具说明；每轮消息携带 `framework_context`，其中包含 `outgoing_batch_id`、`required_outgoing_targets` 和 `remaining_targets`。
11. 长生命周期 GuLiCode 顶层 Agent 会话已接入控制面：profile 可映射为 `AgentNode`，并可通过 `top_agent.start_session` / `top_agent.ask` 与同一运行时 worker 交互。
12. 在 UI 中展示顶层 Agent、运行状态、changeset、conflict 和 artifacts；UI 后续再开发。

## 12.1 当前开发进度标记（2026-05-08）

已完成：

- 第 5 步中的一对多消息分发运行时 MVP 已落地到 `multi_agent_tcp.graph_runtime.GraphRuntime`。
- 框架现在可以创建 `OutgoingMessageBatch`，为 source Agent 维护 `required_target_node_ids` / `remaining_targets`。
- 普通 Agent 提交给下游的消息先进入暂存表，不会立即调用下游 Agent。
- 同一 target 在批次分发前允许覆盖暂存消息。
- 空消息会被视为该 target 已补齐，而不是跳过该 target。
- 当 source Agent 回到 `idle` 且仍有 target 未补齐时，框架会发出 `AgentOutgoingTargetsReminder` 事件。
- 当全部 required targets 补齐后，框架一次性把该批次分别加入下游 Agent 的消息队列。
- 批次投递复用现有 `queue_agent_message()` 和 tick 调度机制；也就是说，消息进入目标 Agent 队列后，仍由框架按 idle 状态逐帧 dispatch。
- 新增事件覆盖：`AgentOutgoingBatchCreated`、`AgentMessageStaged`、`AgentOutgoingTargetsReminder`、`AgentOutgoingBatchDispatched`。
- 已补测试覆盖：一对多完整批次、覆盖、空消息、非法 target 拒绝、allowed target 校验、idle 后补齐提醒。
- `GraphDefinition.agent_connections()` 已能从 `exec` 边自动生成 Agent 到 Agent 的直接可通信关系；`data` 边、Start/End 等 terminal 边不会误入普通 Agent 通信关系。
- `GraphDefinition.agent_organization_view()` 已提供初版组织视图，包含 graph、agents、agent_connections、start_policy，可作为后续顶层 Agent 组织架构接口的本地核心；启动点由顶层 Agent 显式提交，框架只负责校验。
- `GraphRuntime.create_outgoing_batch_from_graph()` 已能基于图结构创建 outgoing batch，并用图上的可通信关系校验 required targets。
- `GuLiCodeTopAgentProfile` 已提供顶层 Agent 的 rule / skill 文本骨架、organization context、JSON `from_dict()` / `load()` / `save()`，明确 GuLiCode 是全局协调者，不是无限权限执行者。
- `TopAgentStartPlan` / `TopAgentTask` / `TopAgentPlanValidation` 已落地，框架可以校验顶层 Agent 提交的启动计划：agent 描述必须覆盖所有 Agent，start_nodes 必须显式存在且来自当前 AgentNode，tasks 必须与 start_nodes 对齐，每个任务必须有 goal、expected_output、acceptance。
- 多对一 fan-in / join 运行时核心已落地：`JoinBarrier`、`JoinContribution`、`GraphRuntime.create_join_barrier()`、`GraphRuntime.submit_join_contribution()`。
- join 支持 `wait-all`、`wait-any`、`quorum` 和 `timeout`；可以聚合 source metadata、accepted changesets、conflicts、artifacts、reports 和 test results；非 required source 会被拒绝，ready / timed_out 后不能继续提交贡献。
- `GraphRuntime.status_snapshot()` 已落地，可返回 run、Agent、queue、outgoing batch、join barrier、job、recent events、workspace 和可选 organization view。
- `RunEndResult`、`GraphRuntime.end_run()`、`GraphRuntime.compute_final_status()` 已落地，支持 `complete`、`cancel`、`fail`、`pause`、`archive_only`，并区分 `success`、`partial_success`、`failed`、`cancelled`、`conflicted`、`timed_out`。
- 非 UI 控制面基础已落地到 `graph_control.py`：`graph_definition_from_dict()`、`load_top_agent_profile()`、`scoped_organization_view()`、`GraphRuntimeControlPlane`、`GraphRuntimeRPCServer`。
- 控制面命令已覆盖 `organization.read`、`top_agent.context`、`run.validate_start`、`run.start/status/end`、`message.create_batch`、`message.stage`、`agent.dispatch`、`join.create`、`join.contribute`。
- CLI thin client 已落地：`organization`、`runtime validate-start`、`runtime top-agent-context`、`runtime start/status/end`、`runtime message-batch/message-stage`、`runtime agent-dispatch`、`runtime join-create/join-contribute`。
- run start manifest 已落地：`GraphRuntime.record_start_manifest()` 会记录 top-agent profile、start plan、organization snapshot、user goal 和 queued initial messages；`status_snapshot()["run"]["manifest"]` 可查询，有 `WorkspaceManifest` 和 `manifest_path` 时可写出 workspace JSON。
- fan-in barrier ready 后自动投递聚合信封已落地：目标 Agent 队列会收到 `join_aggregate` 消息，事件流会记录 `JoinBarrierAggregateQueued`。
- `cancel` / `fail` 收口已落地：queued / dispatching messages、未完成 jobs 和 waiting joins 会被取消，并发出 `AgentQueuedMessageCompleted`、`TaskCancelled`、`JoinBarrierCancelled`、`RunPendingWorkCancelled` 等事件。
- `GraphExecutor.run_blueprint()` 已从单一路径 runner 升级为顺序 DAG runner：节点等待所有 exec 上游完成，多 Agent 上游自动创建 fan-in barrier，并把 `join_aggregate` 投递给汇聚 Agent。
- `complete` / `archive_only` 归档索引已落地：`complete` 生成 `shared/reports/final_report.json`；传入 workspace manager/run 时会调用既有 `archive_run()`，并写入 long-term archive manifest。
- `GuLiCodeTopAgentProfile` 已扩展为可运行 profile，包含 `cli_kind`、`model`、`cwd`、`timeout_sec`、`command`、`adapter_options`、`extra_env`、`external`，并可通过 `to_agent_node()` 映射成长生命周期 GuLiCode worker。
- `GraphRuntimeControlPlane` 已支持 `top_agent.start_session` / `top_agent.ask` / `top_agent.explain_status`，CLI thin client 对应 `runtime top-agent-start-session` / `runtime top-agent-ask` / `runtime explain-status`。
- `GraphRuntime.explain_status()` 已落地，可把 run、Agent 状态、队列、outgoing batch、join、job、workspace 和最近事件压缩成顶层 Agent 可解释的状态摘要、风险和推荐动作。
- 普通 Agent 的 `framework_context` 注入已落地：`ordinary_agent_framework_context()` 与 `inject_framework_context()` 会把 scoped organization、当前消息信封、可达下游、`agent.dispatch` 用法和约束写入每轮消息 context。
- `agent.dispatch` 已收敛到当前 outgoing batch：调用必须携带 `batch_id`，source 必须匹配 batch owner，target 必须属于该 batch 的 `required_target_node_ids`；不再只按全图可达关系临时创建一跳分发。
- `run.start` 会为带下游的 start node 创建本轮 outgoing batch，并把 `required_outgoing_targets` / `remaining_targets` 注入初始 `top_agent_task` 消息。
- `agent.context` / `runtime agent-context` 已落地，用于读取普通 Agent 当前 batch 的工具上下文，便于真实 AgentNode 或外部 worker 在启动/恢复时获取同一份约束。

当前验证：

```text
python -m pytest test_agent_runtime.py test_graph_control.py -q
59 passed

python -m pytest test_graph_control.py test_agent_runtime.py test_workspace_api.py test_workspace_manager.py -q
94 passed

python -m pytest test_graph_control.py -q
5 passed

python -m py_compile graph_runtime.py graph_control.py __main__.py __init__.py
```

仍未完成：

- UI 状态展示暂不开发；后续 UI 只应消费现有 `status_snapshot()` / `explain_status()` / RPC thin client，不再复制状态聚合逻辑。
- 真实 GuLiCode / Codex CLI 长会话的底层 adapter 仍是“长生命周期 worker 边界 + 每条消息调用 CLI”的兼容形态；如果后续 CLI 支持真正交互式 session，可在 adapter 内替换实现而不改变控制面协议。
- 普通 Agent 的 `framework_context` 已进入消息信封，但还需要和真实 AgentNode 启动 prompt / skill 注入链路做端到端联调，确认各 CLI adapter 都能稳定消费 `context` 字段。
- 权限收敛仍可继续加强：`agent.dispatch` 已按 batch 收敛，后续可把 workspace/VCS API、artifact/report publish API 也统一绑定到当前任务信封和 Agent scope。

## 13. 当前结论

顶层 Agent 应该是“全局协调者”，但不应该成为“无限权限执行者”。框架给它组织架构、接口和状态，让它做理解、拆解、解释和建议；框架自己保留调度、校验、写入、转发、冲突、归档和终止的最终控制权。

普通 Agent 只处理局部任务。Agent 之间看起来在通信，实际上所有通信都经过框架承载。这样才能让多 Agent 蓝图既有智能协作的弹性，又有工程系统需要的可观测、可恢复、可归档和可约束。
