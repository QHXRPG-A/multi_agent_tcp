# GuLiCode 移动端 PWA 技术设计

## 目标

本文定义 GuLiCode 移动端第一版客户端的技术选型和接入方式。结论是：在现有 `GuLiCode/packages/app` 的 SolidJS + Vite 前端上增量接入 PWA 能力，优先使用 `vite-plugin-pwa + Workbox`，不另起 Vue/React/Flutter/原生移动端工程。

核心目标：

- 让手机端可以像 App 一样打开 GuLiCode 远程协作入口。
- 复用现有 SolidJS/Vite 前端主线，避免维护第二套 UI 和状态体系。
- 移动端只通过 GuLiCode Collaboration Server 工作，不直连 Python Runtime。
- PWA 只缓存前端 shell 和静态资源，不缓存运行事实、登录态、SSE 事件流和 runtime 响应。
- 第一版完成“派单、看状态、审批、看报告”的移动端闭环；原生壳、推送和上架后置。

本文是工程设计稿，不是具体实现 PR。实际落地时应继续服从 `docs/gulicode_collaboration_server_design.md` 中的服务端边界。

## 推荐结论

推荐技术栈：

```text
GuLiCode existing SolidJS + Vite app
  + vite-plugin-pwa
  + Workbox
  + Web App Manifest
  + mobile-first CSS and safe-area handling
  -> GuLiCode Collaboration Server
  -> Python Runtime Service
  -> GraphRuntimeControlPlane / GraphRuntime
```

不推荐第一阶段采用：

- 不新建 Vue 移动端，除非明确决定移动端长期独立演进。
- 不使用 Flutter / React Native 重写，因为当前移动端不是复杂本地 UI 或本地计算场景。
- 不拆 Swift + Kotlin 双原生客户端，因为成本和发布面过大。
- 不把 PWA 包装成原生壳作为 MVP 起点；Capacitor / Android TWA 应作为第二阶段分发能力。

## 现有项目适配点

当前 GuLiCode 前端主线已经满足 PWA 增量接入条件：

- `GuLiCode/packages/app` 使用 Vite。
- `GuLiCode/packages/app` 已使用 SolidJS、`@solidjs/router`、Tailwind 和现有 app 插件。
- `GuLiCode/packages/desktop` 复用 `@opencode-ai/app`，移动端改造应优先发生在共享 app 层，而不是 Tauri 桌面壳层。

建议接入位置：

| 位置 | 用途 |
| --- | --- |
| `GuLiCode/packages/app/vite.config.ts` | 增加 `VitePWA` 插件配置 |
| `GuLiCode/packages/app/public/` | 放置 PWA icons、favicon、apple touch icon |
| `GuLiCode/packages/app/src/` | 增加 PWA 注册入口、更新提示、移动端布局适配 |
| `GuLiCode/packages/desktop/vite.config.ts` | 暂不优先改动，桌面壳通过 app 包复用产物 |

## 可复用开源项目

### `vite-plugin-pwa`

用途：Vite 项目 PWA 插件，负责 manifest 注入、Service Worker 生成、Workbox 集成、更新注册。

适配方式：直接集成到现有 Vite 配置，不搬模板。

参考：

- https://github.com/vite-pwa/vite-plugin-pwa
- https://vite-pwa-org.netlify.app/examples/solidjs.html

### Workbox

用途：Service Worker 缓存策略、预缓存、运行时缓存、过期清理。

适配方式：第一版使用 `vite-plugin-pwa` 的 `generateSW` 模式和 `workbox` 配置。后续如果需要完全控制 SSE 排除、消息同步或离线队列，再切到 `injectManifest` 自定义 Service Worker。

参考：

- https://developer.chrome.com/docs/workbox

### `solidjs/solid-site`

用途：真实 SolidJS 站点中使用 `vite-plugin-pwa` 的参考，不作为代码基线迁移。

适配方式：只借鉴 PWA 测试、自动更新和 HTTPS preview 流程。

参考：

- https://github.com/solidjs/solid-site

### PWABuilder

用途：PWA 验收、manifest/icon 检查、后续商店包生成。

适配方式：第一版只作为检查工具；不把 PWABuilder starter 作为项目模板。

参考：

- https://docs.pwabuilder.com/

### Capacitor

用途：后续原生壳，支持 iOS / Android 上架、深链、推送、原生安全存储和设备 API。

