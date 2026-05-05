# 节点运行时与图编译方向任务

## 目标

把当前 cluster / broker 编排能力，逐步抬升为面向节点图的执行运行时与编译目标。

## 近期任务

1. 完善 AgentNode prompt contract，使下游 agent 只知晓：
   - 传入上下文
   - 用户设置的 agent prompt / model / skills
   - 框架允许暴露的接口文档
   - 可读/可写路径
   - 输出格式
2. 继续打通 `AgentSkillSelection` 到图执行期的授权 skill 注入：
   - `none` / `all` / `selected` / `upstream` 模型已落地
   - registry / registry-ui 已同步
   - 下一步把 `upstream` 与图上游超级 agent 的配置流、授权 skill materialize 串起来
3. 完善 `AgentSkillView` 与 CodexAdapter 的强隔离：
   - prompt/context 注入已可用
   - 下一步绑定临时 `CODEX_HOME`
   - 后续接入 sandbox / writable path policy
4. 为超级 agent 增加下游 agent 配置能力：
   - model
   - skills
   - prompt contract
   - write/artifact scope
5. 补处理节点、I/O 节点和条件 `switch` 路由。
6. 把内存事件模型扩展为可订阅/可持久化事件流，并补 `WorkspaceChanged`、`ReviewRequested` 的实际触发点。
7. 为非阻塞 job 增加取消、恢复、超时、失败重试和持久 runner。
8. 为共享工作区增加 lock / lease、Dulwich commit/ref merge、归档删除 API、归档索引和空间清理策略。
9. 按 Ryven + GraphRuntime 融合顺序推进图执行链路：
   - 第一步：Ryven Flow -> `GraphDefinition` 编译 + `validate_runnable`（已完成）
   - 第二步：只跑 blocking `AgentNode` 的最小链路
   - 第三步：显示每个节点的运行状态和最终结果
   - 第四步：接 nonblocking job / manifest / workspace event
   - 第五步：做更强的类型系统、Inspector、上下文推荐

## 当前代码对照状态（2026-05-04）

已完成：

1. 已新增 `graph_runtime.py`，包含 `AgentNode`、`AgentInstance`、`GraphRuntime`、`BrokerAgentRuntime`。
2. `AgentNode` 已具备与 `WorkerConfig` / registry 扩展对齐的基础字段：`node_id`、`agent_id`、`cli_kind`、`model`、`cwd`、`skills`、`timeout_sec`、`prompt_via_file`、`command`、`adapter_options`、`extra_env`、`external`。
3. `GraphRuntime.ensure_agent()` 已实现同一次图运行内的 `node_id -> AgentInstance` 绑定与复用；首次经过节点可调用 `cluster.ensure_worker()` 懒启动 worker。
4. `GraphRuntime.send_agent_message()` 已把 Agent 节点消息发送映射到 `cluster.run_single()`，并明确把 cluster 方法视作消息调度原语，而不是每次节点经过都 spawn/teardown。
5. `BrokerAgentRuntime` 已提供连接已有 broker 并向 worker 发送单条消息的轻量运行时。
6. `AgentNode.execution_mode` 已支持 `blocking` / `nonblocking` 字段校验；`GraphRuntime.send_agent_message()` 会把 `nonblocking` 节点转为 job 提交响应。
7. 已新增 `GraphJob`、`GraphEvent`、`WorkspaceManifest`，形成非阻塞 job、事件模型与共享工作区 manifest 的最小可序列化基线。
8. 已新增 `MultiModalEnvelope` / `normalize_envelope`，作为节点端口统一数据容器。
9. 已新增 `RouteNode`、`GraphEdge`、`GraphDefinition`、`GraphExecutor`，支持 DAG 环检测和 `sequence` / `parallel` / `parallel_reduce` 路由到 cluster 原语的最小实现。
10. 已新增 `dulwich_vendor.py` 与 `workspace_manager.py`，接入 vendored Dulwich，并实现用户可指定的项目级长期共享工作区、蓝图运行级临时共享工作区、完整目录归档、job 隔离 worktree、diff、scope 校验、文本三方 merge 和冲突检测。
11. 长期共享工作区支持默认 `<project>/.multi_agent_workspace/`，也支持用户显式传入 `workspace_root`；当它位于工程目录内时，运行快照会排除该目录。agent 访问上下文会把长期共享工作区暴露为 `readonly_shared_workspaces`，并拒绝把它纳入 `write_scope` / `artifact_scope`。
12. 已新增 `SkillSpace`、`AgentSkillView`、`SuperAgentProfile`：框架私有维护 hash -> skill 的映射，按 hash 列表将授权 skills 复制到当前 agent 独立目录，并为超级 agent 提供下游 skill 分配校验。
13. `test_agent_runtime.py` 已覆盖 AgentNode 字段解析、WorkerConfig 转换、GraphRuntime 懒启动与复用、非阻塞 job 事件和 manifest、MultiModalEnvelope、DAG 环检测、路由节点调度。
14. `test_workspace_manager.py` 已覆盖 Dulwich backend、完整目录归档、自定义长期共享目录、只读访问策略、job diff、scope violation、无冲突合并、同文件冲突和 failed run 归档。
15. `test_skill_space.py` 已覆盖 hash skill 映射、agent 独立目录 materialize、未知 hash 拒绝、超级 agent 分配权限和 workspace manager 的 agent 目录集成。
16. `AgentSkillView` 已新增 `codex_execution_context()` 与 `codex_adapter_options()`，可向 CodexAdapter 暴露 agent 独立目录、cache、授权 skills 目录、skill hash 列表与授权 skill catalog。
17. `AgentNode.node_id` 已改为框架自动分配；用户配置侧不再需要填图内部节点 ID。
18. `AgentSkillSelection` 已落地并同步到 registry / registry-ui，支持 `none`、`all`、`selected`、`upstream`；旧 `skills` 列表兼容为 `selected`。registry 静态注入中 `upstream` 不解析 skill，留给图运行时超级 agent 授权。
19. `test_registry_skill_selection.py` 已覆盖 registry 对 skill selection 的解析、catalog 注入和 `show-registry` 输出。
20. `AgentNode.to_dict()` 已补齐，便于 Ryven wrapper、项目保存和 runtime 编译复用同一后端 schema。
21. `GraphDefinition` 已新增 `BlueprintTerminalNode`、`terminal_nodes` 和 `validate_runnable()`，可校验 Start/End 唯一性、DAG 与 start -> end 有向路径。
22. `GraphEdge` 已新增 `edge_type`，用于记录端口连接语义；`validate_runnable()` 只使用 `exec` 边判断 Start -> End 控制流路径，`data` 边不会误判为可运行路径。
23. `compile_ryven_flow()` 已可把 live Ryven flow 编译为 `GraphDefinition`：`BlueprintStart` / `BlueprintEnd` 编译为 `BlueprintTerminalNode`，Ryven `AgentNode` wrapper 编译为后端 `AgentNode`，Ryven 连接编译为带端口名和 `edge_type` 的 `GraphEdge`。

