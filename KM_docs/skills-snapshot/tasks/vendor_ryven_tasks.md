# vendored Ryven / UI 方向任务

## 目标

为未来节点编辑器、蓝图体验和 vendor GUI 定制建立明确的近期推进项，并把 vendored Ryven 的正式启动入口沉淀为稳定方法。

## 近期任务

1. 基于 `vendor-ryvencore-qt-node-appearance.md`，梳理视觉层改造入口：
   - `Design.py`
   - `FlowTheme.py`
   - `NodeItem.py`
   - `PortItem.py`
2. 区分 `ryvencore_qt` 与 `ryven` 的职责，避免把节点绘制问题误归到 QSS 层。
3. 基于 `ryvencore-vs-ue5-blueprint-gaps-2-4-8.md`，筛选高优先级增强项：
   - 编辑期类型检查
   - 兼容矩阵
   - 端口错误反馈
   - 从 pin 拉线的上下文推荐
   - Inspector 解释与数据预览
4. 评估哪些内容适合先以 headless 运行时落地，哪些必须等可视化编辑器阶段再做。
5. 继续推进 `AgentNode` 接入 Ryven 节点 UI 后的完整可运行链路：
   - 第一步：Ryven Flow -> `GraphDefinition` 编译 + `validate_runnable`（已完成）
   - 第二步：只跑 blocking `AgentNode` 的最小链路
   - 第三步：显示每个节点的运行状态和最终结果
   - 第四步：接 nonblocking job / manifest / workspace event
   - 第五步：做更强的类型系统、Inspector、上下文推荐
   - registry-ui agent profile / skill selection 控件联动
6. 持续维护正式启动入口：
   - `python -m multi_agent_tcp ryven`
   - `multi_agent_tcp/ryven_launcher.py`
   - `__main__.py` 中的 `ryven` 子命令
7. 后续若要提升易用性，可继续补充：
   - `--skip-dialog` 的推荐封装
   - Windows `.bat` 一键启动脚本
   - 常用 nodes package / project 预加载入口

## 当前代码对照状态（2026-05-04）

已完成：

1. 已新增 `ryven_launcher.py`，负责注入 vendored `ryven` / `ryvencore_qt` 路径、patch `ryven` version lookup，并默认追加 `-q pyside6`。
2. `__main__.py` 已提供 `python -m multi_agent_tcp ryven` 子命令，并把剩余参数透传给 Ryven。
3. vendored 视觉层入口文件在代码仓中存在：`vendor/ryvencore_qt/ryvencore_qt/src/Design.py`、`flows/FlowTheme.py`、`flows/nodes/NodeItem.py`、`flows/nodes/PortItem.py`。
4. 已新增本地 Ryven nodes package `ryven_blueprint_nodes`，导出 `AgentNode` wrapper、`BlueprintStart`、`BlueprintEnd`。
5. `ryven_launcher.py` 已默认追加 `-n ryven_blueprint_nodes`，启动 Ryven 时会自动加载蓝图节点包。
6. Start/End 机制已落地第一版：新建/加载 flow 后自动补齐，Start/End 隐藏于节点库，并在 UI 删除路径与 core `Flow.remove_node()` 层保护不可删除。
7. `AgentNode` wrapper 已有基础配置表单，可编辑 `agent_id`、`cli_kind`、`model`、`cwd`、`execution_mode` 与 `skill_selection`。
8. `compile_ryven_flow()` 已落地第一版，可把 live Ryven flow 编译为 `GraphDefinition`，并通过 `GraphEdge.edge_type` 保留 `exec` / `data` 端口语义；`validate_runnable()` 已按 `exec` 控制流校验 Start -> End 路径。

部分完成：

1. `ryvencore_qt` 与 `ryven` 的职责边界已通过 launcher 路径和知识文档初步区分，但视觉层改造尚未开始。
2. 正式启动入口已经沉淀；易用性封装和常用 project 预加载仍未做。
3. `AgentNode` 已能进入节点库并保存基础后端配置，Ryven flow 已能编译为 `GraphDefinition`；但还没有 UI 运行按钮、blocking 最小执行链路和事件展示。

未完成 / 下一步：

1. 还未对 `Design.py`、`FlowTheme.py`、`NodeItem.py`、`PortItem.py` 做实际外观改造。
2. 编辑期类型检查、兼容矩阵、端口错误反馈、从 pin 拉线的上下文推荐、Inspector 解释与数据预览尚未实现。
3. 尚未实现运行按钮、blocking `AgentNode` 最小执行链路、执行事件展示和 AgentNode 输出端口结果展示。
4. registry-ui 的 agent profile / skill selection 控件尚未与 Ryven `AgentNode` 配置表单打通。
5. `--skip-dialog` 推荐封装、Windows `.bat` 一键启动脚本、常用 project 预加载入口尚未实现。

## 依赖知识

- [`../knowledge_base/vendor_ryven_ui.md`](../knowledge_base/vendor_ryven_ui.md)
- [`../knowledge_base/agent_node_ryven_integration.md`](../knowledge_base/agent_node_ryven_integration.md)
- [`../knowledge_base/blueprint_gap_notes.md`](../knowledge_base/blueprint_gap_notes.md)
- [`../archive/blueprint_integration_archive.md`](../archive/blueprint_integration_archive.md)