适配方式：PWA 闭环稳定后再引入。Capacitor 不应成为第一阶段 UI 架构中心。

参考：

- https://capacitorjs.com/

## PWA 与服务端边界

移动端 PWA 只负责用户交互和展示，不拥有调度事实。

```text
Mobile PWA
  -> HTTPS + httponly cookie
  -> GuLiCode Collaboration Server
  -> runtime proxy with service token
  -> Python Runtime Service
  -> GraphRuntimeControlPlane / GraphRuntime
```

PWA 不得访问：

- runtime RPC token
- workspace RPC token
- MCP bearer token
- Agent private checkout path
- Codex home
- SSH tunnel / VPS internal port
- service token

PWA 可以展示：

- 当前用户和项目列表
- run metadata
- runtime status snapshot
- runtime event journal 的前端规范化事件
- report / artifact / changeset 索引
- 用户可执行的 run control 操作

## 第一阶段范围

### 要做

- 在现有 SolidJS/Vite app 中接入 `vite-plugin-pwa`。
- 增加 `manifest`、PWA 图标和 `display: standalone`。
- 增加基础 Service Worker，仅缓存前端 shell 和静态资源。
- 移动端布局适配：`100dvh`、safe-area、触摸尺寸、输入行为。
- SSE 事件流断线后按 cursor 重连。
- PWA 安装和更新提示。
- 使用 Lighthouse / PWABuilder 做 PWA 基础验收。
- 使用真机 HTTPS 验证 iOS / Android Home Screen 行为。

### 不做

- 不做完整离线编辑。
- 不缓存登录响应、API 响应、runtime status 或 SSE stream。
- 不做多人实时编辑、协同光标、presence。
- 不做原生推送作为第一阶段依赖。
- 不做 App Store / Google Play 上架包。
- 不在移动端直接修改项目文件。

## Vite 接入草案

第一版建议使用 `generateSW`，降低接入复杂度。

```ts
import { defineConfig } from "vite"
import { VitePWA } from "vite-plugin-pwa"
import desktopPlugin from "./vite"

export default defineConfig({
  plugins: [
    desktopPlugin,
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.ico", "apple-touch-icon.png"],
      manifest: {
        id: "/",
        name: "GuLiCode",
        short_name: "GuLiCode",
        description: "GuLiCode mobile collaboration client",
        start_url: "/",
        scope: "/",
        display: "standalone",
        orientation: "portrait-primary",
        theme_color: "#111827",
        background_color: "#ffffff",
        icons: [
          {
            src: "/pwa-192x192.png",
            sizes: "192x192",
            type: "image/png",
          },
          {
            src: "/pwa-512x512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "any maskable",
          },
        ],
      },
      workbox: {
        cleanupOutdatedCaches: true,
        globPatterns: ["**/*.{js,css,html,ico,png,svg,woff,woff2}"],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [
          /^\/auth\//,
          /^\/api\//,
          /^\/runs\//,
          /^\/stream/,
        ],
        runtimeCaching: [
          {
            urlPattern: ({ url }) =>
              url.pathname.startsWith("/stream") ||
              url.pathname.startsWith("/auth/") ||
              url.pathname.startsWith("/api/") ||
              url.pathname.startsWith("/runs/"),
            handler: "NetworkOnly",
          },
          {
            urlPattern: ({ request }) =>
              request.destination === "image" ||
              request.destination === "font" ||
              request.destination === "style" ||
              request.destination === "script",
            handler: "StaleWhileRevalidate",
            options: {
              cacheName: "gulicode-static-assets",
              expiration: {
                maxEntries: 128,
                maxAgeSeconds: 7 * 24 * 60 * 60,
              },
            },
          },
        ],
      },
      devOptions: {
        enabled: false,
      },
    }),
  ] as any,
  server: {
    host: "0.0.0.0",
    allowedHosts: true,
    port: 3000,
  },
  build: {
    target: "esnext",
  },
})
```

注意：上述是设计草案。实际实现时应根据当前 `desktopPlugin` 类型和构建产物调整 TypeScript 类型。

## 缓存策略

PWA 的缓存目标是提升启动速度和弱网体验，不是把 GuLiCode runtime 做成本地离线系统。

