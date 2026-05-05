# 多 CLI 接入与节点工作流

本文件整理 `multi_agent_tcp` 在多 CLI agent、节点化编排与多模态消息方面的近期方向性知识。它记录的是当前已明确的设计方向与术语，不等价于“功能已实现”。

## 定位

根据 [D:\agents\multi_agent_tcp\KM_docs\multi-cli-node-workflow-brainstorm.md](D:\agents\multi_agent_tcp\KM_docs\multi-cli-node-workflow-brainstorm.md)，项目正在从“围绕 CodeMaker CLI 的薄编排框架”扩展为：

- 多 CLI agent 接入
- 节点化工作流编排
- 多模态消息总线
- headless 优先的运行时设计

这条线与当前主架构并不冲突，而是其上层扩展方向。

## 关键方向

### 1. CLIAdapter 抽象

当前 `codemaker_bridge.py` 是唯一已落地的 CLI adapter 形态。后续方向是抽出一层薄的 `CLIAdapter`：

- 只负责进程 IO、prompt 传递、输出解析、附件落地
- 不负责 LLM 推理、tool routing、对话历史管理
- 保持 `WorkerResult` / `ParallelResult` / `ReduceResult` 这一套统一结果视图

目标不是“模型抽象层”，而是“CLI 进程适配层”。

### 2. 节点化工作流

在现有 `run_parallel` / `run_chain` / `run_single` 之上，近期方向是把 agent 协作与消息处理建模成图：

- Agent 节点：声明并绑定一个长生命周期 CLI agent 实例；第一次经过该节点时启动或绑定实例，之后同次图运行中再次经过该节点时复用该实例发送消息
- 处理节点：模板填充、字段抽取、格式转换
- 路由节点：fan-out、fan-in、switch
- I/O 节点：文件、HTTP、blob 等外部交互

这意味着图编译器未来不能把 Agent 节点理解为“一次性 CLI 调用”。它应先生成图运行期的 `node_id -> agent_instance/session` 映射，再把每次节点经过编译为对已绑定 agent 的消息发送：

- 单 Agent 节点：ensure/bind 该实例，然后按 `cluster.run_single(...)` 风格发送本次消息
- fan-out：ensure/bind 多个实例，然后按 `cluster.run_parallel(...)` 风格并行发送消息
- 线性链：ensure/bind 链上实例，然后按 `cluster.run_chain(...)` 风格传递消息
- fan-out + reduce：ensure/bind fan-out 与 reduce 实例，然后按 `cluster.run_parallel_reduce(...)` 风格汇聚
- 更远期的 DAG 执行入口

Agent 实例生命周期由 GraphRuntime 管理：首次经过节点时创建或绑定，循环/反馈路径再次经过时复用，整张蓝图运行结束、取消或失败收尾时统一销毁本次运行创建的实例；挂接外部已有 agent 时只解除绑定，不擅自关闭外部进程。

Agent 节点还需要区分两种执行模式：

- 阻塞 AgentNode：触发后阻塞当前执行分支，等待本轮消息结果后再决定当前分支继续、失败或改道；它不阻塞其它并行分支。适合审批、评审、计划、汇总、质量门禁、是否继续执行等对当前分支有盖棺定论影响的节点。
- 非阻塞 AgentNode：触发后启动或复用 agent 实例并提交后台任务，当前执行分支立即继续；该节点完成后通过事件反馈给蓝图，例如 `AgentTaskCompleted` / `AgentTaskFailed`，相关节点再根据事件和共享工作区 manifest 查找修改与产物。适合模块开发、长任务执行、后台调研、生成资产、并行验证等短期内不要求当前分支等待结果的任务。

因此 AgentNode 的配置应包含 `execution_mode: blocking | nonblocking`。阻塞模式的输出走当前执行线，非阻塞模式的直接输出主要是 `job_ref` / `agent_ref` / `workspace_ref`，最终结果通过事件总线与共享工作区回流。

共享工作区应被视为多 Agent 协作的 blackboard，而不是普通临时目录。它至少包含：

- 物理文件空间：源码、产物、日志、临时文件、manifest。
- 任务账本：每个后台任务完成时写入 job manifest，记录 `job_id`、`node_id`、`agent_id`、状态、改动文件、产物、摘要、风险与测试。
- 事件流：非阻塞 AgentNode 发出 `TaskStarted`、`TaskProgress`、`TaskCompleted`、`TaskFailed`、`WorkspaceChanged`、`ReviewRequested` 等事件。
- 写入边界：每个 AgentNode 声明 `read_scope`、`write_scope`、`artifact_scope`、`lock_policy`、`merge_policy`，避免多个后台 agent 覆盖彼此改动。

### 3. MultiModalEnvelope

为避免每加一种媒体都扩端口模型，近期方向统一为一种多模态信封：

