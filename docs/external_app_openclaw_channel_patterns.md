# 外部 App 拉起 OpenClaw 对话的接入模式总结

## 当前结论

“其他 App 拉起 OpenClaw”需要先区分两个完全不同的含义：

1. **聊天 App 拉起 OpenClaw 对话**：用户在 WhatsApp、Telegram、Discord、Slack、飞书、LINE、Signal、iMessage 等外部聊天 App 里给某个 bot、账号或号码发消息，OpenClaw Gateway 收到入站消息后路由到 agent 并回复。
2. **业务 App 拉起 OpenClaw UI 或指定会话**：另一个桌面端、移动端或 Web 业务系统直接打开 OpenClaw/GuLiCode 的某个会话、运行或工作台。这一类需要 deep link、universal link、HTTP API 或 Collaboration Server 会话 API。

WhatsApp 的分析结论属于第一类。它的本质是 **账号绑定 + 入站监听 + 权限放行 + agent 路由 + 同渠道回复**，不是生成 `wa.me` / `api.whatsapp.com/send` 链接让用户点击。

因此，其他聊天 App 的核心方法大体类似，但每个平台的“绑定方式”和“入站传输方式”不同。不能把 WhatsApp Web QR 的具体流程照搬到所有 App。

## OpenClaw WhatsApp 链路事实

OpenClaw WhatsApp channel 里没有生产级的 click-to-chat URL 生成链路。此前检查到的 `wa.me` 命中只出现在 QR 终端渲染测试样本中，不是让终端用户点击进入会话的业务路径。

实际链路如下：

```text
用户 WhatsApp App
  -> 给已绑定的助手 WhatsApp 号码发消息
  -> WhatsApp Web / Baileys socket
  -> OpenClaw WhatsApp channel
  -> Gateway 入站监听
  -> policy / pairing / allowFrom 权限检查
  -> resolveAgentRoute
  -> channel turn kernel / agent
  -> deliverWebReply
  -> 同一个 WhatsApp chat 收到回复
```

关键点：

- OpenClaw 先把一个 WhatsApp 账号通过 WhatsApp Web QR 绑定到本地 Gateway。
- 用户侧动作是给这个已绑定的“助手号码”发消息。
- OpenClaw 侧动作是启动 Gateway、保持 WhatsApp Web socket、监听 `messages.upsert`、清洗入站消息、执行权限策略、路由 agent、再通过同一 socket 回复。
- QR 只是账号登录/授权手段，不是终端用户每次发起对话的入口。
- `wa.me` 或平台 click-to-chat URL 即使可以作为用户便利入口，也不是 OpenClaw channel 的核心运行机制。

## 通用聊天 Channel 模型

多数聊天 App 接入 OpenClaw 时，可以抽象为以下模型：

```text
External Chat App
  -> bot / account / phone number / service account
  -> token / OAuth / QR / app secret / CLI daemon / webhook
  -> OpenClaw Gateway channel runtime
  -> inbound normalize
  -> access control
  -> route to agent/session
  -> process turn
  -> send reply through same channel identity
```

这个模型有几个稳定边界：

- **平台身份**：OpenClaw 需要一个能代表 agent 的外部身份，例如 bot token、应用、服务账号、手机号、用户账号或设备。
- **授权材料**：OpenClaw 需要保存或引用 token、secret、OAuth 凭据、QR 登录凭据、service account key、CLI 配置目录等。
- **入站事件**：平台把用户消息送进 Gateway，方式可能是 polling、WebSocket、官方 gateway、HTTP webhook、SSE、外部 CLI 或本地数据库监听。
- **权限策略**：OpenClaw 不应默认让所有陌生人直接进入 agent，通常需要 `pairing`、`allowlist`、`allowFrom`、群策略、mention gate 或显式 `open`。
- **路由策略**：入站消息需要映射到 agent、session、conversation、peer、group/thread 等 OpenClaw 内部标识。
- **回复通道**：回复必须通过同一外部身份发回原 chat、DM、thread、group 或 space。

## 各类 App 的差异

### Bot token 型

代表平台：Telegram、Discord、ClickClack、部分 Mattermost/Matrix/IRC 类集成。

典型流程：

1. 在平台开发者后台或 bot 管理工具里创建 bot。
2. 拿到 bot token。
3. 在 OpenClaw config/env 中配置 token。
4. 启动 Gateway。
5. 用户 DM bot，或在群里 @mention bot。
6. OpenClaw 按 policy 放行并回复。

特点：

- 绑定过程通常不需要扫描二维码。
- 平台身份是 bot，不是个人账号。
- 用户“拉起对话”的方式通常是搜索 bot、打开 DM、把 bot 加入群或频道。
- 有些平台需要开启 message content、members、group privacy、slash command 等额外权限。

### App + WebSocket 型