部分完成：

1. 节点分类目前只落地了 Agent 节点；处理节点、路由节点、I/O 节点仍停留在设计任务。
2. Agent 节点生命周期已有“首次绑定/后续复用/运行时 close 清理绑定”的基础实现；由 cluster 拥有的 worker 进程 teardown 仍委托给 cluster，尚未形成完整图运行失败/取消收尾协议。
3. 图编译目前已有路由节点到 `run_chain` / `run_parallel` / `run_parallel_reduce` 的最小映射，并新增 runnable blueprint 起止约束；Ryven flow -> `GraphDefinition` 编译已落地第一版，但还没有图级 blocking 执行入口和事件回流 UI。
4. 共享工作区已有隔离目录、diff、merge、冲突检测、完整目录归档和 runtime 只读策略；lock / lease、OS ACL / 沙箱级只读强制、持久 runner、Git 对象级 commit/ref merge 仍未做。
5. 事件模型目前是内存列表和 manifest 更新；还不是跨进程事件总线。
6. SkillSpace 目前提供目录级隔离与 prompt/context 暴露；已可生成 CodexAdapter options，但尚未把临时 `CODEX_HOME` 自动绑定到 CLI 运行时做强隔离。
7. `upstream` skill selection 的运行时授权模型已有校验基础，但还没有完整接入图上游超级 agent 的 UI/编排配置流。

未完成 / 下一步：

1. 补处理节点、I/O 节点和条件 `switch` 路由。
2. 把内存事件模型扩展为可订阅/可持久化事件流，并补 `WorkspaceChanged`、`ReviewRequested` 的实际触发点。
3. 为非阻塞 job 增加取消、恢复、超时、失败重试和持久 runner。
4. 为共享工作区增加 lock / lease、Dulwich commit/ref merge、归档删除 API、归档索引和空间清理策略。
5. 实现只跑 blocking `AgentNode` 的最小链路：从 `GraphDefinition` 读取 exec 拓扑，按控制流执行 AgentNode，并把 data 边的 prompt/result 传递接入最小语义。
6. 把 `AgentSkillView` 的 Codex options 自动并入 AgentNode / WorkerConfig 创建路径。
7. 将 `upstream` skill selection 与图上游超级 agent 配置流打通，并在需要时由运行时 materialize 授权 skills。
8. 实现超级 agent 除 skill 分配外的下游 agent 配置能力。
9. 补节点运行状态与最终结果事件模型，供 Ryven UI 显示 queued/running/completed/failed。
10. 接入 nonblocking job / manifest / workspace event 的订阅、展示与持久化边界。
11. 建立更强的端口类型系统、Inspector 数据预览和上下文推荐能力。

## 依赖知识

- [`../knowledge_base/multi_cli_workflow.md`](../knowledge_base/multi_cli_workflow.md)
- [`../knowledge_base/agent_node_ryven_integration.md`](../knowledge_base/agent_node_ryven_integration.md)
- [`../knowledge_base/core_architecture.md`](../knowledge_base/core_architecture.md)
- [`../knowledge_base/cluster_api.md`](../knowledge_base/cluster_api.md)
