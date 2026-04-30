# 蓝图集成变更归档

本文件只记录 `multi_agent_tcp` 在蓝图 / Ryven / vendor GUI 方向上的历史变更，便于后续回顾。

## 变更记录

### 2026-04-26 — 仅文档/skill 同步：对齐当前仓库路径与 vendored Ryven 工作结论

#### 摘要
1. 路径与入口校正：补充当前仓库常见路径 `d:\agents\multi_agent_tcp`，并明确 `multi_agent_tcp/__main__.py`、`multi_agent_tcp/cluster.py`、`multi_agent_tcp/registry.py` 位于根包目录。
2. 文档对齐范围补充：归档时除代码外，同时对照 `README.md`、`GUIDE_FOR_CODEMAKER.md`、`examples/HOWTO.txt`。
3. vendored Ryven 结论沉淀：记录 `vendor/ryven`、`vendor/ryvencore_qt`、`.venv_vendor_ryven` 的职责与用途，并确认 GUI 启动验证和中文界面定制已完成。
4. 归档协议增强：若后续工作涉及 `vendor/` 方向的重要运行基线、启动验证或 GUI 汉化，应继续沉淀到对应归档中。

#### 涉及
- `SKILL.md`
- `vendor/ryven`
- `vendor/ryvencore_qt`
- `.venv_vendor_ryven`

---

### 2026-04-25 — 归档结构重组：新增专题文档并同步 Ryven 工作结论

#### 摘要
1. 在 skill 目录下新增 `archive/` 子目录，用于按主题拆分长期归档。
2. 新增蓝图专题归档，记录 Ryven 蓝图系统引入、许可判断、vendoring 结构与启动验证。
3. 确认 `Ryven` / `ryven-editor` / `ryvencore-qt` 为 MIT，可在项目中 vendoring 并深度修改，但需保留许可证与来源说明。
4. 验证 vendored Ryven 可在独立虚拟环境中启动，作为后续蓝图系统二开的运行基线。

#### 涉及
- `archive/blueprint_integration_archive.md`
- `multi_agent_tcp/vendor/ryven`
- `multi_agent_tcp/vendor/ryvencore_qt`

---

## 当前结论

### 背景

本方向的工作围绕在 `multi_agent_tcp` 内建立一个可内置、可深改的 Python 可视化蓝图/节点系统基线，最终选择将 Ryven 作为蓝图侧参考实现，并将其源码 vendoring 到项目目录中。

### 结论

- Ryven 主仓与 `ryven-editor`、`ryvencore-qt` 许可证均为 MIT，可复制进项目并做大改，但需保留版权与许可证文本。
- 顶层 README 还提到外部依赖 `ryvencore` 为 LGPL-2.1；本轮未把其源码 vendoring 进项目，仅在运行环境中安装依赖。
- 已将适合深改的核心源码复制到：
  - `multi_agent_tcp/vendor/ryven/ryven/`
  - `multi_agent_tcp/vendor/ryvencore_qt/ryvencore_qt/`
- 已保留许可证与来源说明：
  - `multi_agent_tcp/vendor/ryven/LICENSE`
  - `multi_agent_tcp/vendor/ryven/LICENSE.editor`
  - `multi_agent_tcp/vendor/ryven/LICENSE.ryvencore_qt`
  - `multi_agent_tcp/vendor/ryven/README.vendor.md`

### 结构规划

推荐继续保持以下结构：

```text
multi_agent_tcp/
  vendor/
    ryven/
      ryven/
      LICENSE*
      README.vendor.md
    ryvencore_qt/
      ryvencore_qt/
```

其设计目标是：

- 让上游来源和本地自改代码边界清晰
- 保留可运行蓝图基线
- 避免把第三方依赖的 `site-packages`、虚拟环境或安装元数据一并提交进仓库

### 启动验证结论

本轮已完成 vendored Ryven 的启动验证：

- 新建 `multi_agent_tcp/.venv_vendor_ryven`
- 安装运行依赖：`PySide6`、`qtpy`、`waiting`、`textdistance`、`Jinja2`、`Pygments`、`packaging`、`ryvencore`
- 通过 `PYTHONPATH` 显式指向 vendored 目录启动
- 验证到 GUI 进程可进入运行态

当前的 vendored Ryven 可作为后续多模态蓝图系统二开的启动基线。

### 后续建议

1. 继续让 vendored Ryven 完全自洽，减少对原始 `d:\agents\Ryven` 安装元数据的借用。
2. 为 `multi_agent_tcp` 增加自己的蓝图启动入口和节点包。
3. 在多模态方向上优先规划：
   - 节点端口类型
   - 媒体引用/大对象传输方式
   - 图执行与缓存
