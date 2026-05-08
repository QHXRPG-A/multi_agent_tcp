# Dispatch 工作流

本文件记录 `multi_agent_tcp` 的调度入口。当前主线是 `GraphRuntimeControlPlane` / `GraphRuntime`；旧 `show-registry` / `dispatch` 是 legacy backend / broker 入口。相关配置体系见 [`registry_and_skills.md`](registry_and_skills.md)。

## 当前推荐：Graph runtime control plane（非 UI）

面向 GuLiCode 顶层 Agent、多 Agent 蓝图通信和 desktop UI 集成的非 UI 控制面已经落地。CLI 仍是 thin client，核心语义在 `GraphRuntime` / `GraphRuntimeControlPlane`。

本地 graph JSON：

```bash
python -m multi_agent_tcp organization --graph graph.json
python -m multi_agent_tcp organization --graph graph.json --agent-id coder
python -m multi_agent_tcp runtime validate-start --graph graph.json --plan plan.json
python -m multi_agent_tcp runtime top-agent-context --graph graph.json --top-agent-profile profile.json
```

live runtime RPC：

```bash
python -m multi_agent_tcp organization --rpc-url http://127.0.0.1:9000/graph-runtime --token TOKEN
python -m multi_agent_tcp runtime start --rpc-url URL --token TOKEN --plan plan.json
python -m multi_agent_tcp runtime status --rpc-url URL --token TOKEN
python -m multi_agent_tcp runtime end --rpc-url URL --token TOKEN --action complete
python -m multi_agent_tcp runtime message-batch --rpc-url URL --token TOKEN --source-node-id planner --required-targets coder,doc
python -m multi_agent_tcp runtime message-stage --rpc-url URL --token TOKEN --batch-id out-1 --target-node-id coder --body body.json
python -m multi_agent_tcp runtime agent-dispatch --rpc-url URL --token TOKEN --source-node-id coder --target-node-id reviewer --body body.json
python -m multi_agent_tcp runtime join-create --rpc-url URL --token TOKEN --join-id join-1 --target-node-id reviewer --required-sources coder,doc
python -m multi_agent_tcp runtime join-contribute --rpc-url URL --token TOKEN --contribution contribution.json
```

当前边界：

- `runtime start/status/end` 是 GuLiCode/top-Agent 与 runtime 的主控制面。
- `message-batch` / `message-stage` / `agent-dispatch` 应围绕当前任务信封、outgoing batch 和 `required_outgoing_targets` 使用。
- `join-create` / `join-contribute` 是 fan-in / 汇聚路径的非 UI 控制面。
- UI 只应消费这些状态与控制接口，不应复制调度语义。

## Legacy：show-registry / dispatch 两步流程

以下流程保留给旧 broker / registry / adapter 验证场景，不是当前 GuLiCode 产品主入口。

### 1. `show-registry`

只读、无副作用，用于查询所有 enabled agent 的：
- `agent_id`
- `display_name`
- `model`
- `skills`
- `cwd`
- `timeout_sec`

```bash
python -m multi_agent_tcp show-registry [-o agents.json]
```

### 2. `dispatch`

接收任务列表，自动加载 registry、校验 agent、创建集群、注入 skill 并并行执行。

```bash
python -m multi_agent_tcp dispatch --tasks tasks.json [-o result.json]
python -m multi_agent_tcp dispatch --async --tasks tasks.json
```

常用参数：
- `--port`
- `--timeout`
- `--max-retries`
- `--retry-delay-sec`
- `--skill-mode`
- `--async`

## 异步 dispatch

`dispatch --async` 会立即返回：
- `job_id`
- `status_file`
- `output_file`
- 备选 `poll_command`

推荐做法：直接读取 `status_file`，直到 `status` 变为 `completed` 或 `failed`。

备选命令：

```bash
python -m multi_agent_tcp dispatch-status --job-id <job_id> [--wait N]
```

## Session-gated dispatch（legacy）

仍可用于需要 session 校验的场景：

1. `list-agents`
2. `run-agent --session-id ... --agent-id ... --prompt ...`

校验点：
- session 是否存在
- session 是否过期
- agent 是否在 session 白名单内

## Legacy 高层任务入口

旧 cluster facade 仍保留：
- `run-parallel`
- `run-parallel-reduce`
- `run-chain`

这些命令支持 `--config` / `--registry` / `--port` 三种连接方式。新代码应避免把它们作为 GuLiCode / GraphRuntime 的产品级控制面。

## 相关知识

- CLI 速查：[`cli_reference.md`](cli_reference.md)
- 运行时注意事项：[`runtime_notes.md`](runtime_notes.md)
- Registry：[`registry_and_skills.md`](registry_and_skills.md)
