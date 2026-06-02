# multi_agent_tcp

`multi_agent_tcp` 是 GuLiCode 多 Agent 蓝图系统的 Python 运行时底座。当前项目中心不是底层 TCP worker，也不是旧的 Ryven 编辑器，而是 `gulicode-bp` Codex 插件：

```text
gulicode-bp Codex 插件 / 蓝图 Web 工作台
  -> GuLiCode app dev surfaces: /mobile 和 /console
  -> DesktopBlueprintService
  -> GraphRuntimeControlPlane
  -> GraphRuntime
  -> AgentNode 队列、消息分发、汇聚等待、Workspace、事件
  -> CLIWorkerBackend
  -> Codex / CodeMaker 等 CLI worker
```

`gulicode-bp` 插件负责默认用户入口、蓝图编排体验、蓝图 CRUD、启动计划生成和确认运行；`GraphRuntimeControlPlane` 与 `GraphRuntime` 负责框架事实、调度和生命周期；`CLIWorkerBackend` 是执行适配层，用来在需要模型工作时启动具体 CLI worker。GuLiCode Electron 桌面端保留为显式桌面壳、IPC、打包、任务栏或窗口行为开发路径。

## 架构图

### 蓝图框架分层

<img src="docs/diagrams/blueprint_framework_layers.png" alt="蓝图框架分层图" width="92">

产品入口默认在 `gulicode-bp` 插件蓝图工作台，调试时同时保留 `/mobile` 和 `/console`；调度事实在 Python runtime，底层 CLI worker 不拥有产品调度语义。

### Agents 三区协同办公

<img src="docs/diagrams/agents_collaboration_three_zones.png" alt="Agents 三区协同办公图" width="261">

普通 Agents 围绕三个区协作：

- `工程目录`：权威代码源和最终代码目标。Agent 可以读取，但不能直接写。
- `Agent 私有区`：每个 Agent 的可写 `checkout_path`，真实代码改动在这里完成。
- `运行共享区`：保存 `reports`、`artifacts`、`manifest`、`changeset` 引用和事件记录。

代码协作必须走 `checkout -> edit -> status/diff -> submit`。报告和产物通过框架工具发布到运行共享区。

## 当前核心能力

- 插件蓝图工作台：蓝图是项目级能力，默认通过 `gulicode-bp` 本地 Web 工作台运行在当前 project/workspace 语义下。
- 插件启动计划入口：插件工作台负责按当前蓝图、用户任务和起始节点生成启动计划；用户确认后才提交运行。
- 运行时控制面：`GraphRuntimeControlPlane` 提供组织读取、计划校验、启动、状态、结束、消息批次、Agent dispatch、join 等稳定接口。
- 图调度运行时：`GraphRuntime` 负责 AgentNode 队列、消息投递、fan-out、fan-in、idle 提醒、事件、取消、归档和最终状态。
- Workspace 三个区：工程目录只读给 Agent，Agent 私有区可写，运行共享区沉淀报告、产物、manifest、changeset 和冲突记录。
- MCP 工具边界：live blueprint run 可启动 run-scoped MCP 服务，为 AgentNode 暴露受控运行时与 workspace 工具集合。
- Codex-first 适配：当前 live Agent 主线优先使用 Codex CLI；CodeMaker 保留为兼容和备选路径。
- 本地 Collaboration Server：支持 `gulicode-bp` 调试、`/mobile` 和 `/console` 的账号级协作调试；桌面端 bridge 只在显式桌面调试时使用。

## 环境要求

当前本机已验证的基础环境：

```powershell
python --version      # Python 3.13.5
git --version         # git version 2.54.0.windows.1
node --version        # v24.15.0
bun --version         # 1.3.13
codex.cmd --version   # codex-cli 0.125.0
```

新机器至少需要安装：

- Python 3.10+。
- Git for Windows。
- Bun 1.3.x；`GuLiCode/package.json` 当前声明 `bun@1.3.11`，本机使用 `1.3.13`。
- Node.js 22+，用于 JS/Electron 生态工具。
- Codex CLI，用于真实 Codex worker；PowerShell 策略阻止 `codex.ps1` 时使用 `codex.cmd`。
- GuLiCode JS 依赖：`cd GuLiCode; bun install --frozen-lockfile`。
- Playwright Chromium，用于浏览器/e2e 烟测：`cd GuLiCode\packages\app; bunx playwright install chromium`。

更完整的路径、依赖版本、Windows 代理和 packaging 注意事项见 `KM_docs/environment_setup.md`。

## 快速开始

### Python 运行时

在仓库根目录安装 editable package 和常用测试辅助依赖：

```powershell
python -m pip install -e .
python -m pip install pytest merge3
python -m multi_agent_tcp doctor --json
python -m multi_agent_tcp show-registry
```

也可以从本目录的上一级用模块方式运行：

```powershell
python -m multi_agent_tcp show-registry
python -m multi_agent_tcp organization --graph path\to\graph.json
```

### GuLiCode BP 插件调试

默认本地调试入口：

```powershell
.\start-gulicode-debug.cmd
```

等价的显式插件入口：

```powershell
.\start-gulicode-bp-plugin.cmd
```

该脚本会幂等检查并启动 Collaboration Server `127.0.0.1:8787`、`gulicode-bp` 蓝图工作台、GuLiCode app dev server `127.0.0.1:3040`、`http://127.0.0.1:3040/mobile` 与 `http://127.0.0.1:3040/console`，默认不启动 GuLiCode Electron 桌面壳。

### GuLiCode 桌面

只在需要 Electron 桌面壳、IPC、打包、任务栏或窗口行为时使用：

