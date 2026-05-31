import { createSignal, onCleanup, onMount, Show, type ParentProps } from "solid-js"

export type CollaborationClientKind = "mobile" | "desktop"

export const collaborationAuthRequiredEvent = "gulicode:collaboration-auth-required"

type AuthMode = "login" | "register"

export type CollaborationAuthPayload = {
  ok: boolean
  csrfToken: string
  clients?: { mobile: boolean; desktop: boolean }
  syncReady?: boolean
  user?: { id: string; username: string; role?: string }
}

export type DesktopBlueprintSnapshotPayload = {
  projectId?: string
  projectDir?: string
  blueprintId: string
  title?: string
  description?: string
  nodes: Array<{
    id: string
    label: string
    kind?: "agent" | "worker_agent" | "script" | "branch" | "tick"
    role?: string
    state?: "idle" | "queued" | "running" | "completed" | "failed" | "unknown"
    summary?: string
    x?: number
    y?: number
    upstreamNodeIds?: string[]
    downstreamNodeIds?: string[]
    inputPorts?: string[]
    outputPorts?: string[]
    everyNTicks?: number
    agentId?: string
    cliKind?: string
    taskStatus?: string
    queueSize?: number
    messagesSent?: number
    busyCount?: number
    updatedAt?: string
  }>
  edges: Array<{
    source: string
    target: string
    kind?: "exec" | "data" | "unknown"
    outputPort?: string
    inputPort?: string
  }>
}

export type DesktopSessionMessageSegmentPayload = {
  id: string
  type: "text" | "reasoning" | "tool"
  title?: string | null
  body?: string
  status?: string | null
  toolName?: string | null
}

export type DesktopSessionSnapshotPayload = {
  activeSessionId?: string | null
  sessions: Array<{
    id: string
    title?: string
    parentId?: string | null
    createdAt?: string
    updatedAt?: string
    messageCount?: number
  }>
  currentMessages: Array<{
    id: string
    sessionId?: string
    role: string
    label?: string
    body: string
    segments?: DesktopSessionMessageSegmentPayload[]
    createdAt?: string
  }>
  composer?: {
    modes: Array<{
      id: string
      label: string
      kind: "agent" | "blueprintPlanning"
    }>
    activeModeId?: string | null
  }
  updatedAt?: string
}

class CollaborationAuthError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message)
  }
}

export function requireCollaborationAuth() {
  window.dispatchEvent(new CustomEvent(collaborationAuthRequiredEvent))
}

export async function loginCollaboration(
  username: string,
  password: string,
  clientKind: CollaborationClientKind,
  fetcher: typeof fetch = fetch,
) {
  return authJson<CollaborationAuthPayload>("/api/auth/login", fetcher, {
    method: "POST",
    body: { username, password, clientKind },
  })
}

export async function registerCollaboration(username: string, password: string, fetcher: typeof fetch = fetch) {
  return authJson<{ ok: boolean; user?: unknown }>("/api/auth/register", fetcher, {
    method: "POST",
    body: { username, password },
  })
}

export async function registerAndLoginCollaboration(
  username: string,
  password: string,
  clientKind: CollaborationClientKind,
  fetcher: typeof fetch = fetch,
) {
  await registerCollaboration(username, password, fetcher)
  return loginCollaboration(username, password, clientKind, fetcher)
}

export async function getCollaborationSession(fetcher: typeof fetch = fetch) {
  return authJson<CollaborationAuthPayload>("/api/me", fetcher)
}

export async function logoutCollaboration(fetcher: typeof fetch = fetch) {
  return authJson<{ ok: boolean }>("/api/auth/logout", fetcher, { method: "POST" })
}

export async function postDesktopBlueprintSnapshot(payload: DesktopBlueprintSnapshotPayload, fetcher: typeof fetch = fetch) {
  const session = await getCollaborationSession(fetcher)
  await registerDesktopBridge(session, fetcher)
  return authJson<{ ok: boolean; snapshot?: unknown }>("/api/desktop/blueprint-snapshot", fetcher, {
    method: "POST",
    body: payload,
    csrfToken: session.csrfToken,
  })
}