代表平台：Slack Socket Mode、飞书/Lark WebSocket、Discord Gateway。

典型流程：

1. 创建平台 App。
2. 配置 bot、权限、事件订阅和交互能力。
3. 配置 token、app token、app id/secret。
4. Gateway 主动建立 outbound WebSocket。
5. 平台通过 WebSocket 推送消息事件。
6. OpenClaw 处理后调用平台 API 回复。

特点：

- 不要求公网 HTTPS webhook，适合本机、内网或开发环境。
- 需要 outbound 网络能访问平台 WebSocket endpoint。
- 多实例部署时要注意平台对 socket session、app token 或 event delivery 的限制。

### HTTP webhook 型

代表平台：LINE、Google Chat、Slack HTTP Request URLs、飞书 webhook 模式、部分 Telegram webhook。

典型流程：

1. 创建平台 App 或 bot。
2. 配置 webhook URL，例如 `https://gateway-host/line/webhook` 或 `https://gateway-host/googlechat`。
3. 在 OpenClaw 配置 token、secret、service account、audience、verification token 等。
4. Gateway 暴露公开 HTTPS endpoint。
5. 平台向 Gateway POST 事件。
6. Gateway 验签、解析、异步处理并回复。

特点：

- 通常需要公网 HTTPS、反向代理或 tunnel。
- 安全重点是签名校验、body size 限制、raw body 校验、重放保护和路径隔离。
- 适合多副本或服务端部署，但开发环境成本高于 Socket Mode。

### QR / 设备绑定型

代表平台：WhatsApp Web、Signal linked device。

典型流程：

1. 准备一个专用助手手机号或账号。
2. 在 OpenClaw CLI/UI 中触发登录。
3. 平台 App 扫 QR 或完成设备绑定。
4. OpenClaw 保存本地凭据。
5. Gateway 以已绑定设备身份收发消息。
6. 用户给该手机号/账号发消息进入 OpenClaw。

特点：

- 绑定对象通常更像“一个登录设备”，不是开发者后台里的 bot。
- 建议使用独立 bot 号码/账号，避免个人账号自发消息被 loop protection 忽略。
- 凭据目录和设备状态需要长期保存。
- 断线重连、凭据失效、扫码过期是主要运维问题。

### 外部 CLI / 本地客户端型

代表平台：iMessage via `imsg`、Signal via `signal-cli`、IRC 客户端封装。

典型流程：

1. 在宿主机安装平台 CLI 或本地客户端。
2. 通过账号、手机号、本机登录态或平台数据库获得访问能力。
3. OpenClaw Gateway 启动或连接该 CLI。
4. CLI 向 Gateway 提供消息流或 RPC。
5. Gateway 把消息转成 OpenClaw 入站事件并回复。

特点：

- 强依赖宿主环境，例如 macOS Messages、Java、Docker container、账号登录态。
- Gateway 不一定直接连接平台官方 API。
- 运维排障要同时看 OpenClaw、CLI、本地账号状态和平台客户端状态。

## Channel 拉起不是 Deep Link

聊天 channel 的“拉起”通常不是打开 OpenClaw UI，而是让外部平台消息进入 OpenClaw 的 agent turn。

这与 deep link 有本质差异：

| 目标 | 典型入口 | OpenClaw 需要做的事 |
| --- | --- | --- |
| 在聊天 App 中对话 | DM bot、@mention、给号码发消息、加入群聊 | 接收入站消息、鉴权、路由、回复 |
| 打开 OpenClaw/GuLiCode UI | `openclaw://...`、HTTPS link、桌面 IPC、PWA route | 建立 UI session、加载 run/chat/workbench |
| 从业务系统创建任务 | HTTP API、Collaboration Server API、MCP/RPC | 创建 run、写入消息、绑定用户身份和权限 |
| 分享某个 agent 入口 | 平台 invite URL、bot profile、群邀请、二维码 | 帮用户找到外部 bot/账号，真正对话仍走入站监听 |

所以，如果需求是“从其他业务 App 一键打开 GuLiCode 某个会话”，应设计 GuLiCode/Collaboration Server 的 deep link 或 API，而不是复用 WhatsApp channel 的 QR 登录机制。

## 面向 GuLiCode / multi_agent_tcp 的设计启发

当前 `multi_agent_tcp` 的产品中心是：

```text
GuLiCode desktop / UI / top Agent
  -> blueprint entry and workbench surfaces
  -> GraphRuntimeControlPlane
  -> GraphRuntime
  -> AgentNode queues / outgoing batches / joins / workspace state / events
  -> CLIWorkerBackend
```

如果未来要把外部 App 接入 GuLiCode 或 multi-agent runtime，建议保留两层边界：

1. **外部 channel adapter 层**
   - 只负责平台认证、入站事件、出站回复、媒体下载上传、平台特定 metadata。
   - 不直接实现 GraphRuntime 调度。
   - 不直接改项目代码或共享 workspace。

