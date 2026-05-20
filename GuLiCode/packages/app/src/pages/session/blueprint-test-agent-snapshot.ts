import type { BlueprintAgentNode } from "./blueprint-model"

type RecordLike = Record<string, unknown>

export type TestAgentUserMessageLike = {
  id?: string
  runId?: string
  runtimeMessageId?: string
  nodeId?: string
  mode?: "default" | "top" | string
  text?: string
  status?: string
  runtimeStatus?: string
  created_at?: string
  sent_at?: string
  completed_at?: string
  failed_at?: string
  error?: string
}

export type TestAgentStreamEventLike = RecordLike & {
  seq?: number
  kind?: string
  node_id?: string
  agent_id?: string
  message_id?: string
  delta?: string
  text?: string
  status?: string
  created_at?: string | number
}

export type TestAgentPanelLike = {
  nodeId: string
  info?: RecordLike
  userMessages?: TestAgentUserMessageLike[]
  testJsonPath?: string
  testJsonError?: string
}

export type TestAgentPanelSnapshotInput = {
  node: BlueprintAgentNode
  panel: TestAgentPanelLike
  events: TestAgentStreamEventLike[]
  runId?: string
  jsonPath?: string
  now?: () => Date
}

const FRAMEWORK_ACTIONS: Record<string, string> = {
  "agent.dispatch": "发送给其它 Agent",
  "workspace checkout": "检出工作区",
  "workspace status": "查看工作区状态",
  "workspace diff": "查看改动差异",
  "workspace submit": "提交改动",
  "workspace sync": "同步工作区",
  "workspace publish": "发布产物",
  "workspace publish-file": "发布产物",
  "join.contribute": "提交汇聚结果",
  "changeset.submit": "提交改动",
  "artifact.publish": "发布产物",
  "report.submit": "提交报告",
}

export function createTestAgentPanelSnapshot(input: TestAgentPanelSnapshotInput): Record<string, unknown> {
  const updatedAt = (input.now?.() ?? new Date()).toISOString()
  const nodeId = input.node.node_id
  const agentId = input.node.agent_id ?? nodeId
  const messageJournal = arrayOfRecords(input.panel.info?.messageJournal)
  const frameworkApiCalls = arrayOfRecords(input.panel.info?.frameworkApiCalls)
  const userMessages = normalizeUserMessages(input.panel.userMessages ?? [], nodeId)
  const agentReplies = createAgentReplies({
    nodeId,
    agentId,
    events: input.events,
    userMessages: input.panel.userMessages ?? [],
    messageJournal,
  })
  const frameworkMessages = createFrameworkMessages({
    nodeId,
    agentId,
    frameworkApiCalls,
    messageJournal,
  })

  return plainJsonRecord({
    schema_version: 2,
    kind: "gulicode.blueprint.test_agent_messages",
    updated_at: updatedAt,
    runId: input.runId,
    nodeId,
    agentId,
    jsonPath: input.jsonPath,
    agentReplies,
    userMessages,
    frameworkMessages,
  })
}

function normalizeUserMessages(messages: TestAgentUserMessageLike[], nodeId: string) {
  return messages
    .map((message, index) =>
      compactRecord({
        id: stringValue(message.id) ?? `user-${index + 1}`,
        time: message.created_at ?? message.sent_at ?? message.completed_at ?? message.failed_at,
        from: "用户",
        to: stringValue(message.nodeId) ?? nodeId,
        status: message.status,
        text: message.text,
        messageId: message.runtimeMessageId,
        mode: message.mode,
        runtimeStatus: message.runtimeStatus,
        runId: message.runId,
        createdAt: message.created_at,
        sentAt: message.sent_at,
        completedAt: message.completed_at,
        failedAt: message.failed_at,
        error: message.error,
      }),
    )
    .filter((message) => Boolean(message.text || message.summary || message.messageId))
}

function createAgentReplies(input: {
  nodeId: string
  agentId: string
  events: TestAgentStreamEventLike[]
  userMessages: TestAgentUserMessageLike[]
  messageJournal: RecordLike[]
}) {
  const userRuntimeMessageIds = new Set(
    input.userMessages.map((message) => stringValue(message.runtimeMessageId)).filter(Boolean) as string[],
  )
  const replies = new Map<string, RecordLike>()

  for (const event of input.events) {
    const messageId = stringValue(event.message_id)
    if (!messageId) continue
    const text = messageText(event)
    if (!text) continue
    const toUser = userRuntimeMessageIds.has(messageId)
    upsertReply(replies, {
      id: stringValue(event.event_id) ?? stringValue(event.part_id) ?? `reply-${messageId}`,
      time: normalizeTime(event.created_at),
      from: input.nodeId,
      to: toUser ? "用户" : "框架",
      status: stringValue(event.status) ?? "completed",
      text,
      messageId,
      replyType: toUser ? "to_user" : "to_framework",
    })
  }

  for (const record of input.messageJournal) {
    const recordType = stringValue(record.recordType) ?? stringValue(record.record_type)
    if (recordType !== "agent.outgoing.staged" && recordType !== "agent.outgoing.no_op") continue
    const sender = asRecord(record.sender)
    if (stringValue(sender?.node_id) !== input.nodeId && stringValue(record.from) !== input.nodeId) continue
    const metadata = asRecord(record.metadata)
    const targetNodeId = stringValue(record.targetNodeId) ?? stringValue(metadata?.target_node_id)
    const text = messageText(record) ?? stringValue(record.summary)
    upsertReply(replies, {
      id: stringValue(record.id) ?? stringValue(record.record_id) ?? `reply-${record.batchId ?? replies.size + 1}`,
      time: normalizeTime(record.time ?? record.recorded_at),
      from: input.nodeId,
      to: targetNodeId ?? stringValue(record.to) ?? endpointLabel(record.receiver, "其它 Agent"),
      status: stringValue(record.status) ?? "staged",
      text,
      summary: text ? undefined : noOpSummary(record),
      messageId: stringValue(record.messageId) ?? stringValue(record.message_id),
      batchId: stringValue(record.batchId) ?? stringValue(record.batch_id),
      replyType: "to_agent",
    })
  }

  return [...replies.values()]
}