export async function postDesktopSessionSnapshot(payload: DesktopSessionSnapshotPayload, fetcher: typeof fetch = fetch) {
  const session = await getCollaborationSession(fetcher)
  await registerDesktopBridge(session, fetcher)
  return authJson<{ ok: boolean; desktopSessions?: unknown }>("/api/desktop/session-snapshot", fetcher, {
    method: "POST",
    body: payload,
    csrfToken: session.csrfToken,
  })
}

export async function registerDesktopBridge(session?: CollaborationAuthPayload, fetcher: typeof fetch = fetch) {
  const bridge = await getDesktopControlBridgeInfo()
  if (!bridge) return undefined
  const current = session ?? (await getCollaborationSession(fetcher))
  if (!current.user || current.clients?.desktop === false) return undefined
  return authJson<{ ok: boolean; desktopBridge?: unknown }>("/api/desktop/bridge", fetcher, {
    method: "POST",
    body: bridge,
    csrfToken: current.csrfToken,
  })
}

export function CollaborationAuthGate(
  props: ParentProps<{
    clientKind: CollaborationClientKind
    defaultUsername?: string
  }>,
) {
  const [checking, setChecking] = createSignal(true)
  const [authenticated, setAuthenticated] = createSignal(false)
  const [mode, setMode] = createSignal<AuthMode>("login")
  const [username, setUsername] = createSignal(props.defaultUsername ?? "")
  const [password, setPassword] = createSignal("")
  const [confirmPassword, setConfirmPassword] = createSignal("")
  const [submitting, setSubmitting] = createSignal(false)
  const [error, setError] = createSignal<string | null>(null)

  const checkSession = async () => {
    setChecking(true)
    try {
      const session = await authJson<CollaborationAuthPayload>("/api/me")
      if (props.clientKind === "desktop") await registerDesktopBridge(session).catch(() => undefined)
      if (session.clients && !session.clients[props.clientKind]) {
        setAuthenticated(false)
        setMode("login")
        return
      }
      setAuthenticated(true)
      setError(null)
    } catch (sessionError) {
      if (isAuthUnauthorized(sessionError)) {
        setAuthenticated(false)
        setMode("login")
      } else {
        setAuthenticated(false)
        setError(sessionError instanceof Error ? sessionError.message : String(sessionError))
      }
    } finally {
      setChecking(false)
    }
  }

  const submit = async (event: SubmitEvent) => {
    event.preventDefault()
    if (submitting()) return
    const trimmedUsername = username().trim()
    const currentPassword = password()
    if (!trimmedUsername || !currentPassword) {
      setError("请输入用户名和密码。")
      return
    }
    if (mode() === "register") {
      if (currentPassword.length < 8) {
        setError("注册密码至少需要 8 位。")
        return
      }
      if (currentPassword !== confirmPassword()) {
        setError("两次输入的密码不一致。")
        return
      }
    }

    setSubmitting(true)
    setError(null)
    try {
      if (mode() === "register") {
        await registerAndLoginCollaboration(trimmedUsername, currentPassword, props.clientKind)
      } else {
        const session = await loginCollaboration(trimmedUsername, currentPassword, props.clientKind)
        if (props.clientKind === "desktop") await registerDesktopBridge(session).catch(() => undefined)
      }
      setAuthenticated(true)
      setPassword("")
      setConfirmPassword("")
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : String(submitError))
    } finally {
      setSubmitting(false)
    }
  }

  onMount(() => {
    const handleAuthRequired = () => {
      setAuthenticated(false)
      setMode("login")
      setChecking(false)
    }
    window.addEventListener(collaborationAuthRequiredEvent, handleAuthRequired)
    void checkSession()
    onCleanup(() => {
      window.removeEventListener(collaborationAuthRequiredEvent, handleAuthRequired)
    })
  })

  return (
    <Show when={authenticated()} fallback={<AuthPanel />}>
      {props.children}
    </Show>
  )

  function AuthPanel() {
    const isRegister = () => mode() === "register"
    const canSubmit = () =>
      Boolean(username().trim() && password() && !submitting() && !checking() && (!isRegister() || confirmPassword()))

    return (
      <div
        data-testid="collaboration-auth-gate"
        class="flex min-h-screen w-full items-center justify-center bg-[#fbf7f4] px-5 py-8 text-[#161312]"
      >
        <form
          data-testid={isRegister() ? "collaboration-register-form" : "collaboration-login-form"}
          class="grid w-full max-w-[420px] gap-4 rounded-md border border-[#eaded7] bg-[#fffdfa] p-5 shadow-[0_22px_60px_rgba(48,38,32,0.10)]"
          onSubmit={submit}
        >
          <div>
            <p class="text-12-medium uppercase tracking-[0.14em] text-[#b5837d]">GuLiCode</p>
            <h1 class="mt-1 text-22-semibold text-[#161312]">{isRegister() ? "注册" : "登录"}</h1>
            <p class="mt-2 text-13-regular leading-5 text-[#81756e]">
              {props.clientKind === "mobile" ? "移动端协作访问" : "桌面端协作访问"}
            </p>
          </div>

          <label class="grid gap-1 text-12-medium text-[#6f6560]">
            用户名
            <input
              data-testid="collaboration-auth-username"
              class="h-10 rounded-md border border-[#eaded7] bg-white px-3 text-14-regular text-[#3c3430] outline-none transition-colors focus:border-[#b94f45]"
              value={username()}
              autocomplete="username"
              disabled={submitting() || checking()}
              onInput={(event) => setUsername(event.currentTarget.value)}
            />
          </label>

          <label class="grid gap-1 text-12-medium text-[#6f6560]">
            密码
            <input
              data-testid="collaboration-auth-password"
              type="password"
              class="h-10 rounded-md border border-[#eaded7] bg-white px-3 text-14-regular text-[#3c3430] outline-none transition-colors focus:border-[#b94f45]"
              value={password()}
              autocomplete={isRegister() ? "new-password" : "current-password"}
              disabled={submitting() || checking()}
              onInput={(event) => setPassword(event.currentTarget.value)}
            />
          </label>

          <Show when={isRegister()}>
            <label class="grid gap-1 text-12-medium text-[#6f6560]">
              确认密码
              <input
                data-testid="collaboration-auth-confirm"
                type="password"
                class="h-10 rounded-md border border-[#eaded7] bg-white px-3 text-14-regular text-[#3c3430] outline-none transition-colors focus:border-[#b94f45]"
                value={confirmPassword()}
                autocomplete="new-password"
                disabled={submitting() || checking()}
                onInput={(event) => setConfirmPassword(event.currentTarget.value)}
              />
            </label>
          </Show>

          <Show when={error()}>
            {(message) => (
              <div class="rounded-md border border-[#f0d4cf] bg-[#fff1ef] px-3 py-2 text-12-regular text-[#6f3932]">
                {message()}
              </div>
            )}
          </Show>

          <button
            data-testid="collaboration-auth-submit"
            type="submit"
            disabled={!canSubmit()}
            class="h-10 rounded-md border px-4 text-14-medium transition-colors"
            style={{
              "background-color": canSubmit() ? "#161312" : "#e6ddd8",
              "border-color": canSubmit() ? "#161312" : "#dccfc8",
              color: canSubmit() ? "#ffffff" : "#6f6560",
            }}
          >
            {checking() ? "检查中..." : submitting() ? "提交中..." : isRegister() ? "注册并登录" : "登录"}
          </button>

          <button
            type="button"
            data-testid={isRegister() ? "collaboration-auth-login-link" : "collaboration-auth-register-link"}
            class="justify-self-start text-13-medium text-[#b94f45] hover:text-[#8f362e]"
            disabled={submitting() || checking()}
            onClick={() => {
              setError(null)
              setMode(isRegister() ? "login" : "register")
            }}
          >
            {isRegister() ? "返回登录" : "创建账号"}
          </button>
        </form>
      </div>
    )
  }
}

