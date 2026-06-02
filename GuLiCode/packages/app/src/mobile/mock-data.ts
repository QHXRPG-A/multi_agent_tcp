import type {
  BlueprintAgentPanel,
  BlueprintAgentPanelEvent,
  BlueprintNodeState,
  MobileMockData,
} from "./mobile-state"

function stateLabel(state: BlueprintNodeState) {
  switch (state) {
    case "done":
      return "已完成"
    case "running":
      return "运行中"
    case "queued":
      return "排队中"
    case "idle":
      return "空闲"
    case "failed":
      return "失败"
  }
}

function makeAgentPanel(input: {
  id: string
  label: string
  state: BlueprintNodeState
  role: string
  taskStatus: string
  queueSize: number
  messagesSent: number
  busyCount: number
  updatedAt: string
  events: BlueprintAgentPanelEvent[]
  agentId?: string
  cliKind?: string
}): BlueprintAgentPanel {
  const agentId = input.agentId ?? input.label
  const cliKind = input.cliKind ?? "codex"

  return {
    agentId,
    cliKind,
    taskStatus: input.taskStatus,
    queueSize: input.queueSize,
    messagesSent: input.messagesSent,
    busyCount: input.busyCount,
    updatedAt: input.updatedAt,
    statusDetails: [
      { label: "nodeId", value: input.id },
      { label: "agentId", value: agentId },
      { label: "cliKind", value: cliKind },
      { label: "state", value: stateLabel(input.state) },
      { label: "role", value: input.role },
      { label: "updatedAt", value: input.updatedAt },
    ],
    events: input.events,
    inputPlaceholder: "等待 live runtime",
    disabledNotice: "纯前端 mock：消息发送未接入 runtime。",
  }
}