| 资源 | 策略 | 原因 |
| --- | --- | --- |
| `index.html` | 预缓存或网络优先，配合更新机制 | 保证 app shell 可启动，但不能长期卡旧版本 |
| JS / CSS hashed assets | 预缓存 | Vite 产物带 hash，适合静态缓存 |
| icons / fonts | `StaleWhileRevalidate` | 提升启动速度 |
| `/auth/*` | `NetworkOnly` | 登录态和 cookie 不能缓存 |
| `/api/*` | `NetworkOnly` | API 返回可能含权限和实时状态 |
| `/runs/*` | `NetworkOnly` | run metadata 和状态必须来自服务端 |
| `/stream` | `NetworkOnly` | SSE 必须保持实时网络连接 |
| reports / artifacts | 第一版 `NetworkOnly` | 避免缓存敏感产物；后续只允许缓存内容寻址且权限安全的只读文件 |

如果后续要缓存 report / artifact，必须满足：

- URL 包含不可变版本或内容 hash。
- 响应不包含 runtime token、workspace token 或私有路径。
- 服务端明确设置缓存头。
- 用户登出时清理相关 Cache Storage。

## SSE 事件流要求

第一版运行状态主要是 server-to-client，因此继续使用 SSE。

客户端要求：

- 建立 `GET /stream?runId=...&cursor=...`。
- 记录最近已处理事件 id / cursor。
- 网络断开、页面后台恢复、锁屏后恢复时按 cursor 重连。
- 重连后必须幂等应用事件，避免重复展示用户确认、工具卡片或状态迁移。
- 不通过 Service Worker 缓存 `/stream`。

建议行为：

```text
open run panel
  -> load /runs/:runId/status from network
  -> connect /stream?runId=...&cursor=lastCursor
  -> apply runtime events
  -> persist lastCursor in session-level client state
  -> visibilitychange/pageshow reconnect if needed
```

如果未来需要多人协同编辑、实时输入、光标 presence 或双向消息流，再在 Collaboration Server 上引入 WebSocket。WebSocket 不应替代 TLS，也不应自定义加密协议。

## 移动端 UI 要求

移动端页面不是桌面端缩小版，应围绕派单和监控设计。

第一版至少需要：

- 使用 `100dvh`，避免 iOS 地址栏导致的高度错误。
- 使用 `env(safe-area-inset-*)` 处理刘海屏和 Home indicator。
- 输入框 `font-size` 不小于 `16px`，避免 iOS 聚焦自动放大。
- 桌面端 Enter 发送，移动端 Enter 换行。
- 长列表使用虚拟滚动或分页加载，首屏只加载最近记录。
- 工具调用卡片、Agent 发言、report 入口可折叠。
- 运行中状态区域保持稳定高度，避免 SSE 事件导致布局跳动。
- 底部操作区避开 safe-area，并保持主要操作可单手触达。

建议页面优先级：

1. 登录页。
2. 项目列表。
3. run 列表。
4. run 详情：状态、事件流、Agent 发言、工具卡片、报告入口。
5. 创建 run：top-agent 指令、blueprint 选择、提交。
6. 审批和结束操作：confirm / reject / pause / cancel / archive。

## 安全约束

PWA 安全边界必须比普通网页更严格，因为它会被用户当作 App 长期使用。

要求：

- 生产环境必须使用 HTTPS。
- 浏览器登录态使用 `httponly`、`secure`、`sameSite=lax` cookie。
- 前端不得持久化 runtime token、workspace token、service token。
- Service Worker 不缓存任何包含权限、token、私有路径或运行事实的响应。
- 登出时清理前端内存状态，并请求服务端注销 session。
- 如果使用 Cache Storage 缓存 report / artifact，必须在登出或切换账号时清理。
- 错误页面不能泄露 upstream 地址、VPS 内部端口、隧道信息或本机路径。

## 本地开发与真机测试

### 桌面浏览器

开发阶段可以使用：

```text
bun --cwd GuLiCode/packages/app dev
```

`localhost` 在现代浏览器中通常被视为安全上下文，足够验证 manifest、Service Worker 注册、基础缓存和 app shell 行为。

开发期建议默认关闭 Service Worker，避免旧缓存干扰调试。需要调试 PWA 时再通过专用环境变量或临时配置打开 `devOptions.enabled`。

### 真机测试

手机不能访问开发机上的 `localhost`。真机测试建议使用：

- 局域网 IP + 本地 HTTPS 证书。
- Caddy 反代到本机 Vite dev server。
- Tailscale / Cloudflare Tunnel / ngrok。
- 测试 VPS 域名 + HTTPS。

必须真机验证：