export function BlueprintCollaborationAuthPanel(props: { defaultUsername?: string }) {
  const clientKind: CollaborationClientKind = "desktop"
  const [checking, setChecking] = createSignal(true)
  const [session, setSession] = createSignal<CollaborationAuthPayload | null>(null)
  const [expanded, setExpanded] = createSignal(false)
  const [mode, setMode] = createSignal<AuthMode>("login")
  const [username, setUsername] = createSignal(props.defaultUsername ?? "1")
  const [password, setPassword] = createSignal("")
  const [confirmPassword, setConfirmPassword] = createSignal("")
  const [submitting, setSubmitting] = createSignal(false)
  const [error, setError] = createSignal<string | null>(null)

  const hasDesktopSession = () => {
    const current = session()
    if (!current?.user) return false
    return current.clients ? current.clients[clientKind] : true
  }
  const mobileOnline = () => session()?.clients?.mobile === true
  const statusText = () => {
    if (checking()) return "检查中"
    if (hasDesktopSession()) return "已登录"
    if (session()?.user) return "需桌面登录"
    if (error()) return "服务异常"
    return "未登录"
  }
  const syncText = () => {
    const current = session()
    if (!hasDesktopSession()) return "登录后同步移动端状态"
    if (current?.syncReady) return "移动端已连接"
    return mobileOnline() ? "等待同步就绪" : "等待移动端登录"
  }

  const refreshSession = async (openWhenLoggedOut = false) => {
    setChecking(true)
    try {
      const next = await getCollaborationSession()
      await registerDesktopBridge(next).catch(() => undefined)
      setSession(next)
      setError(null)
      setExpanded(openWhenLoggedOut && (!next.user || (next.clients ? !next.clients[clientKind] : false)))
    } catch (sessionError) {
      setSession(null)
      if (isAuthUnauthorized(sessionError)) {
        setError(null)
      } else {
        setError(sessionError instanceof Error ? sessionError.message : String(sessionError))
      }
      if (openWhenLoggedOut) setExpanded(true)
    } finally {
      setChecking(false)
    }
  }

  const submit = async (event: SubmitEvent) => {
    event.preventDefault()
    if (submitting()) return
    const trimmedUsername = username().trim()
    const currentPassword = password()
    if (!trimmedUsername || !currentPassword) {
      setError("请输入用户名和密码。")
      return
    }
    if (mode() === "register") {
      if (currentPassword.length < 8) {
        setError("注册密码至少需要 8 位。")
        return
      }
      if (currentPassword !== confirmPassword()) {
        setError("两次输入的密码不一致。")
        return
      }
    }

    setSubmitting(true)
    setError(null)
    try {
      const next =
        mode() === "register"
          ? await registerAndLoginCollaboration(trimmedUsername, currentPassword, clientKind)
          : await loginCollaboration(trimmedUsername, currentPassword, clientKind)
      await registerDesktopBridge(next).catch(() => undefined)
      setSession(next)
      setExpanded(false)
      setPassword("")
      setConfirmPassword("")
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : String(submitError))
    } finally {
      setSubmitting(false)
    }
  }

  const logout = async () => {
    if (submitting()) return
    setSubmitting(true)
    setError(null)
    try {
      await logoutCollaboration()
      setSession(null)
      setExpanded(true)
    } catch (logoutError) {
      setError(logoutError instanceof Error ? logoutError.message : String(logoutError))
    } finally {
      setSubmitting(false)
    }
  }

  onMount(() => {
    void refreshSession(true)
  })

  return (
    <div
      data-testid="blueprint-collaboration-auth-panel"
      class="w-[268px] max-w-[calc(100vw-32px)] rounded-md border border-[rgba(103,232,249,0.28)] bg-[rgba(7,16,25,0.94)] text-[#d6e9f5] shadow-[0_18px_48px_rgba(0,0,0,0.38)] backdrop-blur"
      onPointerDown={(event) => event.stopPropagation()}
      onWheel={(event) => event.stopPropagation()}
    >
      <div class="flex items-start justify-between gap-3 border-b border-[rgba(103,232,249,0.16)] px-3 py-2">
        <div class="min-w-0">
          <div class="text-10-medium uppercase tracking-[0.12em] text-[#67e8f9]">蓝图协作</div>
          <div class="mt-0.5 truncate text-12-medium text-[#f8fdff]">{statusText()}</div>
        </div>
        <button
          type="button"
          class="shrink-0 rounded border border-[rgba(103,232,249,0.32)] px-2 py-1 text-11-medium text-[#d6e9f5] transition-colors hover:border-[#67e8f9] hover:text-[#f8fdff] disabled:border-[rgba(103,232,249,0.16)] disabled:text-[#6f8799]"
          disabled={checking() || submitting()}
          onClick={() => setExpanded((open) => !open)}
        >
          {expanded() ? "收起" : hasDesktopSession() ? "管理" : "登录"}
        </button>
      </div>

      <div class="grid gap-2 px-3 py-2">
        <Show when={hasDesktopSession()} fallback={<LoggedOutBody />}>
          <div class="grid gap-1 text-12-regular text-[#95afc4]">
            <div class="truncate text-[#f8fdff]">用户：{session()?.user?.username ?? "-"}</div>
            <div>{syncText()}</div>
          </div>
          <Show when={expanded()}>
            <button
              type="button"
              class="h-8 rounded border border-[rgba(248,113,113,0.42)] bg-[rgba(127,29,29,0.18)] px-3 text-12-medium text-[#fecaca] transition-colors hover:border-[#fca5a5] disabled:text-[#7f8a94]"
              disabled={submitting()}
              onClick={() => void logout()}
            >
              {submitting() ? "退出中..." : "退出登录"}
            </button>
          </Show>
        </Show>
      </div>
    </div>
  )

  function LoggedOutBody() {
    const isRegister = () => mode() === "register"
    const canSubmit = () => Boolean(username().trim() && password() && !submitting() && !checking() && (!isRegister() || confirmPassword()))

    return (
      <>
        <div class="text-12-regular leading-5 text-[#95afc4]">{syncText()}</div>
        <Show when={session()?.user && !session()?.clients?.desktop}>
          <div class="rounded border border-[rgba(250,204,21,0.24)] bg-[rgba(113,63,18,0.20)] px-2 py-1.5 text-11-regular text-[#fde68a]">
            当前账号还没有桌面端会话，请在这里登录一次。
          </div>
        </Show>
        <Show when={error()}>
          {(message) => (
            <div class="rounded border border-[rgba(248,113,113,0.30)] bg-[rgba(127,29,29,0.20)] px-2 py-1.5 text-11-regular text-[#fecaca]">
              {message()}
            </div>
          )}
        </Show>
        <Show
          when={expanded()}
          fallback={
            <button
              type="button"
              class="h-8 rounded border border-[rgba(103,232,249,0.32)] bg-[rgba(103,232,249,0.08)] px-3 text-12-medium text-[#e8f7ff] transition-colors hover:border-[#67e8f9]"
              onClick={() => setExpanded(true)}
            >
              登录 / 注册
            </button>
          }
        >
          <form class="grid gap-2" onSubmit={submit}>
            <input
              data-testid="blueprint-collaboration-username"
              class="h-8 rounded border border-[rgba(103,232,249,0.22)] bg-[#071019] px-2 text-12-regular text-[#f8fdff] outline-none transition-colors placeholder:text-[#557086] focus:border-[#67e8f9]"
              value={username()}
              autocomplete="username"
              placeholder="用户名"
              disabled={submitting() || checking()}
              onInput={(event) => setUsername(event.currentTarget.value)}
            />
            <input
              data-testid="blueprint-collaboration-password"
              type="password"
              class="h-8 rounded border border-[rgba(103,232,249,0.22)] bg-[#071019] px-2 text-12-regular text-[#f8fdff] outline-none transition-colors placeholder:text-[#557086] focus:border-[#67e8f9]"
              value={password()}
              autocomplete={isRegister() ? "new-password" : "current-password"}
              placeholder="密码"
              disabled={submitting() || checking()}
              onInput={(event) => setPassword(event.currentTarget.value)}
            />
            <Show when={isRegister()}>
              <input
                data-testid="blueprint-collaboration-confirm"
                type="password"
                class="h-8 rounded border border-[rgba(103,232,249,0.22)] bg-[#071019] px-2 text-12-regular text-[#f8fdff] outline-none transition-colors placeholder:text-[#557086] focus:border-[#67e8f9]"
                value={confirmPassword()}
                autocomplete="new-password"
                placeholder="确认密码"
                disabled={submitting() || checking()}
                onInput={(event) => setConfirmPassword(event.currentTarget.value)}
              />
            </Show>
            <button
              data-testid="blueprint-collaboration-submit"
              type="submit"
              disabled={!canSubmit()}
              class="h-8 rounded border border-[#67e8f9] bg-[rgba(103,232,249,0.18)] px-3 text-12-medium text-[#f8fdff] transition-colors hover:bg-[rgba(103,232,249,0.26)] disabled:border-[rgba(103,232,249,0.18)] disabled:bg-[#10202d] disabled:text-[#88a2b4]"
            >
              {submitting() ? "提交中..." : isRegister() ? "注册并登录" : "登录"}
            </button>
            <button
              type="button"
              class="justify-self-start text-11-medium text-[#67e8f9] hover:text-[#b9efff] disabled:text-[#557086]"
              disabled={submitting() || checking()}
              onClick={() => {
                setError(null)
                setMode(isRegister() ? "login" : "register")
              }}
            >
              {isRegister() ? "返回登录" : "创建账号"}
            </button>
          </form>
        </Show>
      </>
    )
  }
}