export const mobileMockData: MobileMockData = {
  messages: [
    {
      id: "msg-user-goal",
      speaker: "user",
      label: "你",
      body: "请让 Top Agent 先看当前蓝图运行情况，整理节点状态和这轮 diff，但暂时不要从手机端改蓝图。",
      time: "09:40",
    },
    {
      id: "msg-top-plan",
      speaker: "top-agent",
      label: "Top Agent",
      body: "收到。我会只读取当前运行态：先确认蓝图结构，再汇总正在执行的 Agent，最后把变更文件整理成移动端可读摘要。",
      time: "09:41",
      segments: [
        {
          id: "desktop-plan-text",
          type: "text",
          body: "收到。我会只读取当前运行态，并同步桌面端当前会话。",
        },
        {
          id: "desktop-plan-reasoning",
          type: "reasoning",
          title: "思考过程",
          status: "completed",
          body: "先确认桌面会话和 composer 模式，再检查蓝图全图结构与运行态。",
        },
        {
          id: "desktop-plan-tool",
          type: "tool",
          title: "工具调用",
          toolName: "blueprint.snapshot",
          status: "completed",
          body: "{\"nodes\":9,\"edges\":9,\"mode\":\"blueprintPlanning\"}",
        },
      ],
    },
    {
      id: "msg-top-status",
      speaker: "top-agent",
      label: "Top Agent",
      body: "当前 Coder 节点运行中，Planner 已完成，Review 还在排队。Diff 已收敛到 5 个文件，没有发现需要手机端确认的阻塞项。",
      time: "09:46",
    },
    {
      id: "msg-user-next",
      speaker: "user",
      label: "你",
      body: "先保持只读。等桌面端蓝图确认后，再考虑移动端是否需要审批入口。",
      time: "09:47",
    },
    {
      id: "msg-top-next",
      speaker: "top-agent",
      label: "Top Agent",
      body: "已记录：移动端第一版只展示对话、蓝图概览、运行情况和 diff，不提供消息传递、运行控制或蓝图编辑。",
      time: "09:48",
    },
  ],
  blueprint: {
    title: "GuLiCode 蓝图运行",
    description: "只读查看当前 Top Agent 编排，不在移动端编辑或触发运行。",
    nodes: [
      {
        id: "start",
        label: "Start",
        kind: "worker_agent",
        state: "done",
        role: "入口",
        detail: "接收 Top Agent 的编排目标，锁定本轮只读查看范围。",
        note: "移动端只显示运行快照，不提供启动或重跑入口。",
        agentPanel: makeAgentPanel({
          id: "start",
          label: "Start",
          state: "done",
          role: "入口",
          taskStatus: "succeeded",
          queueSize: 0,
          messagesSent: 1,
          busyCount: 0,
          updatedAt: "09:42",
          events: [
            {
              id: "start-user-goal",
              title: "用户目标",
              tone: "user",
              status: "completed",
              text: "请只读取当前蓝图运行态，不要从移动端修改蓝图。",
              time: "09:40",
            },
            {
              id: "start-scope-lock",
              title: "范围锁定",
              tone: "tool",
              status: "completed",
              detail: "workspace.readonly=true",
              text: "已锁定移动端只读范围，后续节点只展示运行快照。",
              time: "09:42",
            },
          ],
        }),
      },
      {
        id: "top-agent",
        label: "Top Agent",
        kind: "worker_agent",
        state: "done",
        role: "总控",
        detail: "拆分蓝图状态、运行节点和 Diff 摘要，保持桌面端为唯一编辑入口。",
        note: "已确认本轮移动端不发送消息、不审批、不改蓝图。",
        agentPanel: makeAgentPanel({
          id: "top-agent",
          label: "Top Agent",
          state: "done",
          role: "总控",
          taskStatus: "succeeded",
          queueSize: 0,
          messagesSent: 4,
          busyCount: 0,
          updatedAt: "09:46",
          events: [
            {
              id: "top-agent-reasoning",
              title: "Agent 思考",
              tone: "reasoning",
              status: "completed",
              text: "先确认蓝图结构，再汇总正在执行的 Agent，最后整理移动端可读 diff。",
              time: "09:41",
            },
            {
              id: "top-agent-reply",
              title: "Agent 回复",
              tone: "reply",
              status: "completed",
              text: "当前 Coder 节点运行中，Planner 已完成，Review 还在排队。",
              time: "09:46",
            },
          ],
        }),
      },
      {
        id: "planner",
        label: "Planner",
        kind: "worker_agent",
        state: "done",
        role: "规划",
        detail: "整理节点执行顺序，并把 Review 与 Summary 留在后续队列。",
        note: "计划已同步给 Coder，等待当前实现节点完成。",
        agentPanel: makeAgentPanel({
          id: "planner",
          label: "Planner",
          state: "done",
          role: "规划",
          taskStatus: "succeeded",
          queueSize: 0,
          messagesSent: 2,
          busyCount: 0,
          updatedAt: "09:44",
          events: [
            {
              id: "planner-tool-plan",
              title: "工具调用 · blueprint.plan",
              tone: "tool",
              status: "completed",
              detail: "Review 与 Summary 保持 queued",
              text: "生成只读移动端展示顺序：Start -> Top Agent -> Planner -> Coder -> Review -> Summary。",
              time: "09:43",
            },
            {
              id: "planner-reply",
              title: "Agent 回复",
              tone: "reply",
              status: "completed",
              text: "规划完成，当前实现任务交给 Coder，后续检查和汇总保持等待。",
              time: "09:44",
            },
          ],
        }),
      },
      {
        id: "coder",
        label: "Coder",
        kind: "agent",
        state: "running",
        role: "实现",
        detail: "正在重做移动端 mock 的展示结构，并收敛点击反馈。",
        note: "当前进度来自 mock 数据，实际运行仍以桌面端蓝图为准。",
        agentPanel: makeAgentPanel({
          id: "coder",
          label: "Coder",
          state: "running",
          role: "实现",
          taskStatus: "running",
          queueSize: 1,
          messagesSent: 7,
          busyCount: 1,
          updatedAt: "09:48",
          events: [
            {
              id: "coder-reasoning",
              title: "Agent 思考",
              tone: "reasoning",
              status: "streaming",
              text: "把列表详情改成移动端底部弹卡，同时保留 Diff accordion 和只读限制。",
              time: "09:47",
            },
            {
              id: "coder-tool",
              title: "工具调用 · edit",
              tone: "tool",
              status: "running",
              detail: "packages/app/src/mobile/mobile-app.tsx",
              text: "正在替换结构总览节点点击行为，并新增 AgentInfoSheet mock 面板。",
              time: "09:48",
            },
            {
              id: "coder-event",
              title: "运行事件",
              tone: "event",
              status: "running",
              text: "当前为前端 mock 展示，不会触发真实 runtime 调用。",
              time: "09:48",
            },
          ],
        }),
      },
      {
        id: "script-format",
        label: "Format Result",
        kind: "script",
        state: "idle",
        role: "Script Function",
        detail: "输入 1 / 输出 1，格式化 Coder 的结构化结果供后续节点读取。",
        note: "脚本来自桌面端蓝图快照，移动端只展示函数签名。",
        summary: "format_result(payload: dict) -> {summary: str}",
        inputPorts: ["payload: dict"],
        outputPorts: ["summary: str"],
        agentPanel: makeAgentPanel({
          id: "script-format",
          label: "Format Result",
          state: "idle",
          role: "Script Function",
          taskStatus: "idle",
          queueSize: 0,
          messagesSent: 0,
          busyCount: 0,
          updatedAt: "09:48",
          events: [
            {
              id: "script-format-idle",
              title: "脚本节点",
              tone: "event",
              status: "idle",
              text: "等待 Coder 输出后由框架执行，移动端不直接运行脚本。",
              time: "09:48",
            },
          ],
        }),
      },
      {
        id: "branch-review",
        label: "Branch",
        kind: "branch",
        state: "idle",
        role: "Common Node",
        detail: "输入 1 / 输出 2，根据条件路由到 Review 或 Summary。",
        note: "框架内置节点，移动端只展示路由关系。",
        summary: "condition: bool -> true/false",
        inputPorts: ["condition: bool"],
        outputPorts: ["true: message", "false: message"],
        agentPanel: makeAgentPanel({
          id: "branch-review",
          label: "Branch",
          state: "idle",
          role: "Common Node",
          taskStatus: "idle",
          queueSize: 0,
          messagesSent: 0,
          busyCount: 0,
          updatedAt: "09:48",
          events: [
            {
              id: "branch-idle",
              title: "Branch 节点",
              tone: "event",
              status: "idle",
              text: "等待 bool 条件，true 进入 Review，false 进入 Summary。",
              time: "09:48",
            },
          ],
        }),
      },
      {
        id: "tick-refresh",
        label: "Tick",
        kind: "tick",
        state: "idle",
        role: "Common Node",
        detail: "输入 0 / 输出 1，每 3 秒触发一次移动端可见刷新提示。",
        note: "Tick 由桌面端运行时调度，移动端不修改频率。",
        summary: "every_n_seconds = 3",
        outputPorts: ["tick: tick"],
        everyNSeconds: 3,
        agentPanel: makeAgentPanel({
          id: "tick-refresh",
          label: "Tick",
          state: "idle",
          role: "Common Node",
          taskStatus: "idle",
          queueSize: 0,
          messagesSent: 0,
          busyCount: 0,
          updatedAt: "09:48",
          events: [
            {
              id: "tick-idle",
              title: "Tick 节点",
              tone: "event",
              status: "idle",
              text: "按桌面端蓝图配置周期触发，移动端只展示节拍配置。",
              time: "09:48",
            },
          ],
        }),
      },
      {
        id: "review",
        label: "Review",
        kind: "worker_agent",
        state: "queued",
        role: "检查",
        detail: "等待 Coder 结束后检查视觉、交互和移动端溢出。",
        note: "队列中，移动端暂不提供人工审批按钮。",
        agentPanel: makeAgentPanel({
          id: "review",
          label: "Review",
          state: "queued",
          role: "检查",
          taskStatus: "queued",
          queueSize: 1,
          messagesSent: 0,
          busyCount: 0,
          updatedAt: "09:48",
          events: [
            {
              id: "review-queued",
              title: "队列状态",
              tone: "event",
              status: "queued",
              text: "等待 Coder 节点完成后检查视觉、交互、测试和移动端溢出。",
              time: "09:48",
            },
          ],
        }),
      },
      {
        id: "summary",
        label: "Summary",
        kind: "worker_agent",
        state: "queued",
        role: "汇总",
        detail: "最终把节点状态、变更文件和只读限制汇总成移动端摘要。",
        note: "当前还没有最终报告，先展示预留状态。",
        agentPanel: makeAgentPanel({
          id: "summary",
          label: "Summary",
          state: "queued",
          role: "汇总",
          taskStatus: "not_started",
          queueSize: 1,
          messagesSent: 0,
          busyCount: 0,
          updatedAt: "09:48",
          events: [
            {
              id: "summary-queued",
              title: "队列状态",
              tone: "event",
              status: "queued",
              text: "当前还没有最终报告，等待 Review 后生成移动端摘要。",
              time: "09:48",
            },
          ],
        }),
      },
    ],
    edges: [
      { source: "start", target: "top-agent", kind: "exec" },
      { source: "top-agent", target: "planner", kind: "exec" },
      { source: "planner", target: "coder", kind: "exec" },
      { source: "coder", target: "script-format", kind: "data", outputPort: "out", inputPort: "payload" },
      { source: "script-format", target: "branch-review", kind: "data", outputPort: "summary", inputPort: "condition" },
      { source: "branch-review", target: "review", kind: "exec", outputPort: "true", inputPort: "in" },
      { source: "branch-review", target: "summary", kind: "exec", outputPort: "false", inputPort: "in" },
      { source: "tick-refresh", target: "top-agent", kind: "data", outputPort: "tick", inputPort: "in" },
      { source: "review", target: "summary", kind: "exec" },
    ],
    run: {
      label: "运行中",
      progress: 68,
      currentNode: "Coder",
      updatedAt: "09:48",
      agents: [
        { name: "Top Agent", state: "done" },
        { name: "Planner", state: "done" },
        { name: "Coder", state: "running" },
        { name: "Review", state: "queued" },
      ],
    },
    diff: {
      fileCount: 5,
      additions: 128,
      deletions: 34,
      files: [
        {
          path: "packages/app/src/mobile/mobile-app.tsx",
          summary: "重做移动端 mock 信息架构",
          additions: 72,
          deletions: 18,
          previewLines: [
            { type: "delete", text: "- active tab 使用黑色实底" },
            { type: "add", text: "+ active tab 使用奶白底和柔和玫瑰边框" },
            { type: "add", text: "+ 节点和 Diff 支持就地展开详情" },
            { type: "context", text: "  mock 仍保持只读，不调用 runtime API" },
          ],
        },
        {
          path: "packages/app/src/mobile/mobile-state.ts",
          summary: "替换为只读展示数据模型",
          additions: 24,
          deletions: 9,
          previewLines: [
            { type: "add", text: "+ BlueprintNode 增加 role/detail/note 展示字段" },
            { type: "add", text: "+ BlueprintDiffFile 增加 previewLines" },
            { type: "context", text: "  类型仍只服务移动端 mock 数据" },
          ],
        },
        {
          path: "packages/app/e2e/mobile.spec.ts",
          summary: "更新顶部标签和只读页面断言",
          additions: 18,
          deletions: 4,
          previewLines: [
            { type: "add", text: "+ 断言 active tab 不再是黑色" },
            { type: "add", text: "+ 断言节点详情和 Diff 详情可展开" },
            { type: "delete", text: "- 移除旧的独立箭头展示断言" },
          ],
        },
      ],
    },
  },
  server: {
    clients: { mobile: true, desktop: true },
    syncReady: true,
    capabilities: [],
    planningRequests: [
      {
        id: "planning-mobile-sync",
        projectId: "mock-project",
        blueprintId: "mock-blueprint",
        goal: "补全移动端桌面镜像同步",
        status: "waiting_for_answer",
        desktopSessionId: "desktop-main",
        planningSessionId: "plan-mobile-sync",
        pendingQuestion: {
          questionId: "scope",
          questions: [
            {
              id: "scope",
              question: "移动端是否保持只读镜像，不提供蓝图编辑入口？",
            },
          ],
        },
        createdAt: "2026-05-31T09:40:00+08:00",
        updatedAt: "2026-05-31T09:48:00+08:00",
      },
      {
        id: "planning-mobile-plan",
        projectId: "mock-project",
        blueprintId: "mock-blueprint",
        goal: "同步桌面 Blueprint 全图节点",
        status: "waiting_for_approval",
        desktopSessionId: "desktop-main",
        planningSessionId: "plan-mobile-graph",
        pendingPlan: {
          plan: {
            steps: ["同步 Agent / Script / Branch / Tick", "保留桌面边和端口", "移动端只读展示"],
          },
        },
        createdAt: "2026-05-31T09:42:00+08:00",
        updatedAt: "2026-05-31T09:49:00+08:00",
      },
    ],
    desktopSessions: {
      online: true,
      loggedIn: true,
      stale: false,
      updatedAt: "2026-05-31T09:50:00+08:00",
      activeSessionId: "desktop-main",
      sessions: [
        {
          id: "desktop-main",
          title: "移动端镜像同步",
          messageCount: 5,
          updatedAt: "2026-05-31T09:50:00+08:00",
        },
        {
          id: "desktop-archive",
          title: "归档检查",
          messageCount: 2,
          updatedAt: "2026-05-31T09:30:00+08:00",
        },
      ],
      currentMessages: [],
      composer: {
        activeModeId: "mode-blueprint",
        modes: [
          { id: "mode-agent", label: "Top Agent", kind: "agent" },
          { id: "mode-blueprint", label: "Blueprint Planning", kind: "blueprintPlanning" },
        ],
      },
    },
  },
}
