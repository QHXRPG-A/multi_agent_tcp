# CLI 速查

本文件只做命令索引，工作流说明见 [`dispatch_workflows.md`](dispatch_workflows.md)。

## 推荐 LLM 两步流程

```text
python -m multi_agent_tcp show-registry [-o agents.json]
python -m multi_agent_tcp dispatch --tasks tasks.json [-o result.json] [--max-retries 2] [--skill-mode catalog]
python -m multi_agent_tcp dispatch --tasks-json '[{"agent_id":"agent-1","prompt":"..."}]' -o result.json
python -m multi_agent_tcp dispatch --async --tasks tasks.json
python -m multi_agent_tcp dispatch-status --job-id <job_id> [--wait 25]
```

## Session-gated dispatch（legacy）

```text
python -m multi_agent_tcp list-agents [-o result.json]
python -m multi_agent_tcp run-agent --session-id 58248 --agent-id agent-1 --prompt "任务描述"
python -m multi_agent_tcp run-agent --session-id 58248 --agent-id agent-1 --prompt-file task.md --skill-mode full
```

## 高层入口

```text
python -m multi_agent_tcp cluster start --config multi_agent_tcp/examples/cluster.json
python -m multi_agent_tcp run-parallel --registry --tasks tasks.json -o result.json --skill-mode catalog
python -m multi_agent_tcp run-parallel --config multi_agent_tcp/examples/cluster.json --tasks multi_agent_tcp/examples/tasks_parallel.json -o result.json
python -m multi_agent_tcp run-parallel --port 9140 --tasks tasks.json
python -m multi_agent_tcp run-parallel --config cluster.json --tasks tasks.json --max-retries 2 --retry-delay-sec 5
python -m multi_agent_tcp run-parallel-reduce --registry --tasks tasks.json --reduce-worker agent-1 --reduce-prompt "Merge:\n{results}" -o result.json
python -m multi_agent_tcp run-chain --registry --tasks tasks.json -o result.json
```

## 低层入口

```text
python -m multi_agent_tcp broker --config multi_agent_tcp/examples/broker.json
python -m multi_agent_tcp agent --config <agent.json> [--mode echo|listen|codex-worker]
python -m multi_agent_tcp spawn --config multi_agent_tcp/examples/spawn_three_codex.json
python -m multi_agent_tcp.orchestrate --recipe multi_agent_tcp/examples/recipe_chain.json
```

## GUI

```text
python -m multi_agent_tcp registry-ui
python -m multi_agent_tcp.registry_ui
python -m multi_agent_tcp ryven
python -m multi_agent_tcp ryven --skip-dialog
```

## Ryven 启动说明

- 对于 vendored `Ryven`，优先使用 `python -m multi_agent_tcp ryven`
- 该入口会统一处理 `sys.path` 注入、`PySide6` 默认选择，以及缺失 `ryven` 包元数据时的兼容逻辑
- 若关闭启动对话框后出现 `Start-up screen dismissed`，通常属于正常退出而非启动失败

## Skill 合并

```text
python -m multi_agent_tcp.init_skill_list [--force]
```

## 演示 / 测试

```text
python -m multi_agent_tcp.demo_three_codexs [--port 9133]
python -m multi_agent_tcp.demo_gclient_three_search [--trace] [--port 9140] [--max-retries 2] [--retry-delay-sec 5]
python -m multi_agent_tcp.test_skill_injection [--agent-id agent-1] [--skill excel-export-flow] [--mode catalog|full]
```