function isAuthUnauthorized(error: unknown) {
  return error instanceof CollaborationAuthError && error.status === 401
}

async function authJson<T>(
  path: string,
  fetcher: typeof fetch = fetch,
  options: { method?: "GET" | "POST"; body?: unknown; csrfToken?: string } = {},
): Promise<T> {
  const headers: Record<string, string> = { accept: "application/json" }
  let body: string | undefined
  if (options.body !== undefined) {
    headers["content-type"] = "application/json"
    body = JSON.stringify(options.body)
  }
  if (options.csrfToken) headers["x-csrf-token"] = options.csrfToken
  const response = await fetcher(collaborationAuthApiPath(path), {
    method: options.method ?? "GET",
    credentials: "include",
    headers,
    body,
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new CollaborationAuthError(
      response.status,
      String(data.code ?? "REQUEST_FAILED"),
      String(data.message ?? response.statusText),
    )
  }
  return data as T
}

function collaborationAuthApiPath(path: string) {
  const env = (import.meta as ImportMeta & { env?: { VITE_COLLABORATION_API_URL?: string } }).env
  const base = env?.VITE_COLLABORATION_API_URL?.trim().replace(/\/+$/, "")
  if (!base) return path
  return `${base}${path.startsWith("/") ? path : `/${path}`}`
}

async function getDesktopControlBridgeInfo() {
  const api = (globalThis as typeof globalThis & {
    window?: {
      api?: {
        getDesktopControlBridge?: () => Promise<{ bridgeUrl: string; bridgeToken: string }>
      }
    }
  }).window?.api
  if (typeof api?.getDesktopControlBridge !== "function") return undefined
  return api.getDesktopControlBridge().catch(() => undefined)
}
