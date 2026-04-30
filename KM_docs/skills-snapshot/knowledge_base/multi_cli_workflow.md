# 多 CLI 接入与节点工作流

本文件整理 `multi_agent_tcp` 在多 CLI agent、节点化编排与多模态消息方面的近期方向性知识。它记录的是当前已明确的设计方向与术语，不等价于“功能已实现”。

## 定位

根据 [D:\agents\multi_agent_tcp\KM_docs\multi-cli-node-workflow-brainstorm.md](D:\agents\multi_agent_tcp\KM_docs\multi-cli-node-workflow-brainstorm.md)，项目正在从“围绕 CodeMaker CLI 的薄编排框架”扩展为：

- 多 CLI agent 接入
- 节点化工作流编排
- 多模态消息总线
- headless 优先的运行时设计

这条线与当前主架构并不冲突，而是其上层扩展方向。

## 关键方向

### 1. CLIAdapter 抽象

当前 `codemaker_bridge.py` 是唯一已落地的 CLI adapter 形态。后续方向是抽出一层薄的 `CLIAdapter`：

- 只负责进程 IO、prompt 传递、输出解析、附件落地
- 不负责 LLM 推理、tool routing、对话历史管理
- 保持 `WorkerResult` / `ParallelResult` / `ReduceResult` 这一套统一结果视图

目标不是“模型抽象层”，而是“CLI 进程适配层”。

### 2. 节点化工作流

在现有 `run_parallel` / `run_chain` / `run_single` 之上，近期方向是把 agent 协作与消息处理建模成图：

- Agent 节点：调一个 CLI 执行 prompt
- 处理节点：模板填充、字段抽取、格式转换
- 路由节点：fan-out、fan-in、switch
- I/O 节点：文件、HTTP、blob 等外部交互

这意味着图编译器未来可能把节点图翻译回：
- `cluster.run_single(...)`
- `cluster.run_parallel(...)`
- `cluster.run_chain(...)`
- `cluster.run_parallel_reduce(...)`
- 更远期的 DAG 执行入口

### 3. MultiModalEnvelope

为避免每加一种媒体都扩端口模型，近期方向统一为一种多模态信封：

- `kind`: `text` / `image` / `audio` / `file` / `blob`
- `mime`
- `encoding`: `inline` / `fileref` / `blobref`
- `value`
- `meta`

其作用是统一节点间边上传递的数据容器，而不是让每条边都绑定一种硬编码类型。

### 4. 多模态数据面

近期路线强调渐进扩展：

1. 先支持 text 与小图的 inline / 临时文件落地
2. 再引入 blob store 与 `blob_put` / `blob_get`
3. 未来如有必要，再考虑更重的跨机二进制传输方案

## 与现有知识库的关系

- 主架构：见 [`core_architecture.md`](core_architecture.md)
- Cluster API：见 [`cluster_api.md`](cluster_api.md)
- Registry / skill 注入：见 [`registry_and_skills.md`](registry_and_skills.md)
- 运行时细节：见 [`runtime_notes.md`](runtime_notes.md)

## 与短期任务的关系

本文件只记录方向性知识与术语。具体近期推进项、拆解任务、优先级与阶段目标，统一放到上级 `tasks/` 目录中。
