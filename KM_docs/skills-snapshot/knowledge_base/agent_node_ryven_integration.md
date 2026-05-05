# AgentNode 接入 Ryven 节点 UI 知识

本文件沉淀 `AgentNode` 接入 vendored Ryven / `ryvencore_qt` 节点 UI 时确认的框架知识、当前实现边界和后续维护注意事项。它补充 [`vendor_ryven_ui.md`](vendor_ryven_ui.md) 的启动与视觉层知识，也补充 [`blueprint_gap_notes.md`](blueprint_gap_notes.md) 中的蓝图语义设计。

## 当前结论

`multi_agent_tcp.graph_runtime.AgentNode` 是后端 dataclass 配置对象，不是 Ryven 的 `ryvencore.Node` 子类，不能直接注册进 Ryven 左侧节点库。正确做法是创建一个本地 Ryven nodes package，用 Ryven `Node` 子类包装后端 `AgentNode` 配置，并在节点 state 中保存后端配置 dict。

当前推荐 UI 接入路径：

```text
python -m multi_agent_tcp ryven
  -> ryven_launcher.py 注入 vendor path
  -> 自动追加 -n ryven_blueprint_nodes
  -> Ryven import_nodes_package()
  -> ryven_blueprint_nodes/nodes.py export_nodes()
  -> 左侧节点库显示 AgentNode
```

当前代码位置：

- `multi_agent_tcp/ryven_blueprint_nodes/nodes.py`：导出 `BlueprintStart`、`BlueprintEnd`、Ryven wrapper `AgentNode`
- `multi_agent_tcp/ryven_blueprint_nodes/gui.py`：`AgentNode` 配置表单 GUI
- `multi_agent_tcp/ryven_blueprint.py`：Start/End 自动注入、节点库过滤、删除保护 hook、`compile_ryven_flow()` 编译桥
- `multi_agent_tcp/ryven_launcher.py`：vendored Ryven 启动兼容和默认 nodes package 加载
- `multi_agent_tcp/graph_runtime.py`：后端 `BlueprintTerminalNode`、`GraphDefinition.terminal_nodes`、`GraphEdge.edge_type`、`validate_runnable()`

## Ryven 节点包机制

Ryven 从包含 `nodes.py` 的目录加载节点包：

- `ryven.main.packages.nodes_package.NodesPackage(directory)` 约定 `directory/nodes.py`
- `import_nodes_package()` 会执行该 `nodes.py`
- 节点包通过 `ryven.node_env.export_nodes([...])` 导出 `ryvencore.Node` 子类
- GUI 代码通过 `@on_gui_load` 延迟导入，避免 no-gui 模式加载 Qt 依赖
- GUI 类通过 `ryven.gui_env.node_gui(SomeNode)` 绑定到节点类

`export_nodes()` 会给节点 identifier 加 package 前缀。比如本地包目录名是 `ryven_blueprint_nodes`，节点 identifier 会进入类似：

```text
ryven_blueprint_nodes.AgentNode
```

因此保存项目时，项目文件依赖这个 nodes package；路径和 package 名变化会影响旧项目加载。

## 左侧节点库

Ryven 左侧节点库展示的是 `Session.nodes` 中注册的节点类型。核心路径：

- `vendor/ryven/ryven/gui/main_window.py`
  - `MainWindow.import_nodes()`
  - `self.core_session.register_node_types(nodes)`
  - `self.nodes_list_widget.update_list(self.core_session.nodes)`
- `vendor/ryvencore_qt/.../node_list_widget/NodeListWidget.py`
  - `update_list(nodes)`
  - `make_pack_hier()`
  - drag/drop 使用 `NodeWidget._create_mime_data(node)`

要让 `AgentNode` 常驻左侧节点库，启动时默认加载本地 nodes package 即可；不要把后端 dataclass 直接塞进 `Session.nodes`。

Start/End 节点应存在于 flow 里，但不应出现在节点库里供用户拖第二个实例。当前做法是给 Start/End 节点类标记：

```python
hide_from_node_list = True
blueprint_protected = True
blueprint_terminal_kind = "start"  # or "end"
```

再 hook `NodeListWidget.update_list()` 过滤 `hide_from_node_list` 节点类。

## Flow 创建与自动 Start/End

`ryvencore.Session.create_flow(title, data=None)` 的关键顺序是：

```text
Flow(session, title)
self.flows.append(flow)
self.flow_created.emit(flow)
if data is not None:
    flow.load(data)
```

