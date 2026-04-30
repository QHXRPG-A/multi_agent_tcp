# 蓝图对标改进方向

本文件整理对标 UE5 蓝图时，当前流图栈在类型系统、编辑效率与信息密度方面的主要改进方向。内容基于：

- [D:\agents\multi_agent_tcp\KM_docs\ryvencore-vs-ue5-blueprint-gaps-2-4-8.md](D:\agents\multi_agent_tcp\KM_docs\ryvencore-vs-ue5-blueprint-gaps-2-4-8.md)

## 定位

这些内容属于“近期方向性知识”，不是已完成能力。适合作为：

- 知识库中的设计参考
- 短期任务拆解的输入
- 后续节点编辑器增强的判断依据

## 三条主线

### 1. 类型系统与连线安全

建议把类型问题拆成四层：

- 视觉类型
- 编辑期类型
- 执行期类型
- 序列化 / 存档类型

尤其值得优先补的是编辑期连接规则与错误反馈机制。

### 2. 兼容矩阵

连接关系不应只做“能连 / 不能连”二元判断，更适合拆成：

1. 严格匹配
2. 自动转换
3. 显式转换
4. 拒绝连接

这会直接影响：
- 端口连接提示
- 推荐节点
- 自动补转换节点
- 图级检查与未来迁移

### 3. 编辑效率

与 UE5 蓝图相比，后续值得增强的方向包括：

- 从 pin 拉线的上下文推荐
- 图内 / 跨图搜索与引用图谱
- 子图、宏、函数图等折叠能力
- 基于 `FlowCommands` 的批量重构能力
- Inspector 里更强的解释与数据预览

## 对 skill 的意义

这部分内容不应直接写成“已实现”，但应作为稳定参考知识沉淀下来，因为它会持续影响：

- 节点系统设计
- 端口 schema 与类型兼容矩阵
- 编辑器 UX 改进
- 任务优先级判断

## 相关知识

- 节点工作流方向：[`multi_cli_workflow.md`](multi_cli_workflow.md)
- vendored UI 视觉层：[`vendor_ryven_ui.md`](vendor_ryven_ui.md)
- 近期目标任务：[`../tasks/current_goals.md`](../tasks/current_goals.md)
