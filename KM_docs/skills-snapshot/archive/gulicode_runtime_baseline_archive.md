# GuLiCode 运行基线变更归档

本文件只记录 `multi_agent_tcp` 在 GuLiCode / OpenCode 运行基线方向上的历史变更，便于后续回顾。

## 变更记录

### 2026-04-25 — 归档结构重组：新增专题文档并同步 GuLiCode 启动基线

#### 摘要
1. 在 skill 目录下新增 `archive/` 子目录，用于按主题拆分长期归档。
2. 新增 GuLiCode 专题归档，记录从精简快照策略切换为“完整可启动 workspace 基线”的方法。
3. 确认 OpenCode 根许可证为 MIT，可作为项目内源码基线引入并大改，但需保留许可证与来源说明。
4. 验证 `multi_agent_tcp/GuLiCode/` 的最小 CLI 入口可以运行，说明当前基线已具备继续裁剪与迁移的前提。

#### 涉及
- `archive/gulicode_runtime_baseline_archive.md`
- `multi_agent_tcp/GuLiCode`

---

## 当前结论

### 背景

本方向的目标是在 `multi_agent_tcp` 中引入 OpenCode 的合适部分，并建立一个可逐步迁移、可持续裁剪的启动基线，而不是只保存零散源码快照。

### 结论

- OpenCode 根许可证为 MIT，可作为项目内源码基线引入并大改，但需保留许可证与来源说明。
- 仅抽取少量 package 的“精简版 GuLiCode”无法可靠启动，workspace 依赖、`catalog:` 引用与内部包导出会断裂。
- 因此策略调整为：先重建为完整可启动 workspace 基线，再逐步裁剪。

### 最终结构

已在项目内建立：

```text
multi_agent_tcp/GuLiCode/
```

并按“完整 workspace，排除缓存/产物”的原则重建，保留：

- `package.json`
- `bun.lock`
- `bunfig.toml`
- `tsconfig.json`
- `turbo.json`
- `sst.config.ts`
- `sst-env.d.ts`
- `packages/`
- `sdks/`
- `github/`
- `patches/`
- `.opencode/`
- `LICENSE`
- `README.vendor.md`

同时删除：

- `node_modules`
- `dist`
- `.next`
- `.turbo`
- `.sst`
- `.git`

### 启动验证结论

本轮已验证：

```bash
bun run --cwd packages/opencode --conditions=browser src/index.ts --help
```

可成功运行，并输出 OpenCode CLI 帮助信息，期间还完成了一次数据库迁移。

这意味着当前 `GuLiCode` 已具备：

- 完整 workspace 结构
- Bun 依赖解析能力
- 可运行的最小启动基线

### 方法论结论

对这种重度 workspace/monorepo 项目，正确迁移顺序应为：

1. 先建立完整可启动基线
2. 每裁一次就复测启动
3. 在持续可运行的前提下逐步收缩到最小核心

而不是先做静态精简快照再试图补齐缺失依赖。

### 后续建议

1. 对 `GuLiCode` 做“可验证裁剪”，每删一组 package 就做一次启动测试。
2. 优先识别并保留最核心的：
   - `packages/opencode`
   - `packages/shared`
   - 视情况保留 `packages/plugin`、`packages/script`、`packages/sdk/js`
3. 后续再逐步做去 OpenCode 化：
   - 改项目名
   - 改入口
   - 改包边界
   - 去掉不需要的 provider / UI / 平台面
