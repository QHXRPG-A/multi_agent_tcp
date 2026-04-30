# vendored Ryven / UI 方向任务

## 目标

为未来节点编辑器、蓝图体验和 vendor GUI 定制建立明确的近期推进项。

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

## 依赖知识

- [`../knowledge_base/vendor_ryven_ui.md`](../knowledge_base/vendor_ryven_ui.md)
- [`../knowledge_base/blueprint_gap_notes.md`](../knowledge_base/blueprint_gap_notes.md)
- [`../archive/blueprint_integration_archive.md`](../archive/blueprint_integration_archive.md)
