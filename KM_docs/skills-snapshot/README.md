# multi-agent-tcp Codex skill

本目录是当前本机生效 Codex skill 的仓库快照，安装位置是 `C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp\`。

## 目的

- 为 GuLiCode desktop、Guli 产品化、蓝图嵌入桌面端、GraphRuntimeControlPlane、GraphRuntime、AgentNode 队列、workspace/events 和 CLIWorkerBackend adapter 提供本地工作记忆。
- 把当前主线固定在 “Guli 产品化 + 蓝图嵌入 GuLiCode 桌面端”，避免再次被旧 Ryven UI 文档带偏。
- 让后续更新 skill 时有稳定的知识库、任务目录和归档目录，并能同步覆盖到 `KM_docs/skills-snapshot`。

## 当前主线

- GuLiCode desktop 是当前用户可见产品面。
- 蓝图能力应作为 GuLiCode desktop 内嵌工作台推进，而不是作为独立的 Ryven 前端主线。
- `GraphRuntimeControlPlane` 负责组织读取、开始校验、运行控制、消息批次、join、结束归档等非 UI 控制面。
- `GraphRuntime` 负责 AgentNode queue、tick dispatch、outgoing batch、fan-in/join、workspace/event/final status。
- `CLIWorkerBackend` 负责 Codex / CodeMaker / 其它 CLI 的后端适配。
- Collaboration Server 是本地 desktop、`/mobile` 和 `/console` 的账号级协作调试入口；最新移动端/桌面 bridge 交接见 `archive/future-server/collaboration_server_desktop_bridge_mobile_chat_2026-05-29.md`。

## 一致性状态

- 2026-05-29 已验证仓库快照 `KM_docs/skills-snapshot` 与已安装 skill `C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp` 内容一致。
- 环境文档已更新到当前机器：`F:\src\Package\Script\Python\multi_agent_tcp`、Python 3.13.5、Bun 1.3.13、Node v24.15.0、Codex CLI 0.125.0。
- 更新 skill 时应镜像整个目录树，而不是只复制 `SKILL.md`，以免保留已删除的旧文档。

## 维护规则

- 新内容优先写入 `knowledge_base/` 或 `tasks/`，长期变更再归档到 `archive/`。
- 写新文档时不要恢复旧的 “Cursor/CodeMaker TCP 编排是中心” 的表述。
- `CodeMakerCluster` 只作为旧 API 兼容名使用；新文档优先写 `CLIWorkerBackend`。
- 旧 Ryven/editor UI 文档已从当前 skill 主快照中移除；若用户明确要求恢复该轨道，再从 git 历史或旧归档中回看。
- 修改环境或启动方式时，同时更新 `environment_setup.md`、`knowledge_base/debug_start.md` 和根 README 中对应入口。

## 当前包含内容

- `SKILL.md`
- `environment_setup.md`
- `knowledge_base/`
- `tasks/`
- `archive/`