2. **GuLiCode Collaboration Server / runtime bridge 层**
   - 负责用户身份、权限、run/session 映射、审计、事件投影。
   - 通过 `DesktopBlueprintService` / `GraphRuntimeControlPlane` 调用 runtime。
   - 对移动端、Web、外部 App 暴露稳定 API。

推荐抽象：

```text
External Platform Adapter
  -> InboundMessage(channel, account, peer, sender, text, attachments, thread)
  -> Collaboration Server / Gateway boundary
  -> RuntimeBridge.queue_message(...)
  -> GraphRuntimeControlPlane
  -> AgentNode / Top Agent / Blueprint run
  -> OutboundReply(channel, account, peer, thread, content)
  -> External Platform Adapter
```

这样可以避免把 Telegram/Slack/WhatsApp 这类平台细节泄漏到 GraphRuntime，也避免让外部用户直接获得 runtime token、workspace RPC token、private checkout path 或本地 Codex 环境。

## 权限与安全原则

外部 App 接入时，默认应采用保守策略：

- DM 默认 `pairing` 或 `allowlist`，不要默认 public open。
- 群聊默认 require mention，且 group allowlist 单独配置。
- bot-authored message 默认过滤，只有明确支持 `allowBots` 时才进入 loop protection。
- webhook path 只暴露平台需要的 endpoint，不暴露 dashboard、runtime RPC、workspace RPC。
- webhook 必须做签名校验、raw body 校验、大小限制和超时限制。
- token、secret、OAuth refresh token、service account key 不进入前端 payload。
- 外部 sender id、display name、群 id、thread id 只能作为授权和路由事实，不应当作可信用户资料。
- 多账号场景中，account id 必须参与路由 key，避免不同 bot/号码互相串线。

## 实现检查清单

新增一个外部聊天 App channel 时，至少要回答这些问题：

- 平台身份是什么：bot、应用、服务账号、手机号、个人账号、设备，还是本地 CLI？
- 授权方式是什么：token、secret、OAuth、QR、service account、captcha/SMS、宿主登录态？
- 入站传输是什么：polling、WebSocket、HTTP webhook、SSE、本地数据库、CLI RPC？
- 出站回复如何发：reply token、chat id、thread id、channel id、room id、phone number？
- DM 和群聊如何区分？
- sender id、group id、thread id 的稳定格式是什么？
- 默认权限策略是什么？
- 未知用户如何 pairing？
- group mention gate 如何做？
- bot 自发消息和其他 bot 消息如何过滤？
- 附件、图片、语音、文件、位置等媒体如何下载和回传？
- 多账号配置如何表示？
- 凭据保存在哪里？如何轮换、撤销、重登？
- Gateway 断线重连、webhook 重试、消息去重如何处理？
- 路由到哪个 agent/session/run？session key 如何稳定生成？
- 失败时用户收到什么提示？日志中如何排障？

## 排障思路

如果“用户在外部 App 发了消息但 OpenClaw 没反应”，按层排查：

1. **平台层**：bot 是否存在、是否在线、是否加入群、是否被用户拉黑、是否有消息权限。
2. **授权层**：token/secret/OAuth/QR 凭据是否有效，账号是否掉线。
3. **传输层**：WebSocket 是否连接，webhook URL 是否可公网访问，签名是否通过，polling 是否在跑。
4. **入站层**：Gateway 是否收到事件，是否被过滤为自发消息、空消息、status/broadcast 或 bot loop。
5. **权限层**：`dmPolicy`、`allowFrom`、pairing、group allowlist、require mention 是否拦截。
6. **路由层**：是否解析出正确 `conversationId`、`peerId`、agent id 和 session key。
7. **runtime 层**：agent turn 是否执行，GraphRuntime/turn kernel 是否报错。
8. **出站层**：回复 API 是否失败，reply token 是否过期，目标 thread/chat 是否可写。

这个排障顺序适用于 WhatsApp，也适用于大多数 Telegram、Slack、Discord、飞书、LINE、Google Chat、Signal、iMessage 等 channel。

## 设计结论

其他聊天 App 接入 OpenClaw 时，方法论确实类似：先让 OpenClaw 拥有或连接一个外部平台身份，再让 Gateway 监听该身份的入站消息，最后把消息路由到 agent 并从同一平台身份回复。

但“类似”只在架构层成立：

- WhatsApp / Signal 更像账号或设备绑定。
- Telegram / Discord 更像 bot token。
- Slack / 飞书可能是 WebSocket app。
- LINE / Google Chat 更像 webhook app。
- iMessage 更像本地宿主 CLI。

如果需求是让外部业务 App 直接打开 OpenClaw/GuLiCode，则应另行设计 deep link、Collaboration Server API 或 desktop IPC，而不是套用聊天 channel 的账号绑定机制。