function createFrameworkMessages(input: {
  nodeId: string
  agentId: string
  frameworkApiCalls: RecordLike[]
  messageJournal: RecordLike[]
}) {
  const calls = input.frameworkApiCalls.length ? input.frameworkApiCalls : frameworkCallsFromJournal(input.messageJournal, input.nodeId)
  return calls
    .map((call, index) => {
      const action = frameworkActionLabel(call)
      const summary = stringValue(call.summary) ?? messageText(call)
      return compactRecord({
        id: stringValue(call.id) ?? stringValue(call.record_id) ?? `framework-${index + 1}`,
        time: normalizeTime(call.time ?? call.recorded_at),
        from: endpointLabel(call.from ?? call.sender, input.nodeId),
        to: "框架",
        status: call.status,
        action,
        summary,
        messageId: stringValue(call.messageId) ?? stringValue(call.message_id),
        batchId: stringValue(call.batchId) ?? stringValue(call.batch_id),
      })
    })
    .filter((message) => Boolean(message.action || message.summary || message.messageId || message.batchId))
}

function frameworkCallsFromJournal(records: RecordLike[], nodeId: string) {
  return records.filter((record) => {
    const recordType = stringValue(record.recordType) ?? stringValue(record.record_type)
    const sender = asRecord(record.sender)
    return (
      (recordType === "agent.outgoing.staged" || recordType === "agent.outgoing.no_op") &&
      (stringValue(sender?.node_id) === nodeId || stringValue(record.from) === nodeId)
    )
  })
}

function frameworkActionLabel(call: RecordLike) {
  const api = stringValue(call.api) ?? stringValue(call.interface) ?? stringValue(call.recordType) ?? stringValue(call.record_type)
  const command = stringValue(call.command)
  const normalized =
    api === "workspace" && command
      ? `workspace ${command}`
      : api === "workspace_api" && command
        ? `workspace ${command}`
        : api === "agent.outgoing.staged" || api === "agent.outgoing.no_op"
          ? "agent.dispatch"
          : api
  return (normalized && FRAMEWORK_ACTIONS[normalized]) || "调用框架接口"
}

function upsertReply(replies: Map<string, RecordLike>, next: RecordLike) {
  const key = `${next.replyType ?? "reply"}:${next.messageId ?? next.batchId ?? next.id}`
  const current = replies.get(key)
  if (!current) {
    replies.set(key, compactRecord(next))
    return
  }
  const currentText = stringValue(current.text)
  const nextText = stringValue(next.text)
  const nextCompleted = next.status === "completed" || next.status === "succeeded"
  const currentCompleted = current.status === "completed" || current.status === "succeeded"
  if ((nextCompleted && !currentCompleted) || (nextText?.length ?? 0) >= (currentText?.length ?? 0)) {
    replies.set(key, compactRecord({ ...current, ...next }))
  }
}

function messageText(record: RecordLike) {
  const direct = stringValue(record.text) ?? stringValue(record.delta)
  if (direct) return direct
  const payload = asRecord(record.payload)
  const payloadText = stringValue(payload?.text) ?? stringValue(payload?.prompt) ?? stringValue(payload?.message)
  if (payloadText) return payloadText
  const body = asRecord(payload?.body)
  return stringValue(body?.text) ?? stringValue(body?.prompt) ?? stringValue(body?.message)
}

function noOpSummary(record: RecordLike) {
  const recordType = stringValue(record.recordType) ?? stringValue(record.record_type)
  return recordType === "agent.outgoing.no_op" ? "无下游消息" : undefined
}

function endpointLabel(value: unknown, fallback: string) {
  if (typeof value === "string" && value.trim()) return value.trim()
  const record = asRecord(value)
  return (
    stringValue(record?.node_id) ??
    stringValue(record?.agent_id) ??
    stringValue(record?.type) ??
    fallback
  )
}

function normalizeTime(value: unknown) {
  if (typeof value === "string" && value.trim()) return value.trim()
  if (typeof value === "number" && Number.isFinite(value)) {
    const millis = value > 10_000_000_000 ? value : value * 1000
    return new Date(millis).toISOString()
  }
  return undefined
}

function compactRecord(record: RecordLike): RecordLike {
  return Object.fromEntries(Object.entries(record).filter(([, value]) => value !== undefined && value !== ""))
}

function plainJsonRecord(value: RecordLike): RecordLike {
  return JSON.parse(JSON.stringify(value)) as RecordLike
}

function arrayOfRecords(value: unknown): RecordLike[] {
  return Array.isArray(value) ? value.map((entry) => asRecord(entry) ?? { value: entry }) : []
}

function asRecord(value: unknown): RecordLike | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as RecordLike) : undefined
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined
}
