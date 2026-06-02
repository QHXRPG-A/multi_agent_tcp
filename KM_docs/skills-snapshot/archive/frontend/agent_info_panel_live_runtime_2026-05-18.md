# Agent 信息面板与 Live Runtime 归档 - 2026-05-18

> Superseded interaction note: the original hover-to-open behavior in this
> archive has been replaced by left mouse long-press with a circular progress
> ring, plus the Agent node right-click `Info panel` / `信息面板` menu item.
> See `agent_info_panel_interaction_2026-05-18.md` for the current panel
> interaction baseline, including move and resize behavior.

## 背景

本轮目标是把蓝图从仅状态投影推进到 live runtime，并为 GuLiCode
蓝图画布增加 Agent 信息面板：

- 鼠标悬停 Agent 节点 2 秒打开信息面板。
- 未运行蓝图时也可查看静态 Agent 配置和“未运行”状态。
- live 运行时流式显示 Agent 输出、公开 reasoning 摘要、工具调用和错误。
- 支持向 Agent 队列发送消息，模式为 `default` 或 `top`。
- 面板支持 close、pin，多 pinned 面板可并存；非 pinned 面板外部点击关闭。

## 关键结论

- 本轮施工重点是中间层：Python desktop blueprint service、GraphRuntime、
  CLIWorkerBackend/TCP worker 链路、Codex JSONL 流解析。
- UI 与后端收束为两条 transport：
  - `HTTP/IPC` 控制面：start/status/end、agentInfo、queueAgentMessage、
    agentStreamToken。
  - `WebSocket` 事件面：只推统一的 `AgentStreamEvent`。
- 两条 transport 不是两套业务协议；状态和流式事件都从同一套 runtime
  事件/快照模型投影。
- “思考过程”只展示 CLI 公开输出里的 reasoning/thought summary，不展示隐藏链路思维。
- Hover 和发送消息不会自动启动蓝图；发送消息必须已有 live run。

## 已落地范围

- `desktop_blueprint_service.py`
  - `blueprint.start(..., executionMode)` 支持 `status` / `live`。
  - live run 创建 `CLIWorkerBackend`、`GraphRuntimeControlPlane`、
    `GraphRuntime`，并管理 tick/backend/WS 生命周期。
  - 新增 `blueprint.agentInfo`、`blueprint.queueAgentMessage`、
    `blueprint.agentStreamToken`。
  - 内置本地 WebSocket upgrade，用一次性 token 推送 Agent stream 事件。
- `graph_runtime.py`
  - 启动 tick loop。
  - Agent 队列支持 `default` / `top`。
  - 状态变化、队列变化、消息 started/completed、工具/错误等统一写入
    `AgentStreamEvent`。
- TCP worker/backend 链路
  - `AgentMessage` 携带 metadata。
  - `agent.stream` 中间事件不会被 `wait_for_message` 当作最终 reply。
  - 最终结果仍走原有 reply 语义，兼容 `run_single`。
- `codex_bridge.py`
  - Codex stdout/stderr 改为逐行读取。
  - 边解析 JSONL 边归一成 `AgentStreamEvent`。
  - 保持最终结果收集逻辑兼容。
- GuLiCode Electron / preload / platform
  - 新增控制面 IPC 和 WS URL 获取。
  - Renderer 不直接依赖 Python token/端口细节。
- `blueprint-side-panel.tsx`
  - 新增 Agent 信息面板、hover 2 秒、pin/close、多面板、外部点击关闭、
    流式 transcript、发送框、默认/置顶模式、未运行只读状态。
  - 修复 Solid store 浅合并导致面板无法关闭的问题：删除面板时使用
    `reconcile(panels)` 替换整个 panels 集合。

## 已验证

Python：

```powershell
python -m py_compile desktop_blueprint_service.py graph_runtime.py client.py broker.py adapters.py codex_bridge.py cluster.py __main__.py test_desktop_blueprint_service.py
pytest -q test_desktop_blueprint_service.py test_multi_agent_tcp_cli.py
pytest -q test_agent_runtime.py::test_graph_runtime_queues_messages_until_agent_is_idle test_agent_runtime.py::test_graph_runtime_keeps_agent_idle_after_worker_ok_false test_agent_runtime.py::test_nonblocking_agent_job_fails_on_worker_ok_false
```

App：

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run typecheck
bun run build
```

Electron：

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-runtime.test.ts ./src/main/ipc-blueprint-runtime.test.ts
bun run typecheck
bun run build
```

Packaging：

- `bun run package:win` 在普通 Windows 会话中仍可能因为 `winCodeSign`
  symlink 权限失败。
- 已用本地免签 config workaround 成功产出：
  - `dist/opencode-electron-win-x64.exe`
  - `dist/opencode-electron-win-x64.exe.blockmap`
  - `dist/win-unpacked/GuLiCode Dev.exe`

Debug startup：

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
$env:ELECTRON_ENABLE_LOGGING = '1'
$env:ELECTRON_ENABLE_STACK_DUMPING = '1'
Remove-Item Env:\DEBUG -ErrorAction SilentlyContinue
bun run dev
```

## 当前未完成 / 后续建议

- `blueprint-list-models` 仍可能因本机 spawn `EPERM` 失败，需要把
  `codex` / `codex` 可执行文件解析、权限错误提示和 fallback 做得更友好。
- Agent 信息面板的 pin 图标当前复用现有 icon，后续可接入专门 pin icon。
- runtime 状态面板仍是 `HTTP/IPC` 轮询的状态投影；Agent transcript 已走
  WebSocket。后续可决定是否把更细粒度运行时状态也迁移到统一事件面。
- 需要继续人工 smoke：
  - hover 2 秒打开
  - close/pin/外部点击关闭
  - 多 pinned 面板
  - 未运行只读
  - live run 下流式 transcript
  - `default/top` 队列发送
