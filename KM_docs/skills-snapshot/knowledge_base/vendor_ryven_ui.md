# vendored Ryven / ryvencore_qt 视觉层知识

本文件整理 `multi_agent_tcp/vendor` 下 `Ryven` 与 `ryvencore_qt` 的节点外观、主题与视觉结构知识，便于后续 UI 定制、换肤或节点编辑器二开。

## 适用范围

主要参考：
- [D:\agents\multi_agent_tcp\KM_docs\vendor-ryvencore-qt-node-appearance.md](D:\agents\multi_agent_tcp\KM_docs\vendor-ryvencore-qt-node-appearance.md)

相关目录：
- `vendor/ryvencore_qt/ryvencore_qt/`
- `vendor/ryven/ryven/`

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

## 对 skill 的意义

这部分知识适合归入长期知识库，而不是只留在归档中，因为：

- 它描述的是结构性知识，不是单次历史事件
- 它会直接影响后续 vendor GUI 汉化、节点外观改造和编辑器主题策略
- 它与蓝图系统方向及多 CLI 节点化工作流存在直接联系

## 相关知识

- 多 CLI 与节点工作流方向：[`multi_cli_workflow.md`](multi_cli_workflow.md)
- 蓝图改进方向：[`blueprint_gap_notes.md`](blueprint_gap_notes.md)
- 蓝图方向历史：[`../archive/blueprint_integration_archive.md`](../archive/blueprint_integration_archive.md)
