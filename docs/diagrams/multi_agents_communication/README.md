# 多 Agents 通信流程图

本目录保存当前 multi-agent TCP 框架的通信流程图。SVG 图片已经翻译为中文，并且每张图底部都带有关键函数、变量、事件名的中文解释；`.mmd` 文件保留 Mermaid 源，方便后续编辑。

## 文件说明

- `01_overview.svg` / `01_overview.mmd`：控制面、运行时、队列、TCP、worker、状态查询和结束流程总览。
- `02_fanout_dispatch.svg` / `02_fanout_dispatch.mmd`：一对多 `agent.dispatch` 与 outgoing batch 暂存分发流程。
- `03_fanin_join.svg` / `03_fanin_join.mmd`：多来源 fan-in、`JoinBarrier` 与 `join_aggregate` 汇聚流程。
- `04_tcp_delivery.svg` / `04_tcp_delivery.mmd`：底层 TCP 投递链路，覆盖 `CLIWorkerBackend`、`AgentTCPClient`、`Broker`、worker 进程和 `CLIAdapter`。

SVG 文件可以直接作为本地图片打开；`.mmd` 文件用于后续重绘或同步到 Mermaid 文档。
