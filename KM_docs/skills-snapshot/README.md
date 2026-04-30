# multi-agent-tcp Skill 文档快照

> **目的**：把 `multi_agent_tcp` 项目相关的 skill 文档（Cursor 与 CodeMaker 两套）打包到本仓库内，便于：
>
> - **远程仓库的读者** 不必访问本地 `.cursor/` 与 `.codemaker/` 目录就能看到当前最新的 skill 定义；
> - **跨工作区分享**：clone 仓库到任意环境后，开发者可以一眼看到「这个项目假设接入方 agent CLI 拿到的 skill 文档长什么样」；
> - **协作沟通**：在 PR / Issue / Wiki 中能直接链接到 commit-pinned 的 skill 文本，避免「skill 又改了，链接失效」。
>
> **重要**：本文件夹只是**快照**（snapshot），**不是**真正生效的 skill。CodeMaker / Cursor 实际加载的仍是 `.cursor/skills/multi-agent-tcp/` 与 `.codemaker/skills/multi-agent-tcp/` 下的原文件；本快照只在每次 skill 更新后**手动同步**到这里，并随当次提交一并推送。

## 文件清单

| 快照文件 | 源路径（工作区根相对） |
|----------|------------------------|
| [`cursor-SKILL.md`](cursor-SKILL.md) | `.cursor/skills/multi-agent-tcp/SKILL.md` |
| [`cursor-ARCHIVE.md`](cursor-ARCHIVE.md) | `.cursor/skills/multi-agent-tcp/ARCHIVE.md` |
| [`codemaker-SKILL.md`](codemaker-SKILL.md) | `.codemaker/skills/multi-agent-tcp/SKILL.md` |

> `.codemaker/skills/multi-agent-tcp/ARCHIVE.md` 当前不存在；归档历史只在 `.cursor` 一份维护。

## 两份 SKILL.md 的差异

不是同一份文件的双份副本，结构和受众都不同：

- **`cursor-SKILL.md`**：百科式参考。给 Cursor 中的 AI agent 当查阅手册——架构表、API 速查、CLI 速查、协议细节、心跳、归档协议等。
- **`codemaker-SKILL.md`**：处方式工作流。给 CodeMaker / Claude Code / Codex 等 agent CLI 在自己的 prompt 处理过程中**作为发起方调用 `dispatch`** 时严格遵守的「5 步流程」（show-registry → 拆任务 → `--async` → self-work → 轮询 status_file）。

## 同步约定

- **何时更新本快照**：每次修改 `.cursor/skills/multi-agent-tcp/SKILL.md` / `ARCHIVE.md` 或 `.codemaker/skills/multi-agent-tcp/SKILL.md` 后，应一并把内容同步到本目录对应的快照文件；同一个 commit 推上 GitHub。
- **谁是权威源**：源文件（在 `.cursor/` 与 `.codemaker/` 下）是权威；本快照若与源不一致，应以**源为准**重新覆盖快照。
- **不要直接编辑本快照**：本快照是被动复制的产物；如需修改 skill 内容，请改源文件后重新拷贝。
- **历史快照**：每次推送等于把当时的 skill 文本钉死在 git history；按 `git log -- multi_agent_tcp/KM_docs/skills-snapshot/` 即可回看任意历史版本。

## 与项目的定位关系

`multi_agent_tcp` 的项目定位是「多 agent CLI 之间的对等通信总线 + 多 agent 生命周期/会话/能力管理」（详见同目录上层 [`../../README.md`](../../README.md) 与 [`../../ROADMAP.md`](../../ROADMAP.md)）。skill 文档是这套定位下「**接入方 agent 拿到的能力声明 + 行为约定**」的核心载体——快照让远程读者看到这些行为约定的当前形态。
