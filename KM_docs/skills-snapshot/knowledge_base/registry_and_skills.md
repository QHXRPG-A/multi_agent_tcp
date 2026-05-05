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
      "skill_selection": {
        "mode": "selected",
        "skill_hashes": ["excel-export-flow", "messiah-ui-dev"]
      },
      "timeout_sec": 1800,
      "enabled": true
    }
  }
}
```

## Agent skill selection

`AgentProfile` 与 `AgentNode` 共享 `AgentSkillSelection` 的用户侧模型：

- `none`：不暴露任何 skill。
- `all`：暴露当前 `skill_list/manifest.json` 中的全部 skill。
- `selected`：只暴露用户显式选择的 skill。
- `upstream`：由图运行时上游超级 agent 分配 skill；registry 静态注入阶段不解析。

兼容规则：

- 旧配置中的 `skills: [...]` 会继续被读取，并按 `selected` 解释。
- registry 体系里的 skill 标识仍是 `skill_list` 中的 skill 名称；为了与图运行时模型复用，当前存放在 `skill_selection.skill_hashes` 字段。
- `show-registry` 与 session snapshot 会输出 `skill_selection`，同时保留解析后的 `skills` 描述列表。

示例：

```json
{
  "skill_selection": {"mode": "none"}
}
```

```json
{
  "skill_selection": {"mode": "all"}
}
```

```json
{
  "skill_selection": {
    "mode": "selected",
    "skill_hashes": ["excel-export-flow"]
  },
  "skills": ["excel-export-flow"]
}
```

```json
{
  "skill_selection": {"mode": "upstream"}
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
- skill mode 下拉：`none` / `all` / `selected` / `upstream`
- `selected` 模式下的 skill 多选弹窗、全选和清空

## 相关知识

- Dispatch 工作流：[`dispatch_workflows.md`](dispatch_workflows.md)
- Cluster API：[`cluster_api.md`](cluster_api.md)
- 主架构：[`core_architecture.md`](core_architecture.md)
- 多 CLI 方向：[`multi_cli_workflow.md`](multi_cli_workflow.md)
