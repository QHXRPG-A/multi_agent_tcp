import { describe, expect, test } from "bun:test"
import { readFileSync } from "node:fs"
import { loadClientLogs, loadUserMonitor, loginConsole, type ConsoleClientLog, type ConsoleMonitorResponse } from "./api"
import { chooseSelectedUserId } from "./server-console-app"

describe("server console API helpers", () => {
  test("logs in without marking a mobile or desktop client kind", async () => {
    const requests: Array<{ path: string; init?: RequestInit }> = []
    const fetcher = async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ path: String(input), init })
      return json({ ok: true, csrfToken: "csrf-console", user: { id: "admin", username: "admin", role: "admin" } })
    }

    const result = await loginConsole("admin", "admin-pass-123", fetcher as unknown as typeof fetch)

    expect(result.csrfToken).toBe("csrf-console")
    expect(requests[0]?.path).toBe("/api/auth/login")
    expect(requests[0]?.init?.method).toBe("POST")
    expect(requests[0]?.init?.credentials).toBe("include")
    expect(requests[0]?.init?.body).toBe(JSON.stringify({ username: "admin", password: "admin-pass-123" }))
  })

  test("loads monitor and logs with cookie credentials", async () => {
    const requests: Array<{ path: string; init?: RequestInit }> = []
    const fetcher = async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ path: String(input), init })
      if (String(input).startsWith("/api/admin/logs/client")) return json({ ok: true, logs: [] })
      return json(sampleMonitor)
    }

    await loadUserMonitor(fetcher as unknown as typeof fetch)
    await loadClientLogs({ limit: 25, userId: "admin" }, fetcher as unknown as typeof fetch)

    expect(requests[0]?.path).toBe("/api/admin/monitor/users")
    expect(requests[0]?.init?.credentials).toBe("include")
    expect(requests[1]?.path).toBe("/api/admin/logs/client?limit=25&userId=admin")
    expect(requests[1]?.init?.credentials).toBe("include")
  })
})

describe("server console dashboard", () => {
  test("keeps an existing selection when the user still exists", () => {
    expect(chooseSelectedUserId("viewer", sampleMonitor.users)).toBe("viewer")
    expect(chooseSelectedUserId("missing", sampleMonitor.users)).toBe("admin")
  })

  test("declares the expected monitoring surfaces", () => {
    const source = readFileSync("./src/server-console/server-console-app.tsx", "utf8")

    expect(source).toContain("data-testid=\"server-console-app\"")
    expect(source).toContain("Mobile online")
    expect(source).toContain("Desktop online")
    expect(source).toContain("Recent sessions")
    expect(source).toContain("Client logs")
    expect(source).toContain("activeSessionCount")
  })
})

const sampleMonitor = {
  ok: true,
  totals: {
    totalUsers: 2,
    activeUsers: 2,
    activeSessions: 3,
    mobileOnline: 1,
    desktopOnline: 1,
  },
  users: [
    {
      user: {
        id: "admin",
        username: "admin",
        role: "admin",
        active: true,
        createdAt: "2026-05-29T01:00:00Z",
        updatedAt: "2026-05-29T01:00:00Z",
      },
      clients: { mobile: true, desktop: true },
      activeSessionCount: 2,
      lastLoginAt: "2026-05-29T02:00:00Z",
      lastClientLogAt: "2026-05-29T02:01:00Z",
      sessions: [
        {
          clientKind: "mobile",
          createdAt: "2026-05-29T02:00:00Z",
          expiresAt: "2026-06-28T02:00:00Z",
          userAgent: "Chrome Mobile",
          idSuffix: "abcd1234",
        },
      ],
    },
    {
      user: {
        id: "viewer",
        username: "viewer",
        role: "user",
        active: true,
        createdAt: "2026-05-29T01:00:00Z",
        updatedAt: "2026-05-29T01:00:00Z",
      },
      clients: { mobile: false, desktop: false },
      activeSessionCount: 0,
      lastLoginAt: null,
      lastClientLogAt: null,
      sessions: [],
    },
  ],
} satisfies ConsoleMonitorResponse

const sampleLogs = [
  {
    id: 1,
    createdAt: "2026-05-29T02:01:00Z",
    sessionUserId: "admin",
    level: "info",
    event: "mobile.load.success",
    message: "Loaded from API",
    context: {},
  },
] satisfies ConsoleClientLog[]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  })
}
