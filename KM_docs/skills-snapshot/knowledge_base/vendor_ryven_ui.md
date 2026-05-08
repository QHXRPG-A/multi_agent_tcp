# vendored Ryven / ryvencore_qt 视觉层知识

本文件整理 `multi_agent_tcp/vendor` 下 `Ryven` 与 `ryvencore_qt` 的节点外观、主题、视觉结构与正式启动入口知识，便于后续 UI 定制、换肤、节点编辑器二开，以及稳定启动 vendored Ryven。

> 当前定位：Ryven 是二级/延后 visual-editor 轨道。当前产品主线是 GuLiCode desktop + GraphRuntimeControlPlane + GraphRuntime。除非用户明确要求 Ryven/editor，本文件只作为历史和备用知识。

## 适用范围

主要参考：
- [D:\agents\multi_agent_tcp\KM_docs\vendor-ryvencore-qt-node-appearance.md](D:\agents\multi_agent_tcp\KM_docs\vendor-ryvencore-qt-node-appearance.md)

相关目录：
- `vendor/ryvencore_qt/ryvencore_qt/`
- `vendor/ryven/ryven/`
- `ryven_launcher.py`
- `__main__.py`

## 核心结论

### 1. 外观不是单纯 QSS

`ryvencore_qt` 的节点、端口、标题等绘制主要基于 Qt Graphics：

- `QGraphicsObject`
- `QPainter`
- `FlowTheme`
- `Design`

因此大部分节点视觉改造不应只盯着 QSS，而要优先关注 `FlowTheme.py` 与相关绘制入口。

### 2. 视觉层的关键分工

- `Design.py`：负责当前 `FlowTheme`、性能模式、阴影、动画、字体注册
- `flows/FlowTheme.py`：定义节点、端口、标题、连线、画布背景的主题绘制逻辑
- `flows/nodes/NodeItem.py`：节点图元绘制入口
- `flows/nodes/NodeItem_TitleLabel.py`：标题绘制
- `flows/nodes/PortItem.py`：端口绘制
- `flows/nodes/NodeItemWidget.py`：节点布局相关参数消费方

### 3. Ryven 与 ryvencore_qt 不是同一层

- `ryvencore_qt`：负责节点图、端口、连线等底层视觉绘制
- `ryven`：更偏应用级资源、样式表和上层界面

做节点编辑器视觉定制时，通常优先从 `ryvencore_qt` 下手；做应用整体风格时，再看 `ryven/resources/stylesheets/` 等资源。

### 4. vendored Ryven 需要专门启动入口

当前仓库中的 `Ryven` 不是通过标准 pip 包安装，而是 vendored 到仓库内，因此直接按普通 `ryven` 命令方式启动并不稳定。主要兼容点包括：

- 需要把 `vendor/ryven` 与 `vendor/ryvencore_qt` 注入 `sys.path`
- 当前 Python 3.11+ / 3.13 环境下默认不应再走 `PySide2`，而应优先使用 `PySide6`
- vendored 目录缺少标准安装元数据时，需要兼容 `importlib.metadata.version('ryven')`

因此仓库内应统一通过正式入口启动：

```text
python -m multi_agent_tcp ryven
```

### 5. 正式启动入口位置

当前仓库已补充正式启动路径：

- `multi_agent_tcp/ryven_launcher.py`：负责 vendored 启动兼容
- `multi_agent_tcp/__main__.py`：提供 `python -m multi_agent_tcp ryven` 子命令

推荐启动方式：

```text
python -m multi_agent_tcp ryven
python -m multi_agent_tcp ryven --skip-dialog
python -m multi_agent_tcp ryven --help
```

### 6. 启动对话框被关闭不算脚本故障

如果运行后出现 `Start-up screen dismissed`，通常表示用户关闭了 Ryven 启动对话框，这是 Ryven 自身的正常退出路径，不表示仓库启动脚本失效。

## 对 skill 的意义

这部分知识适合归入长期知识库，而不是只留在归档中，因为：

- 它描述的是结构性知识，不是单次历史事件
- 它会直接影响后续 vendor GUI 汉化、节点外观改造、编辑器主题策略与启动维护方式
- 它与蓝图系统方向及多 CLI 节点化工作流存在直接联系

## 相关知识

- CLI 入口速查：[`cli_reference.md`](cli_reference.md)
- 多 CLI 与节点工作流方向：[`multi_cli_workflow.md`](multi_cli_workflow.md)
- AgentNode 接入 Ryven 节点 UI：[`agent_node_ryven_integration.md`](agent_node_ryven_integration.md)
- 蓝图改进方向：[`blueprint_gap_notes.md`](blueprint_gap_notes.md)
- 蓝图方向历史：[`../archive/blueprint_integration_archive.md`](../archive/blueprint_integration_archive.md)
