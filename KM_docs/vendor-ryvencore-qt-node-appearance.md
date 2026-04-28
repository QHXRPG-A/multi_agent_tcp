# vendor / ryvencore_qt：节点外观与主题设计

本文说明 `multi_agent_tcp/vendor` 下 **Ryven / ryvencore_qt** 流图编辑器中，**节点（Node）、端口（Port）、标题**等视觉如何组织与实现，便于维护或二次换肤。

## 适用范围

- 主要代码包：`vendor/ryvencore_qt/ryvencore_qt/`
- 节点绘制基于 **Qt Graphics**（`QGraphicsObject` + `QPainter`），不是单独一套 QSS 皮肤文件。
- 同目录下的 `vendor/ryven/` 多为应用级样式表（`resources/stylesheets`），与 ryvencore_qt 内这套 **FlowTheme** 属于不同层次。

## 架构概览

| 层级 | 路径（相对 `vendor/ryvencore_qt/ryvencore_qt/src/`） | 职责 |
|------|------------------------------------------------------|------|
| 会话设计 | `Design.py` | 当前 `FlowTheme`、性能模式（`pretty` / `fast`）、节点阴影开关、动画开关；可选从 JSON 加载主题；注册字体（Poppins、Source Code Pro、Asap）。 |
| 流图主题 | `flows/FlowTheme.py` | 基类 `FlowTheme` 定义钩子；各子类实现 `paint_NI` / `draw_NI_*`、标题与端口绘制、连线颜色、画布背景等。 |
| 节点图元 | `flows/nodes/NodeItem.py` | `QGraphicsObject`：`paint()` 委托给 `session_design.flow_theme.paint_NI(...)`；`update_design()` 挂载或移除 `QGraphicsDropShadowEffect`。 |
| 标题 | `flows/nodes/NodeItem_TitleLabel.py` | 调用 `flow_theme.paint_NI_title_label(...)`。 |
| 端口 | `flows/nodes/PortItem.py` | 调用 `flow_theme.paint_PI` / `paint_PI_label`。 |
| 布局 | `flows/nodes/NodeItemWidget.py` | 使用 `flow_theme.header_padding` 等几何参数。 |

## Design：主题与性能

`Design`（`Design.py`）在初始化时设置默认主题（`flow_themes` 列表的最后一项为默认）、性能模式与动画。

- **`set_flow_theme`**：切换主题时重建 `node_selection_stylesheet`（部分主题为浅色面板定制 QSS），并发出 `flow_theme_changed`。
- **`set_performance_mode('fast')`**：关闭 `node_item_shadows_enabled`，减少阴影开销。
- **`load_from_config`**：从 JSON 读取 `flow themes`、`init flow theme`、`init performance mode` 等字段，并调用各主题的 `load()` 做字段覆盖。

字体通过 **`Design.register_fonts()`** 从 `resources/fonts/` 加载。

## FlowTheme：外观的核心

文件：`flows/FlowTheme.py`。

### 基类约定

- **`paint_NI`**：根据 `node_style`（`'normal'` / `'small'`）调用 `draw_NI_normal` 或 `draw_NI_small`。
- **`paint_NI_title_label` / `paint_PI` / `paint_PI_label`**：子类覆盖以实现不同字体、颜色、对齐与端口形状。
- **`paint_NI_selection_border`**：选中高亮框（基类提供默认圆角矩形逻辑）。
- **连线与画布**：如 `exec_conn_color`、`data_conn_color`、`flow_background_brush`、`flow_background_grid` 等类属性；部分键可通过 `load()` / `_load()` 从配置 JSON 覆盖（见各主题 `EXPORT` 列表）。

### 内置主题（`flow_themes` 列表）

包含但不限于：Toy、Tron（DarkTron）、Ghost、Blender、Simple、Ueli、pure dark、colorful dark、pure light、colorful light、Industrial、Fusion 等。每种主题对「圆角矩形 / `QPainterPath` / 线性或径向渐变」的组合不同，例如：

- **Industrial**：执行端口为**三角形**，数据端口为双椭圆描边风格。
- **Toy**：圆角卡片 + 径向渐变 body、线性渐变 header。
- **PureDark / PureLight**：偏扁平分区与细线分割标题区。

新增视觉风格时，通常 **新增 `FlowTheme` 子类** 并挂入文件末尾的 `flow_themes` 列表（若 Ryven CLI 硬编码了主题名，需同步维护，见 `FlowTheme.py` 顶部注释）。

## NodeItem：绘制入口

`NodeItem.paint()` 不自行画形状，而是把几何与状态交给当前主题：

- 传入：`selected`、`hovered`、`node_style`、`color`（可由 `NodeItemAnimator` 驱动）、`bounding_rect`、`title_rect` 等。
- 首次绘制后会触发 `update_shape()` 等，以在 `QGraphicsWidget` 布局就绪后得到正确的包围盒（见类内注释与 Qt 论坛链接）。

阴影在 **`update_design()`** 中：当 `session_design.node_item_shadows_enabled` 为真时，设置 `QGraphicsDropShadowEffect`（偏移、模糊半径、`flow_theme.node_item_shadow_color`）；否则 `setGraphicsEffect(None)`。

## 与 ryven 目录的区别（简述）

- **ryvencore_qt**：节点/端口/连线由 **`FlowTheme` + `QPainter`** 绘制，主题切换走 `Design.set_flow_theme`。
- **ryven**：更多面向整个应用的 **QSS / 图标资源**（`vendor/ryven/ryven/resources/stylesheets/`），不替代上述节点绘制管线。

## 关键文件速查

```
vendor/ryvencore_qt/ryvencore_qt/src/Design.py
vendor/ryvencore_qt/ryvencore_qt/src/flows/FlowTheme.py
vendor/ryvencore_qt/ryvencore_qt/src/flows/nodes/NodeItem.py
vendor/ryvencore_qt/ryvencore_qt/src/flows/nodes/NodeItem_TitleLabel.py
vendor/ryvencore_qt/ryvencore_qt/src/flows/nodes/PortItem.py
vendor/ryvencore_qt/ryvencore_qt/src/flows/nodes/NodeItemWidget.py
vendor/ryvencore_qt/ryvencore_qt/resources/fonts/
vendor/ryvencore_qt/ryvencore_qt/resources/node_expand_icon.svg
vendor/ryvencore_qt/ryvencore_qt/resources/node_collapse_icon.svg
```

## 一句话总结

节点外观由 **`FlowTheme` 子类中的命令式 QPainter 绘制** 定义；**`Design`** 负责当前主题、性能模式与阴影；**`NodeItem`** 在 `paint` 中把状态委托给主题，标题与端口同理。换肤或改版应优先改/增 `FlowTheme.py` 中的对应子类，并视需要更新 `Design` 加载逻辑与 JSON 配置 schema。