- iOS Safari 添加到主屏幕。
- Android Chrome 安装 PWA。
- standalone 模式下 safe-area 是否正确。
- 锁屏/后台恢复后 SSE 是否能按 cursor 续连。
- 弱网和断网时 app shell 是否可打开，动态数据是否明确显示网络错误。
- 更新发布后是否能拿到新版前端资源。

## 验收标准

PWA 基础验收：

- Lighthouse PWA 检查通过关键项。
- PWABuilder 不报告 manifest/icon/blocking 问题。
- `display: standalone` 生效。
- iOS / Android 主屏幕图标、名称、启动背景正确。
- 静态 shell 可被缓存，断网时能显示明确的离线或重连状态。

业务验收：

- 未登录访问项目返回登录页或 401 展示。
- 登录后能读取项目列表。
- 能创建 run，且创建失败时展示服务端返回的稳定错误格式。
- 能连接 SSE 并接收 status、agent utterance、tool card、report 事件。
- SSE 断开后能按 cursor 重连，不重复应用已处理事件。
- `/stream`、`/runs/*`、`/auth/*`、`/api/*` 不被 Service Worker 返回旧缓存。
- 登出后不能通过浏览器后退或离线缓存看到敏感运行数据。

## 分阶段实施计划

### 阶段 1：PWA 基础设施

- 安装 `vite-plugin-pwa`。
- 添加 manifest、icons、apple touch icon。
- 配置 Workbox 静态资源缓存和动态接口 `NetworkOnly`。
- 增加 PWA 注册入口和更新提示。
- 桌面浏览器验证构建产物。

### 阶段 2：移动端页面闭环

- 登录、项目列表、run 列表、run 详情移动端适配。
- 创建 run 表单移动端适配。
- SSE 状态流、工具卡片、报告入口移动端适配。
- safe-area、`100dvh`、输入行为和触摸尺寸修正。

### 阶段 3：真机和弱网硬化

- HTTPS 真机测试。
- 后台恢复和断线重连。
- 更新提示和缓存清理。
- 登出和切换账号缓存安全验证。
- Lighthouse / PWABuilder 验收。

### 阶段 4：原生壳评估

当 PWA 闭环稳定后，再评估：

- Android TWA：适合低成本上 Google Play。
- Capacitor：适合 iOS / Android 统一原生壳、推送、深链和原生安全存储。
- 原生插件：只在明确需要系统能力时添加。

阶段 4 不应改变业务事实源。即使套原生壳，移动端仍然通过 Collaboration Server 工作，不能直连 Python Runtime 或 workspace RPC。

## 风险与对策

| 风险 | 对策 |
| --- | --- |
| Service Worker 返回旧 `index.html` 导致资源 404 | 使用 hashed assets、`cleanupOutdatedCaches`、更新提示和谨慎的 `navigateFallback` |
| API 或 SSE 被错误缓存 | 明确 `NetworkOnly`，并在测试中检查 DevTools network source |
| iOS 后台恢复后 SSE 断开 | 使用 `visibilitychange` / `pageshow` 触发 status reload 和 cursor reconnect |
| PWA 被当作离线 App 使用 | 离线时只展示 shell 和重连状态，不允许创建虚假 run |
| 多账号缓存串号 | 登出清理 client state，动态数据不进入 Cache Storage |
| 移动端 UI 过度复用桌面布局 | 为 run list / run detail / composer 建立移动端布局断点 |

## 后续开放问题

- PWA 是否作为 `packages/app` 的默认能力，还是只在远程协作构建中启用。
- 是否需要独立 `mobile` 路由布局，还是通过响应式布局覆盖现有页面。
- reports / artifacts 是否允许内容寻址缓存。
- 是否需要后台 Web Push，还是第一版仅靠用户主动打开查看。
- 如果引入 Capacitor，原生壳是否复用同一 build 产物，还是需要独立 mobile build profile。

## 参考

- `docs/gulicode_collaboration_server_design.md`
- `GuLiCode/packages/app/package.json`
- `GuLiCode/packages/app/vite.config.ts`
- `GuLiCode/packages/desktop/vite.config.ts`
- https://github.com/vite-pwa/vite-plugin-pwa
- https://vite-pwa-org.netlify.app/examples/solidjs.html
- https://developer.chrome.com/docs/workbox
- https://github.com/solidjs/solid-site
- https://docs.pwabuilder.com/
- https://capacitorjs.com/
