# 核心架构

## 定位

`multi_agent_tcp` 是一个让 Cursor、CodeMaker 或其他 Python 调用者同时与多个 CodeMaker CLI worker 交互的编排框架。核心目标是并行分发任务、串行链式协作，以及聚合多路结果。

## 关键路径

- 常见代码根路径：`d:\agents\multi_agent_tcp\`
- 根包入口文件：
  - `multi_agent_tcp/__main__.py`
  - `multi_agent_tcp/cluster.py`
  - `multi_agent_tcp/registry.py`
- 用户文档：
  - `multi_agent_tcp/examples/HOWTO.txt`
  - `multi_agent_tcp/README.md`
  - `multi_agent_tcp/GUIDE_FOR_CODEMAKER.md`
- 本地 CodeMaker 说明：`multi_agent_tcp/codemaker_cli.md`

## 主组件

| 组件 | 文件 | 职责 |
|------|------|------|
| Cluster（门面） | `cluster.py` | `CodeMakerCluster`：管理 broker + worker 生命周期，提供并行、串行、reduce 等高层任务接口 |
| Async Dispatch | `__main__.py` | `dispatch --async`、状态文件落盘、后台作业跟踪 |
| Registry | `registry.py` | `AgentsRegistry`、`AgentProfile`、`SkillInfo`、`AgentSession`、skill catalog |
| Registry UI | `registry_ui.py` | Tkinter 图形化管理 `agents_registry.json` |
| Agents 配置 | `agents_registry.json` | agent 的 model / skills / cwd / timeout_sec / enabled |
| Skill 合并 | `init_skill_list.py` | 将 `.codemaker/skills` 与 `.cursor/skills` 合并到 `skill_list/` |
| Broker | `broker.py` | 单端口 broker，处理 `register` / `send` / `broadcast` / `ping` / `batch_gather` |
| Client | `client.py` | `AgentTCPClient`，封装发送、接收、gather 与 pump |
| 协议 | `protocol.py` | 4 字节大端长度 + UTF-8 JSON frame |
| CodeMaker 桥 | `codemaker_bridge.py` | 子进程执行 `codemaker run`，包含超时和运行时防御 |
| 编排 CLI | `orchestrate.py` | 读取 JSON 配方执行 `send_to` / `broadcast` / `wait_for` / `batch_gather` |
| 日志 | `log_setup.py` | stderr + RotatingFileHandler |
| 进程工具 | `_proc_utils.py` | Windows 进程树清理、异步杀树、终止等待 |

## 端口模型

- 仅 broker 进程 bind 一个端口。
- 各 agent 作为 TCP 客户端连接到 broker。
- 多个连接共享同一 broker 端口。

## 相关知识

- Cluster API：[`cluster_api.md`](cluster_api.md)
- Registry 与 skill 体系：[`registry_and_skills.md`](registry_and_skills.md)
- Dispatch 工作流：[`dispatch_workflows.md`](dispatch_workflows.md)
- 运行时注意事项：[`runtime_notes.md`](runtime_notes.md)
- 多 CLI 与节点工作流方向：[`multi_cli_workflow.md`](multi_cli_workflow.md)
- vendored UI / 蓝图方向：[`vendor_ryven_ui.md`](vendor_ryven_ui.md)、[`blueprint_gap_notes.md`](blueprint_gap_notes.md)