`SessionGUI._flow_created()` 监听 core session 的 `flow_created`，并在事件中创建 `FlowView`。这意味着：

- flow 创建事件发生在 `flow.load(data)` 之前
- 新 flow 和加载旧项目都会走同一个 create/load 流程
- 自动插入 Start/End 必须幂等，否则加载旧项目时容易重复插入
- hook 放在 `Session.create_flow()` 外层时，应在原始 `create_flow()` 返回后再检查 flow 中是否已经有 Start/End

当前策略：

1. `install_blueprint_hooks()` patch `ryvencore.Session.create_flow`
2. 原始 create/load 完成后调用 `ensure_blueprint_terminal_nodes(flow, flow_view)`
3. 如果缺 Start 或 End，就用 `flow.create_node(start_class/end_class)` 补齐
4. 如果已存在，不重复创建
5. 位置由 `ryven_blueprint.py` 中 `_START_POS` / `_END_POS` 设定

注意：当前实现会修复缺失的 Start/End，但不会自动删除重复 terminal；重复 terminal 交给后端 `validate_runnable()` 报错。

## 删除保护

仅在菜单层隐藏删除动作不够。Ryven 的删除路径主要有三层：

- `FlowView.keyPressEvent()` 中 Delete 键调用 `remove_selected_components__cmd()`
- `_cut()` 会复制选中内容后调用 `remove_selected_components__cmd()`
- `RemoveComponents_Command.redo_()` 最终调用 `flow.remove_node(n)`

因此 Start/End 的不可删除需要同时保护 UI 层和 core 层：

1. hook `FlowView.remove_selected_components__cmd()`，从选中项中过滤受保护节点
2. hook `RemoveComponents_Command.__init__()`，避免被构造成待删除 node list
3. hook `ryvencore.Flow.remove_node()`，即使绕过 UI 调 core API，也不删除 `blueprint_protected` 节点

复制/剪切还有一个额外问题：如果用户复制 Start/End，再粘贴，会制造重复 terminal。当前 hook 会让 `_get_nodes_data()`、`_get_connections_data()`、`_get_output_data()` 对受保护 terminal 做过滤，从而降低复制/剪切路径制造重复 Start/End 的风险。

## 节点序列化与配置保存

Ryven 节点持久化主要走：

- `Node.get_state()` / `Node.set_state(data, version)`：节点自有业务 state
- `Node.additional_data()` / `load_additional_data()`：给前端或扩展保存额外信息
- `NodeItem.complete_data()`：给节点保存 `pos x`、`pos y`、main widget state、collapse 等前端信息

因此 wrapper `AgentNode` 应把后端配置保存到 `get_state()` 里，而不是依赖 GUI widget 的临时状态：

```python
def get_state(self):
    return {"agent_node": dict(self.agent_config)}

def set_state(self, data, version):
    self.agent_config = _normalize_agent_config(data)
```

后端 `graph_runtime.AgentNode` 需要稳定的 `to_dict()` / `from_dict()`，让 UI 表单、项目保存和 runtime 编译使用同一 schema。不要在 UI 层另造一份不兼容字段名。

当前 AgentNode 前后端一致性的准确边界：

- 一致：Ryven wrapper 内部保存后端 `AgentNode.to_dict()` 产物，加载、保存和编译都通过 `RuntimeAgentNode.from_dict()` 校验。
- 一致：`compile_ryven_flow()` 编译时调用 wrapper 的 `runtime_node()`，拿到真正的后端 `AgentNode` dataclass 后放入 `GraphDefinition.agent_nodes`。
- UI 子集：当前表单只直接暴露 `agent_id`、`cli_kind`、`model`、`cwd`、`execution_mode`、`skill_selection` 和 skill hashes；`timeout_sec`、`prompt_via_file`、`command`、`adapter_options`、`extra_env`、`external`、workspace 与 scope 字段仍可保存在 config dict 中，但暂未做专门控件。
- 待补：复制/粘贴普通 `AgentNode` 时可能复制出相同后端 `node_id`；编译器会报 duplicate node_id，后续应在复制生命周期或编译前修复策略中重新分配节点 ID。

## 后端 runnable 图结构

原来的 `GraphDefinition` 只有：

```text
agent_nodes
route_nodes
edges
validate_dag()
```

这只能校验 unknown edge 与 DAG cycle，不能表达“必须有 Start/End，并且必须从 Start 能走到 End”。因此需要显式补终端节点语义：

```text
terminal_nodes: Dict[str, BlueprintTerminalNode]
validate_runnable()
```

`validate_runnable()` 的当前规则：