```powershell
.\start-gulicode-desktop.cmd
```

跨平台终端入口：

```powershell
cd GuLiCode
bun run desktop
```

打包烟测入口：

```powershell
.\start-gulicode-desktop.cmd --packaged
```

桌面启动成功通常会看到 renderer dev server、Electron app started、sidecar server ready 等日志标记。详细桌面启动和打包注意事项见 `KM_docs/skills-snapshot/knowledge_base/gulicode_desktop.md`。

## 开发与验证

### Python runtime

常用验证命令：

```powershell
python -m py_compile graph_runtime.py graph_control.py blueprint_mcp_runtime.py agent_launch_context.py desktop_blueprint_service.py
pytest -q test_agent_runtime.py -k "not real_codex"
pytest -q test_desktop_blueprint_service.py
pytest -q test_workspace_api.py test_workspace_manager.py
```

真实 Codex smoke 依赖本机 Codex、模型、凭据和网络状态，默认不作为普通 CI 路径：

```powershell
$env:MULTI_AGENT_TCP_RUN_REAL_CODEX_MCP = "1"
python -m pytest -q test_desktop_blueprint_service.py::test_real_codex_live_blueprint_uses_mcp_for_workspace_and_dispatch_flow -vv
```

### GuLiCode app

常用验证命令：

```powershell
cd GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/i18n/parity.test.ts
bun run typecheck
```

移动端/协作调试相关验证：

```powershell
python -m pytest -q test_collaboration_server.py

cd GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/mobile ./src/components/collaboration-auth.test.ts ./src/pages/session/blueprint-planning-session.test.ts
bun run typecheck
```

Electron 侧常用验证：

```powershell
cd GuLiCode\packages\desktop-electron
bun test ./src/main/ipc-blueprint-runtime.test.ts
bun run typecheck
```

## 目录导览

| 路径 | 说明 |
| --- | --- |
| `GuLiCode/` | GuLiCode 桌面产品代码，包含 Electron shell、SolidJS app、OpenCode vendor 基线和桌面启动脚本。 |
| `collaboration_server/` | 本地 Collaboration Server，提供登录、presence、桌面 bridge、移动端提交、会话镜像和只读管理控制台 API。 |
| `graph_runtime.py` | 核心运行时：AgentNode 队列、dispatch、join、workspace 状态、事件和最终状态。 |
| `graph_control.py` | Runtime control-plane 包装层，提供组织读取、start/status/end、message batch、join 等接口。 |
| `desktop_blueprint_service.py` | GuLiCode 桌面与 Python runtime 之间的服务外壳。 |
| `blueprint_mcp_runtime.py` | live blueprint run 的 MCP 工具边界与 run-scoped MCP 服务。 |
| `workspace_manager.py` / `workspace_api.py` / `workspace_rpc.py` | 三个区、private checkout、changeset、冲突检测、报告和产物发布。 |
| `codex_bridge.py` / `codemaker_bridge.py` / `cluster.py` | CLI worker 适配和兼容层。新文档中优先使用 `CLIWorkerBackend` 这个语义名。 |
| `docs/` | 设计文档、Workspace API 说明、蓝图 fixture、架构图。 |
| `KM_docs/skills-snapshot/` | 当前 Codex skill 知识快照，记录近期架构方向、验证命令和交接状态。 |
| `start-gulicode-debug.cmd` / `start-gulicode-debug.ps1` | 插件优先调试启动脚本，默认拉起 `gulicode-bp` 蓝图工作台、`/mobile` 和 `/console`，不启动 Electron 桌面壳。 |
| `start-gulicode-bp-plugin.cmd` | 插件优先调试入口别名。 |
| `skill_list/` | 本地 Agent skill 目录，通常由 `python -m multi_agent_tcp.init_skill_list` 初始化。 |
| `test_*.py` | Python runtime、workspace、desktop service、control-plane 和 Collaboration Server 的测试。 |

## 当前边界

- 不把低层 TCP worker 当作产品中心。它只是 `CLIWorkerBackend` 后面的一个执行路径。
- 不恢复旧 Ryven/editor UI 作为主线。当前蓝图能力应嵌入 GuLiCode 桌面。
- 普通 Agents 不直接互发消息。它们通过框架 API 暂存 dispatch 意图，由 `GraphRuntime` 校验并投递。
- 普通 Agents 不直接写工程目录或运行共享区。代码改动进入私有 checkout，提交 changeset 后由框架校验、合并或返回冲突。
- 插件不直接改写 runtime 内部状态。它读取蓝图组织上下文、生成/校验结构化启动计划，并通过控制面请求生命周期动作。
- UI 不复制调度语义。GuLiCode 前端消费 runtime/control-plane 状态，不重新实现队列、join、workspace 决策。

## 相关文档

- `docs/workspace_api.md`：Workspace 三个区、checkout/status/diff/submit/publish 的当前契约。
- `docs/gulicode_blueprint_workbench_design.md`：GuLiCode 蓝图工作台的产品和技术边界。
- `docs/external_app_openclaw_channel_patterns.md`：外部聊天 App 拉起 OpenClaw 对话的 channel 接入模式，以及它和 UI deep link 的区别。
- `KM_docs/environment_setup.md`：当前机器环境、依赖安装、调试启动和 Windows 注意事项。
- `KM_docs/skills-snapshot/knowledge_base/core_architecture.md`：当前核心架构快照。
- `KM_docs/skills-snapshot/knowledge_base/dispatch_workflows.md`：runtime control-plane 和消息分发工作流。
- `KM_docs/skills-snapshot/knowledge_base/gulicode_desktop.md`：GuLiCode 桌面启动、打包和本机验证规则。