- `kind`: `text` / `image` / `audio` / `file` / `blob`
- `mime`
- `encoding`: `inline` / `fileref` / `blobref`
- `value`
- `meta`

其作用是统一节点间边上传递的数据容器，而不是让每条边都绑定一种硬编码类型。

### 4. 多模态数据面

近期路线强调渐进扩展：

1. 先支持 text 与小图的 inline / 临时文件落地
2. 再引入 blob store 与 `blob_put` / `blob_get`
3. 未来如有必要，再考虑更重的跨机二进制传输方案

## 当前代码落地状态（2026-05-03）

### CLI adapter 与 Codex 落地状态

`adapter spike` 指“正式实现某个 CLI adapter 之前的事实确认清单与最小探针”。Codex 的第一轮 spike 已转化为最小真实 adapter；后续 spike 仍用于确认其它 CLI 是否支持非交互调用、prompt 输入方式、结构化输出、cwd/env、附件、超时、取消和会话复用。

当前本机事实：

- Codex CLI 存在于 `C:\Users\a\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe`，版本输出为 `codex-cli 0.125.0`。
- `codex exec` 支持非交互运行；prompt 可来自命令参数或 stdin；支持 `--json` JSONL 事件输出、`--output-last-message <FILE>`、`--cd <DIR>`、`--model <MODEL>`、`--image <FILE>`、sandbox / approval 配置等选项。
- 代码仓已新增 `codex_bridge.py` 与 `CodexAdapter`：支持 stdin prompt、`--json`、`--output-last-message`、`--cd`、`--model`、`--image`、超时杀进程树、可选 `CODEX_HOME`、JSONL / last-message 提取。
- `adapter_from_agent_config()` 支持 `cli_kind=codex` / `mode=codex-worker`；`python -m multi_agent_tcp agent --mode codex-worker` 已可进入 Codex worker loop。
- `WorkerConfig(cli_kind="codex", model=...)` 会把 model 写入 Codex runtime config，并映射到 `codex exec --model`。
- `WorkerResult` 已支持从 `body.codex.final_text` / `last_message` 解析统一 answer。
- Claude CLI 当前不在 PATH；只记录为“待确认”，不预设命令名、非交互语义或输出格式。
- 代码仓已有 `test_codex_cli_smoke.py`，覆盖 Codex CLI 是否存在、是否暴露 `exec` 非交互命令；`test_agent_runtime.py` 与 `test_skill_space.py` 已覆盖 Codex adapter 分派、model 映射、结果提取与 skill view 注入。

### 运行时 primitives

代码仓当前已新增或扩展：

- `MultiModalEnvelope` / `normalize_envelope`：节点端口统一数据容器，支持 `text` / `image` / `audio` / `file` / `blob` 与 `inline` / `fileref` / `blobref` 编码。
- `AgentNode.execution_mode`：支持 `blocking` / `nonblocking` 字段校验。
- `GraphJob`、`GraphEvent`、`WorkspaceManifest`：非阻塞 job、事件流与共享工作区 manifest 的最小可序列化模型。
- `GraphRuntime.submit_agent_job()`：非阻塞 AgentNode 提交后台 job，记录 manifest，发出 `TaskStarted` / `TaskProgress` / `TaskCompleted` / `TaskFailed` 事件。
- `RouteNode`、`GraphEdge`、`GraphDefinition`、`GraphExecutor`：DAG 校验和 `sequence` / `parallel` / `parallel_reduce` 路由到 cluster 原语的最小实现。
- `dulwich_vendor.py` / `workspace_manager.py`：接入 vendored Dulwich，并新增项目级长期共享工作区、蓝图运行级临时共享工作区、job 隔离目录、diff、scope 校验、文本三方 merge、冲突检测和完整目录归档。
- `skill_space.py`：新增受控 skill 空间、agent 独立目录中的 skill view、hash -> skill 的私有映射，以及超级 agent 的下游 skill 分配权限模型。

当前仍未完成：

- 真实 Claude adapter 执行器。
- Codex 临时 `CODEX_HOME` 与 workspace / agent 独立目录生命周期的自动强隔离。
- 分布式事件总线、持久化 job runner、取消/恢复、lock / lease、Dulwich Git 对象级 commit/ref merge。
- 处理节点、I/O 节点、条件 switch 路由、可视化图编译器。

### SkillSpace、Agent 独立目录与超级 Agent

当前新增三个概念：

- `SkillSpace`：项目级受控 skill 空间。真实 skill 目录只由框架知道，空间内用 opaque hash 标识 skill。
- `AgentSkillView` / agent 独立目录：每个 agent 在一次 run 下拥有独立目录，例如 `runs/active/<run_id>/agents/<agent_id>/`，其中包含 `cache/` 与复制出来的授权 skills。
- `SuperAgentProfile`：最小超级 agent 权限模型。超级 agent 可查看 skill 空间的可分配 skill catalog，并可为下游 agent 指定 skill hash 列表。

