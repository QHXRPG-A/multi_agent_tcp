export type ConsoleRole = "admin" | "user"
export type ConsoleClientKind = "mobile" | "desktop"

export type ConsoleUser = {
  id: string
  username: string
  role: ConsoleRole
  active: boolean
  createdAt: string
  updatedAt: string
}

export type ConsoleSessionSummary = {
  clientKind: ConsoleClientKind | null
  createdAt: string
  expiresAt: string
  userAgent?: string | null
  idSuffix: string
}

export type ConsoleUserMonitor = {
  user: ConsoleUser
  clients: { mobile: boolean; desktop: boolean }
  activeSessionCount: number
  lastLoginAt?: string | null
  lastClientLogAt?: string | null
  sessions: ConsoleSessionSummary[]
}

export type ConsoleMonitorResponse = {
  ok: boolean
  totals: {
    totalUsers: number
    activeUsers: number
    activeSessions: number
    mobileOnline: number
    desktopOnline: number
  }
  users: ConsoleUserMonitor[]
}

export type ConsoleClientLog = {
  id: number
  createdAt: string
  sessionUserId?: string | null
  level: "debug" | "info" | "warning" | "error"
  event: string
  message: string
  context: Record<string, unknown>
  requestId?: string | null
  clientCreatedAt?: string | null
}

export type ConsoleSessionResponse = {
  ok: boolean
  csrfToken: string
  user?: ConsoleUser
}

class ConsoleApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message)
  }
}

export function isConsoleUnauthorized(error: unknown) {
  return error instanceof ConsoleApiError && error.status === 401
}

export function isConsoleForbidden(error: unknown) {
  return error instanceof ConsoleApiError && error.status === 403
}

export async function getConsoleSession(fetcher: typeof fetch = fetch) {
  return consoleJson<ConsoleSessionResponse>("/api/me", fetcher)
}

export async function loginConsole(username: string, password: string, fetcher: typeof fetch = fetch) {
  return consoleJson<ConsoleSessionResponse>("/api/auth/login", fetcher, {
    method: "POST",
    body: { username, password },
  })
}

export async function loadUserMonitor(fetcher: typeof fetch = fetch) {
  return consoleJson<ConsoleMonitorResponse>("/api/admin/monitor/users", fetcher)
}

export async function loadClientLogs(
  options: { limit?: number; userId?: string | null } = {},
  fetcher: typeof fetch = fetch,
) {
  const params = new URLSearchParams()
  params.set("limit", String(options.limit ?? 80))
  if (options.userId) params.set("userId", options.userId)
  return consoleJson<{ ok: boolean; logs: ConsoleClientLog[] }>(`/api/admin/logs/client?${params}`, fetcher)
}

async function consoleJson<T>(
  path: string,
  fetcher: typeof fetch = fetch,
  options: { method?: "GET" | "POST"; body?: unknown } = {},
): Promise<T> {
  const headers: Record<string, string> = { accept: "application/json" }
  let body: string | undefined
  if (options.body !== undefined) {
    headers["content-type"] = "application/json"
    body = JSON.stringify(options.body)
  }
  const response = await fetcher(consoleApiPath(path), {
    method: options.method ?? "GET",
    credentials: "include",
    headers,
    body,
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ConsoleApiError(
      response.status,
      String(data.code ?? "REQUEST_FAILED"),
      String(data.message ?? response.statusText),
    )
  }
  return data as T
}

function consoleApiPath(path: string) {
  const env = (import.meta as ImportMeta & { env?: { VITE_COLLABORATION_API_URL?: string } }).env
  const base = env?.VITE_COLLABORATION_API_URL?.trim().replace(/\/+$/, "")
  if (!base) return path
  return `${base}${path.startsWith("/") ? path : `/${path}`}`
}
