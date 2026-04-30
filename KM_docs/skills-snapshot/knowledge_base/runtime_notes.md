# 运行时注意事项

## batch_gather 协议

1. 发起方 → broker：`{"type": "batch_gather", "id": "<unique>", "timeout_sec": 300, "items": [{"to": "<agent_id>", "body": <json>}, ...]}`
2. broker → target：标准 `message` 帧 + `gather` 元数据
3. target → broker：标准 `send` 帧 + `gather_reply`
4. broker → 发起方：`gather_result`

常见错误码：
- `pre_check_failed`
- `duplicate_gather_id`
- `timeout`
- `dispatch_failed`
- `target_disconnected`

## 失败重试

`run_parallel()` 支持对可重试错误自动重试：
- 检测 `database is locked`、`resource temporarily unavailable` 等模式
- 失败 worker 逐个串行重试
- 日志前缀：`[retry]`

## `codemaker run` 易错点

1. 必须提供一条 message，仅 `-f` 不够。
2. `run_stub_message` 必须放在 `-f` 前面。
3. 不要在 `-f` 后面再跟长句 argv，否则会被当成文件路径。
4. 中文或非 ASCII prompt 推荐写入 UTF-8 临时文件，经 `-f` 传递。
5. 子进程环境带 `PYTHONUTF8=1`。
6. `--format json` 输出 NDJSON，最终文本答案在 `type=text` 条目中。
7. 模型参数必须是 `netease-codemaker/<model>` 前缀。
8. `cwd` 下 `codemaker.json` 的 `permission` 应为 `allow`，否则可能挂起。
9. `prompt_via_file='never'` + 非 ASCII 在 Windows argv 编码下有风险。

## 心跳探活

1. broker 每 30 秒发 `ping`
2. agent 的 `pump()` 独立回 `pong`
3. 75 秒无帧则 broker 驱逐连接
4. gather 逻辑必须非阻塞 handler 循环

## 日志落盘

`log_setup.setup_logging(verbose, name)` 会写入：
- stderr
- `multi_agent_tcp/logs/{name}_{ts}_{pid}.log`

## 进程树清理

`_proc_utils.py` 提供：
- `kill_process_tree`
- `terminate_and_wait`
- `async_kill_process_tree`

## Windows 编码注意

- 不要通过 PowerShell 管道写中文 JSON。
- 推荐使用 `Path.write_text(encoding="utf-8")` 或 CLI 自带 `-o` 参数。

## 相关知识

- Dispatch 工作流：[`dispatch_workflows.md`](dispatch_workflows.md)
- Cluster API：[`cluster_api.md`](cluster_api.md)
- 主架构：[`core_architecture.md`](core_architecture.md)
- 多 CLI 方向：[`multi_cli_workflow.md`](multi_cli_workflow.md)