设计规则：

- 一个 hash 对应一个 skill。hash -> 真实目录的映射只保存在 `SkillSpace` 的私有 manifest 中。
- 下游 agent 不接触真实 skill 空间路径，也不知道其他未授权 skills。
- 下游 agent 只拿到 `AgentSkillView` 中复制后的 skill 路径，路径形如 `agent_workspace/skills/<hash>/SKILL.md`。
- 框架通过 `SkillSpace.materialize_for_agent(agent_id, agent_root, skill_hashes)` 将授权 skills 复制进当前 agent 独立目录。
- `AgentSkillView.context()` 会生成可注入上下文，告知 agent 自己的独立目录、cache 目录、skills 目录和本次授权 skill hashes。
- `AgentSkillView.catalog_prompt()` 会生成只包含授权 skills 的 catalog prompt。
- `AgentSkillView.codex_execution_context()` / `codex_adapter_options()` 会生成 CodexAdapter 可直接使用的执行上下文与 prompt preamble，只暴露 agent 独立目录和授权 skill catalog。
- `SuperAgentProfile.validate_assignment()` 会校验超级 agent 是否有权给下游分配某些 skill hashes。

当前实现是目录级隔离和 prompt/context 级暴露；CodexAdapter 支持指定 `codex_home`，但临时 `CODEX_HOME` 尚未自动绑定到 agent 独立目录 / run workspace 生命周期。

### 共享工作区生命周期

当前实现采用“用户可指定的项目级长期共享工作区 + 蓝图运行级临时共享工作区 + 完整目录归档”：

```text
<long-term-workspace>/
  workspace.json
  runs/
    active/<run_id>/
      base/
      integration/
      jobs/<job_id>/worktree/
      run_manifest.json
    archived/<run_id>/
    failed/<run_id>/
```

规则：

- `DulwichWorkspaceManager.open_or_init(project_root, workspace_root=...)` 会检测或初始化项目级长期共享工作区；若不传 `workspace_root`，默认使用 `<project>/.multi_agent_workspace/`。
- 推荐用户把长期共享工作区放在对应工程目录下，例如 `<project>/.multi_agent_workspace/` 或 `<project>/.agent_shared/`；也允许放在工程目录外。
- 长期共享工作区是 runtime 控制面目录，agent 可以读取其中的归档、manifest、事件与历史产物，但不允许直接修改。
- 当长期共享工作区位于工程目录内部时，创建 `base` 快照和 job worktree 时会排除该目录，避免把长期账本递归复制进每个运行目录。
- `create_run()` 会在 `runs/active/<run_id>` 创建本次蓝图运行目录，并复制 `base` 与 `integration` 快照。
- `prepare_job()` 为每个 job 创建隔离 `jobs/<job_id>/worktree`。
- `prepare_job()` 会拒绝把长期共享工作区路径放入 `write_scope` / `artifact_scope`。
- `agent_access_context(job)` 会返回 `writable_worktree` 与 `readonly_shared_workspaces`，供后续 agent 启动和沙箱/工具权限层使用。
- `agent_workspace_dir(run, agent_id)` 会为当前 run 创建/返回对应 agent 的独立目录，供 SkillSpace materialize skill view 和后续 agent cache 使用。
- `diff_job()` 对比 `base` 与 job worktree，识别 `added` / `modified` / `deleted`。
- `merge_job()` 先做 `write_scope` / `artifact_scope` 校验，再把 job 变更合并到 `integration`。
- 文本文件使用保守三方 merge；同一路径双方不同修改会写入 conflict marker 并返回冲突。
- 二进制冲突、删除/修改冲突、scope 越界都会阻止自动合并。
- `archive_run()` 将整个 `runs/active/<run_id>` 移动到 `runs/archived/<run_id>` 或 `runs/failed/<run_id>`，保留完整目录。后续删除归档接口已预留，但当前不实现。

当前实现不调用 Git CLI / SVN CLI。Dulwich 已 vendored 到 `vendor/dulwich`，通过 `.gitignore` 排除第三方源码进入项目提交。只读访问当前是 runtime policy 与 manifest 约束；真正 OS ACL / 沙箱级强制写入拦截仍属后续任务。

## 与现有知识库的关系

- 主架构：见 [`core_architecture.md`](core_architecture.md)
- Cluster API：见 [`cluster_api.md`](cluster_api.md)
- Registry / skill 注入：见 [`registry_and_skills.md`](registry_and_skills.md)
- 运行时细节：见 [`runtime_notes.md`](runtime_notes.md)

## 与短期任务的关系

本文件只记录方向性知识与术语。具体近期推进项、拆解任务、优先级与阶段目标，统一放到上级 `tasks/` 目录中。
