import { describe, expect, test } from "bun:test"
import {
  getCollaborationSession,
  loginCollaboration,
  logoutCollaboration,
  postDesktopBlueprintSnapshot,
  registerAndLoginCollaboration,
} from "./collaboration-auth"

describe("collaboration auth API helpers", () => {
  test("logs in with the requested client kind and cookie credentials", async () => {
    const requests: Array<{ path: string; init?: RequestInit }> = []
    const fetcher = async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ path: String(input), init })
      return json({ ok: true, csrfToken: "csrf-1", clients: { mobile: false, desktop: true }, syncReady: false })
    }

    const result = await loginCollaboration("debug", "debug-pass-123", "desktop", fetcher as unknown as typeof fetch)

    expect(result.csrfToken).toBe("csrf-1")
    expect(requests[0]?.path).toBe("/api/auth/login")
    expect(requests[0]?.init?.method).toBe("POST")
    expect(requests[0]?.init?.credentials).toBe("include")
    expect(requests[0]?.init?.body).toBe(
      JSON.stringify({ username: "debug", password: "debug-pass-123", clientKind: "desktop" }),
    )
  })

  test("register success automatically logs in with the same client kind", async () => {
    const requests: Array<{ path: string; init?: RequestInit }> = []
    const fetcher = async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ path: String(input), init })
      if (String(input) === "/api/auth/register") return json({ ok: true, user: { username: "alice" } })
      return json({ ok: true, csrfToken: "csrf-login", clients: { mobile: true, desktop: false }, syncReady: false })
    }

    const result = await registerAndLoginCollaboration("alice", "alice-pass-123", "mobile", fetcher as unknown as typeof fetch)

    expect(result.csrfToken).toBe("csrf-login")
    expect(requests.map((request) => request.path)).toEqual(["/api/auth/register", "/api/auth/login"])
    expect(requests[0]?.init?.body).toBe(JSON.stringify({ username: "alice", password: "alice-pass-123" }))
    expect(requests[1]?.init?.body).toBe(
      JSON.stringify({ username: "alice", password: "alice-pass-123", clientKind: "mobile" }),
    )
  })

  test("loads and logs out the current collaboration session with cookies", async () => {
    const requests: Array<{ path: string; init?: RequestInit }> = []
    const fetcher = async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ path: String(input), init })
      return json({
        ok: true,
        csrfToken: "csrf-me",
        user: { id: "usr_1", username: "debug" },
        clients: { mobile: false, desktop: true },
        syncReady: false,
      })
    }

    const session = await getCollaborationSession(fetcher as unknown as typeof fetch)
    await logoutCollaboration(fetcher as unknown as typeof fetch)

    expect(session.user?.username).toBe("debug")
    expect(requests.map((request) => request.path)).toEqual(["/api/me", "/api/auth/logout"])
    expect(requests[0]?.init?.credentials).toBe("include")
    expect(requests[1]?.init?.method).toBe("POST")
    expect(requests[1]?.init?.credentials).toBe("include")
  })

  test("posts desktop blueprint snapshots with CSRF", async () => {
    const requests: Array<{ path: string; init?: RequestInit }> = []
    const fetcher = async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ path: String(input), init })
      if (String(input) === "/api/me") {
        return json({ ok: true, csrfToken: "csrf-me", clients: { mobile: true, desktop: true }, syncReady: true })
      }
      return json({ ok: true, snapshot: { blueprintId: "default" } })
    }

    await postDesktopBlueprintSnapshot(
      {
        projectDir: "C:/repo",
        blueprintId: "default",
        title: "当前蓝图",
        nodes: [{ id: "agent-a", label: "Agent A", state: "idle", x: 120, y: 240 }],
        edges: [],
      },
      fetcher as unknown as typeof fetch,
    )

    expect(requests.map((request) => request.path)).toEqual(["/api/me", "/api/desktop/blueprint-snapshot"])
    expect(requests[1]?.init?.method).toBe("POST")
    expect((requests[1]?.init?.headers as Record<string, string>)["x-csrf-token"]).toBe("csrf-me")
    expect(requests[1]?.init?.body).toContain('"projectDir":"C:/repo"')
    expect(requests[1]?.init?.body).toContain('"x":120')
  })
})

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  })
}