- 图必须是 DAG
- 必须恰好一个 `terminal_kind="start"`
- 必须恰好一个 `terminal_kind="end"`
- 必须存在从 start 到 end 的 `exec` 有向路径

`GraphEdge.edge_type` 是 Ryven 端口语义进入后端 IR 的第一版承载字段：

```text
exec = 控制流，决定节点执行顺序和 runnable 路径
data = 数据流，用于 prompt / context / result 等数据传递
```

因此 `validate_runnable()` 不能把 data 线当控制流。比如 `AgentA.result --data--> AgentB.prompt` 只表达数据依赖，不表达 AgentB 一定执行；必须同时存在 `AgentA.out --exec--> AgentB.in` 才能驱动控制流继续。

这说明“当前数据结构是否支持 Start/End 机制”的准确结论是：

```text
原始结构不完整支持；增加 terminal_nodes 与 validate_runnable 后可以支持。
```

## Ryven Flow -> GraphDefinition 编译桥

`compile_ryven_flow(flow, validate=False)` 是 Ryven 前端与后端运行时之间的中间桥，不让 Ryven UI 直接调用零散 runtime API。推荐链路是：

```text
Ryven Flow
  -> compile_ryven_flow()
  -> GraphDefinition
  -> validate_runnable()
  -> GraphRuntime / GraphExecutor
```

编译规则：

- `BlueprintStart` / `BlueprintEnd` -> `BlueprintTerminalNode`
- Ryven `AgentNode` wrapper -> 后端 `graph_runtime.AgentNode`
- Ryven connection -> `GraphEdge`
- Ryven port label -> `GraphEdge.output_port` / `GraphEdge.input_port`
- Ryven port `type_` -> `GraphEdge.edge_type`

当前第一步已经完成：live Ryven flow 可编译为 `GraphDefinition`，并能通过 `validate_runnable()` 做运行前结构校验。它仍只是运行前编译和校验，不等价于完整执行链路。

下一阶段应优先实现只跑 blocking `AgentNode` 的最小链路：Run 入口编译当前 flow，创建/连接 `CodeMakerCluster`，创建 `GraphRuntime`，按 exec 拓扑调度 blocking AgentNode，并把最终结果回填到 UI 或日志。

## GUI 导入验证注意事项

Ryven nodes package 可以在 no-gui 模式验证导出：

```powershell
python -c "import os; from multi_agent_tcp.ryven_launcher import _ensure_vendor_paths, _BLUEPRINT_NODES_PACKAGE; _ensure_vendor_paths(); os.environ['RYVEN_MODE']='no-gui'; from ryven.main.packages.nodes_package import import_nodes_package; nodes, data = import_nodes_package(directory=str(_BLUEPRINT_NODES_PACKAGE)); print([n.title for n in nodes])"
```

GUI 模式下单独调用 `import_nodes_package()` 可能触发：

```text
AssertionError: Ryven instance not initialized.
```

原因是 Ryven GUI 模式会注册 node source code 到 `ryven.gui.code_editor.codes_storage`，它依赖 `ryven.main.config.instance` 已被正式 editor 初始化。这个错误不等价于正式启动失败；正式路径应通过：

```powershell
python -m multi_agent_tcp ryven
```

## 当前未完成边界

当前已完成的是“节点可拖拽、可配置、Start/End 自动存在、Ryven flow 可编译为 `GraphDefinition`、基础后端校验可表达 runnable 约束”。仍未完成的链路包括：

- 运行按钮、执行事件展示、节点输出端口结果展示
- blocking `AgentNode` 最小图执行链路
- 从 registry-ui 选择 agent profile / skill selection 的完整控件联动
- 更细的端口类型系统、连接兼容矩阵、错误提示
- 非阻塞 job 的 UI 事件流、workspace manifest 可视化

后续开发时不要把“Ryven 节点 wrapper 已存在”误判为“完整蓝图执行链路已完成”。

## 相关知识

- Ryven 启动与视觉层：[`vendor_ryven_ui.md`](vendor_ryven_ui.md)
- 蓝图语义差距：[`blueprint_gap_notes.md`](blueprint_gap_notes.md)
- 多 CLI 与节点工作流：[`multi_cli_workflow.md`](multi_cli_workflow.md)
- 近期 Ryven 任务：[`../tasks/vendor_ryven_tasks.md`](../tasks/vendor_ryven_tasks.md)
- 蓝图方向历史：[`../archive/blueprint_integration_archive.md`](../archive/blueprint_integration_archive.md)
