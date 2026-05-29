export type MobileLogLevel = "debug" | "info" | "warning" | "error"

export type MobileLogEntry = {
  id: string
  ts: string
  level: MobileLogLevel
  event: string
  message?: string
  context: Record<string, unknown>
  requestId?: string
}

type LogOptions = {
  fetcher?: typeof fetch
  upload?: boolean
  requestId?: string
}

const STORAGE_KEY = "gulicode.mobile.logs"
const RING_LIMIT = 200
const UPLOAD_BATCH_LIMIT = 50
const MAX_STRING_LENGTH = 1000
const SENSITIVE_KEY_PARTS = ["authorization", "bearer", "cookie", "csrf", "password", "secret", "session", "token"]
const ABSOLUTE_WINDOWS_PATH = /\b[A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\?)+/g
const ABSOLUTE_POSIX_PATH = /(?<!:)\/(?:Users|home|tmp|var|opt|etc|mnt|src|workspace)\/[^\s"']+/g
const INLINE_SECRET = /\b(token|secret|password|cookie|csrf)\b\s*[:= ]+\s*[^,\s;]+/gi

let entries: MobileLogEntry[] = readStoredLogs()
let pendingUpload: MobileLogEntry[] = []
let uploadTimer: ReturnType<typeof setTimeout> | undefined
let defaultFetcher: typeof fetch | undefined
let uploadEnabled = true
let lastUploadError: string | undefined

export function configureMobileLogger(options: { fetcher?: typeof fetch; uploadEnabled?: boolean } = {}) {
  defaultFetcher = options.fetcher ?? defaultFetcher
  if (typeof options.uploadEnabled === "boolean") uploadEnabled = options.uploadEnabled
}

export function logMobileEvent(
  level: MobileLogLevel,
  event: string,
  message?: string,
  context: Record<string, unknown> = {},
  options: LogOptions = {},
): MobileLogEntry {
  const entry: MobileLogEntry = {
    id: `mlog_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
    ts: new Date().toISOString(),
    level,
    event: event.slice(0, 128),
    message: message ? sanitizeString(message).slice(0, 1024) : undefined,
    context: sanitizeContext(context),
    requestId: options.requestId,
  }
  entries = [...entries.slice(-(RING_LIMIT - 1)), entry]
  pendingUpload = [...pendingUpload.slice(-(RING_LIMIT - 1)), entry]
  writeStoredLogs(entries)
  if (options.upload !== false) scheduleUpload(options.fetcher)
  return entry
}

export function getMobileLogs(): MobileLogEntry[] {
  return [...entries]
}

export function clearMobileLogs() {
  entries = []
  pendingUpload = []
  lastUploadError = undefined
  writeStoredLogs(entries)
}

export function getMobileLogUploadError() {
  return lastUploadError
}

export async function flushMobileLogs(fetcher?: typeof fetch): Promise<number> {
  if (!uploadEnabled || !pendingUpload.length) return 0
  const activeFetcher = fetcher ?? defaultFetcher ?? safeGlobalFetch()
  if (!activeFetcher) return 0
  const batch = pendingUpload.splice(0, UPLOAD_BATCH_LIMIT)
  try {
    const response = await activeFetcher("/api/client-logs", {
      method: "POST",
      credentials: "include",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        logs: batch.map((entry) => ({
          level: entry.level,
          event: entry.event,
          message: entry.message,
          context: entry.context,
          requestId: entry.requestId,
          createdAt: entry.ts,
        })),
      }),
    })
    if (!response.ok) throw new Error(`client log upload failed: ${response.status}`)
    lastUploadError = undefined
    return batch.length
  } catch (error) {
    pendingUpload = [...batch, ...pendingUpload].slice(-RING_LIMIT)
    lastUploadError = error instanceof Error ? error.message : String(error)
    return 0
  }
}

export function resetMobileLoggerForTests() {
  clearMobileLogs()
  defaultFetcher = undefined
  uploadEnabled = true
  if (uploadTimer) clearTimeout(uploadTimer)
  uploadTimer = undefined
}

function scheduleUpload(fetcher?: typeof fetch) {
  if (!uploadEnabled) return
  const activeFetcher = fetcher ?? defaultFetcher ?? safeGlobalFetch()
  if (!activeFetcher || uploadTimer) return
  uploadTimer = setTimeout(() => {
    uploadTimer = undefined
    void flushMobileLogs(activeFetcher)
  }, 250)
}

function sanitizeContext(value: Record<string, unknown>): Record<string, unknown> {
  const sanitized = sanitizeValue(value, 0)
  return isRecord(sanitized) ? sanitized : {}
}

function sanitizeValue(value: unknown, depth: number): unknown {
  if (depth > 5) return "[truncated]"
  if (Array.isArray(value)) return value.slice(0, 50).map((item) => sanitizeValue(item, depth + 1))
  if (isRecord(value)) {
    const result: Record<string, unknown> = {}
    for (const [key, item] of Object.entries(value).slice(0, 80)) {
      const lowered = key.toLowerCase().replace(/-/g, "_")
      if (SENSITIVE_KEY_PARTS.some((part) => lowered.includes(part))) {
        result[key] = "[redacted]"
      } else {
        result[key] = sanitizeValue(item, depth + 1)
      }
    }
    return result
  }
  if (typeof value === "string") return sanitizeString(value)
  if (typeof value === "number" || typeof value === "boolean" || value === null || value === undefined) return value
  return sanitizeString(String(value))
}

function sanitizeString(value: string) {
  const cleaned = value
    .replace(INLINE_SECRET, (_, label: string) => `${label}=[redacted]`)
    .replace(ABSOLUTE_WINDOWS_PATH, "[redacted-path]")
    .replace(ABSOLUTE_POSIX_PATH, "[redacted-path]")
  return cleaned.length > MAX_STRING_LENGTH ? `${cleaned.slice(0, MAX_STRING_LENGTH)}...[truncated]` : cleaned
}

function readStoredLogs(): MobileLogEntry[] {
  try {
    const raw = globalThis.localStorage?.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.slice(-RING_LIMIT) : []
  } catch {
    return []
  }
}

function writeStoredLogs(value: MobileLogEntry[]) {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(value.slice(-RING_LIMIT)))
  } catch {
    // Storage can be unavailable in private mode or tests; in-memory logs still work.
  }
}

function safeGlobalFetch() {
  return typeof fetch === "function" ? fetch : undefined
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}
