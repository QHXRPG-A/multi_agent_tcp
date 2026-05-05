---
name: multi-agent-tcp
description: >-
 Orchestrates multiple CodeMaker CLI workers over TCP via CodeMakerCluster,
 AgentsRegistry, broker batch_gather, show-registry/dispatch flows, and
 skill catalog injection. Use when working with multi_agent_tcp, CodeMaker
 multi-agent clusters, agents_registry.json, registry-ui, or TCP orchestration
 between Cursor and CodeMaker CLI workers.
---
# multi_agent_tcp —让 Cursor/CodeMaker 与多个 CodeMaker CLI交互的编排框架

> **框架核心目的**：让 Cursor（或 CodeMaker 等 AI 编码助手）能**同时与多个 CodeMaker CLI 实例交互**——并行分发任务、串行链式协作、聚合多路结果。Cursor/CodeMaker 与多 CodeMaker CLI 的交互是本框架的**重中之重**，所有底层组件（Broker、TCP 协议、进程管理）都服务于这一目标。

## 当前定位

- **定位**：Cursor（或任何 Python 调用者）通过一个 `CodeMakerCluster` 对象管理一组 CodeMaker CLI worker 进程，以并行或串行方式提交任务并拿聚合结果。
- **代码根路径**：当前工作区通常为 `d:\agents\multi_agent_tcp\`；历史环境也可能位于 `f:\src\Package\Script\Python\multi_agent_tcp\`。编写命令时以当前本机实际路径为准。
- **维护范围**：用户若说「只更新 Cursor skill」，仅修改本目录下的文档；`.codemaker/skills/multi-agent-tcp/SKILL.md` 为另一份拷贝，需另行同步。

## 文档结构

### 1. `SKILL.md`

只保留：
- 当前有效的高层方法
- 关键规则
- 入口索引
- 模块文档、任务文档与归档文档引用

### 2. `knowledge_base/`

模块知识库目录。不同模块分别记录在独立知识文档中，只保存当前有效知识，不承担历史变更流水。

- [`knowledge_base/README.md`](knowledge_base/README.md)：知识库索引
- [`knowledge_base/core_architecture.md`](knowledge_base/core_architecture.md)：主架构、组件与协议入口
- [`knowledge_base/cluster_api.md`](knowledge_base/cluster_api.md)：`CodeMakerCluster` API 与生命周期
- [`knowledge_base/registry_and_skills.md`](knowledge_base/registry_and_skills.md)：registry、skill 合并、catalog 注入
- [`knowledge_base/dispatch_workflows.md`](knowledge_base/dispatch_workflows.md)：`show-registry` / `dispatch` / async / legacy workflow
- [`knowledge_base/cli_reference.md`](knowledge_base/cli_reference.md)：CLI 速查
- [`knowledge_base/runtime_notes.md`](knowledge_base/runtime_notes.md)：重试、编码、心跳、日志、`codemaker run` 易错点
- [`knowledge_base/multi_cli_workflow.md`](knowledge_base/multi_cli_workflow.md)：多 CLI 接入、节点工作流、`CLIAdapter`、`MultiModalEnvelope` 等近期方向性知识
- [`knowledge_base/vendor_ryven_ui.md`](knowledge_base/vendor_ryven_ui.md)：vendored `Ryven` / `ryvencore_qt` 的节点外观、视觉层与启动入口知识
- [`knowledge_base/agent_node_ryven_integration.md`](knowledge_base/agent_node_ryven_integration.md)：`AgentNode` 接入 Ryven 节点 UI、Start/End 机制、删除保护与 runnable graph 校验
- [`knowledge_base/blueprint_gap_notes.md`](knowledge_base/blueprint_gap_notes.md)：对标 UE5 蓝图时的类型系统、编辑效率与信息密度改进方向

知识文档之间允许直接交叉引用；新增模块时优先在 `knowledge_base/` 中新建对应文档，再从本文件挂入口。

### 3. `tasks/`

短期任务目录。用于沉淀最近要推进的工程目标、任务拆解和阶段性执行清单，不承担长期知识沉淀。

- [`tasks/README.md`](tasks/README.md)：任务目录说明
- [`tasks/current_goals.md`](tasks/current_goals.md)：当前短期目标总览
- [`tasks/multi_cli_adapter_tasks.md`](tasks/multi_cli_adapter_tasks.md)：多 CLI adapter 方向任务
- [`tasks/node_runtime_tasks.md`](tasks/node_runtime_tasks.md)：节点运行时与图编译方向任务
- [`tasks/vendor_ryven_tasks.md`](tasks/vendor_ryven_tasks.md)：vendored Ryven / UI 改造方向任务

### 4. `archive/`

历史变更归档目录。每个 `*_archive.md` 只负责记录某一方向的变更，便于回顾；不再使用总归档文件。

- [`archive/agents_architecture_archive.md`](archive/agents_architecture_archive.md)：多 agent 主架构、dispatch、registry、cluster、CLI 演进历史
- [`archive/blueprint_integration_archive.md`](archive/blueprint_integration_archive.md)：Ryven / 蓝图 / vendor GUI 方向变更历史
- [`archive/gulicode_runtime_baseline_archive.md`](archive/gulicode_runtime_baseline_archive.md)：GuLiCode / OpenCode 运行基线方向变更历史

## 推荐使用方式

### 先看高层入口，再按需深入

1. 先读本文件确认问题属于：主架构、cluster API、registry/skills、dispatch、CLI、运行时注意事项、节点工作流、vendor UI，还是短期任务推进。
2. 再进入 `knowledge_base/` 或 `tasks/` 对应文档。
3. 若需要回顾历史决策、迁移过程或某方向演进，再读取 `archive/` 中对应的 `*_archive.md`。

### 常见查询映射

- 问主架构：看 `knowledge_base/core_architecture.md`
- 问 `CodeMakerCluster`：看 `knowledge_base/cluster_api.md`
- 问 `agents_registry.json` / skill 注入：看 `knowledge_base/registry_and_skills.md`
- 问 `show-registry` / `dispatch` / async：看 `knowledge_base/dispatch_workflows.md`
- 问命令怎么写：看 `knowledge_base/cli_reference.md`
- 问运行时陷阱：看 `knowledge_base/runtime_notes.md`
- 问多 CLI / 节点工作流方向：看 `knowledge_base/multi_cli_workflow.md`
- 问 Ryven / `ryvencore_qt` 视觉层或启动方式：看 `knowledge_base/vendor_ryven_ui.md`
- 问 `AgentNode` 如何接入 Ryven 节点 UI、Start/End 如何自动创建或如何保护不可删除：看 `knowledge_base/agent_node_ryven_integration.md`
- 问蓝图差距与改进点：看 `knowledge_base/blueprint_gap_notes.md`
- 问最近要做什么：看 `tasks/*.md`
- 问历史变更：看 `archive/*.md`

## 归档与维护规则

### 知识库更新

- 当前有效知识优先更新到 `knowledge_base/` 对应模块文档。
- `SKILL.md` 只做导航，不重复承载大量细节。
- 若一个知识点跨多个模块，可在模块文档之间直接交叉引用。
- 来自 `KM_docs` 的方向性内容，只有在适合作为长期参考时才进入知识库；仍属近期推进清单的内容优先进入 `tasks/`。

### 任务目录更新

- 短期目标、阶段性推进项、待做清单统一更新到 `tasks/`。
- `tasks/` 记录的是“最近要推进什么”，不是长期知识库，也不是历史归档。
- 当某项方向沉淀为稳定方法后，应转写到 `knowledge_base/`；当某轮工作需要回顾演进过程时，再追加到 `archive/`。

### 历史归档更新

当用户明确要求「归档」或要沉淀长期历史时：
- 不再新建或恢复总 `ARCHIVE.md`
- 只把历史变更追加到 `archive/` 下对应主题的 `*_archive.md`
- 若是新方向，新增一个新的 `*_archive.md`
- 归档文档只记录变更与阶段性结论，当前有效方法仍应同步回 `knowledge_base/`

### multi_agent_tcp 方向特别说明

- 若用户要求启动或汉化 Ryven GUI，优先查看 `knowledge_base/vendor_ryven_ui.md`、`knowledge_base/agent_node_ryven_integration.md` 与 `archive/blueprint_integration_archive.md`。
- 若用户要求处理 GuLiCode / OpenCode 运行基线，优先查看 `archive/gulicode_runtime_baseline_archive.md`。
- 若用户要求多 agent 编排、dispatch、registry、cluster、registry-ui 等主能力，优先查看 `knowledge_base/` 与 `archive/agents_architecture_archive.md`。
- 若用户要求梳理多 CLI、节点化工作流、多模态消息等近期方向，优先查看 `knowledge_base/multi_cli_workflow.md` 与 `tasks/`。

## 外部与仓库关联

- GitHub 仓库：<https://github.com/QHXRPG-A/multi_agent_tcp>
- `multi_agent_tcp/` 是常见代码仓根目录；本 skill 文档目录与代码仓可能不是同一 git 范围。
- 用户若说「只更新 Cursor」，默认仅维护本 skill 目录，不改代码仓或 `.codemaker` 副本。
