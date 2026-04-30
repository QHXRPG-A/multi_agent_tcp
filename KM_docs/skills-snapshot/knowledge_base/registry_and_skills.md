# Registry 与 Skill 体系

参见 [`core_architecture.md`](core_architecture.md) 获取总览。

## agents_registry.json

用户可通过 `python -m multi_agent_tcp registry-ui` 图形界面管理，或直接编辑 JSON。

```json
{
  "skill_list_dir": "skill_list",
  "agents": {
    "agent-1": {
      "display_name": "助手 Alpha",
      "model": "netease-codemaker/kimi-k2.5",
      "cwd": "F:/src/Package/Script/Python",
      "skills": ["excel-export-flow", "messiah-ui-dev"],
      "timeout_sec": 1800,
      "enabled": true
    }
  }
}
```

## Skill 合并

```bash
python -m multi_agent_tcp.init_skill_list [--force]
```

将 `.codemaker/skills` 和 `.cursor/skills` 合并到 `skill_list/`：
- 重复 skill 以 `.codemaker` 为准
- 生成 `skill_list/manifest.json`
- `skill_list/` 为重建产物，必要时重跑即可

## Skill 注入策略

推荐 `catalog` 模式，而不是把全部 `SKILL.md` 直接嵌入 prompt。

```python
reg = AgentsRegistry.load()
prompt = reg.inject_skills_into_prompt("agent-1", task, mode="catalog")
prompt = reg.inject_skills_into_prompt("agent-1", task, mode="full")
```

catalog 示例：

```text
| Skill | Description | SKILL.md Path |
|-------|-------------|---------------|
| `excel-export-flow` | 导表流程 | `F:/.../skill_list/excel-export-flow/SKILL.md` |
| `messiah-ui-dev` | 弥赛亚UI开发 | `F:/.../skill_list/messiah-ui-dev/SKILL.md` |

Total: 2 skill(s). Use the `read` tool to load the full SKILL.md when needed.
```

## Registry 相关对象

- `AgentsRegistry`
- `AgentProfile`
- `SkillInfo`
- `AgentSession`

## Registry UI

`registry_ui.py` 提供 Tkinter 图形管理界面，可视化编辑 `agents_registry.json`，包含：
- 卡片网格
- 编辑对话框
- model 实时下拉
- skill 多选弹窗

## 相关知识

- Dispatch 工作流：[`dispatch_workflows.md`](dispatch_workflows.md)
- Cluster API：[`cluster_api.md`](cluster_api.md)
- 主架构：[`core_architecture.md`](core_architecture.md)
- 多 CLI 方向：[`multi_cli_workflow.md`](multi_cli_workflow.md)
