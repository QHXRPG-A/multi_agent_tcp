# vendored Ryven / UI 方向任务

> 当前定位：Ryven 是延后的 visual-editor / 历史原型轨道，不是当前 GuLiCode 桌面 app 主线。除非用户明确要求 Ryven/editor 工作，否则不要把本文件中的 `Start -> AgentNode -> End` 最小闭环当作当前优先级。

## 目标

为未来节点编辑器、蓝图体验和 vendor GUI 定制保留知识与任务草案，并把 vendored Ryven 的正式启动入口沉淀为稳定方法。

当前主线应从 GuLiCode desktop / top Agent 发起 start plan，经 `GraphRuntimeControlPlane` 校验并交给 `GraphRuntime` 执行。Ryven 只是在未来需要可视化编辑器时复用 GraphDefinition / AgentNode schema 的一个候选前端。

## 延后任务

### Ryven 最小闭环备忘

如果后续重新启动 Ryven/editor 方向，不要一口气做重度蓝图编辑器，先只完成这条链路：

1. 节点库里能拖出 `Start` / `AgentNode` / `End`
2. `AgentNode` 的配置能稳定保存和恢复
3. `Run Blueprint` 能触发后端编译和执行
4. 执行结果能回写到节点外观或一个最简结果面板
5. 不可删除的 terminal 节点仍要受保护

这意味着：
- 先做执行闭环，不先做完整美术改造
- 先做状态反馈，不先做大型 Inspector
- 先做单图单路径，不先做复杂多分支编辑体验

但在当前项目主线下，这些工作排在 GuLiCode/top-Agent、GraphRuntime 调度、workspace/events 和 desktop UI 集成之后。

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

### 最小闭环方案备忘

短期可行方案优先级如下：

1. 把 `Run Blueprint` 按钮加到 Ryven 侧，作为统一运行入口
2. 按当前 flow 编译出 `GraphDefinition`
3. 只执行单一 `exec` 主链，先支持 `Start -> AgentNode -> End`
4. 执行时把节点状态标成 running / done / failed
5. 把最终结果显示在节点 widget 或下方最简结果区
6. 先不要做复杂主题和交互打磨，先保证“点一下能跑通”

未完成 / 下一步（仅在 Ryven/editor 方向被重新激活时执行）：

1. 先实现 `Run Blueprint` 和 blocking 最小执行链路。
2. 先把节点运行状态和最终结果显示出来。
3. 之后再补 `Design.py`、`FlowTheme.py`、`NodeItem.py`、`PortItem.py` 的外观改造。
4. 再做编辑期类型检查、兼容矩阵、端口错误反馈、从 pin 拉线的上下文推荐、Inspector 解释与数据预览。
5. 再让 registry-ui 的 agent profile / skill selection 控件和 Ryven `AgentNode` 配置表单联动。
6. 最后再补 `--skip-dialog` 推荐封装、Windows `.bat` 一键启动脚本和常用 project 预加载入口。

## 依赖知识

- [`../knowledge_base/vendor_ryven_ui.md`](../knowledge_base/vendor_ryven_ui.md)
- [`../knowledge_base/agent_node_ryven_integration.md`](../knowledge_base/agent_node_ryven_integration.md)
- [`../knowledge_base/blueprint_gap_notes.md`](../knowledge_base/blueprint_gap_notes.md)
- [`../archive/blueprint_integration_archive.md`](../archive/blueprint_integration_archive.md)
