/** @jsxImportSource solid-js */
import { Icon } from "@opencode-ai/ui/icon"
import { createMemo, createSignal, For, onCleanup, onMount, Show, type ParentProps } from "solid-js"
import {
  getConsoleSession,
  isConsoleForbidden,
  isConsoleUnauthorized,
  loadClientLogs,
  loadUserMonitor,
  loginConsole,
  type ConsoleClientLog,
  type ConsoleMonitorResponse,
  type ConsoleUserMonitor,
} from "./api"

type Fetcher = typeof fetch

export function ServerConsoleApp(props: { fetcher?: Fetcher }) {
  return (
    <ServerConsoleAuthGate fetcher={props.fetcher}>
      <ServerConsoleShell fetcher={props.fetcher ?? fetch} />
    </ServerConsoleAuthGate>
  )
}

function ServerConsoleAuthGate(props: ParentProps<{ fetcher?: Fetcher }>) {
  const fetcher = () => props.fetcher ?? fetch
  const [checking, setChecking] = createSignal(true)
  const [authenticated, setAuthenticated] = createSignal(false)
  const [username, setUsername] = createSignal("1")
  const [password, setPassword] = createSignal("")
  const [submitting, setSubmitting] = createSignal(false)
  const [error, setError] = createSignal<string | null>(null)

  const checkSession = async () => {
    setChecking(true)
    try {
      const session = await getConsoleSession(fetcher())
      if (session.user?.role !== "admin") {
        setAuthenticated(false)
        setError("Admin account required")
        return
      }
      setAuthenticated(true)
      setError(null)
    } catch (sessionError) {
      setAuthenticated(false)
      if (isConsoleUnauthorized(sessionError)) {
        setError(null)
      } else if (isConsoleForbidden(sessionError)) {
        setError("Admin account required")
      } else {
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
    if (!trimmedUsername || !password()) {
      setError("Enter username and password")
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      const session = await loginConsole(trimmedUsername, password(), fetcher())
      if (session.user?.role !== "admin") {
        setAuthenticated(false)
        setError("Admin account required")
        return
      }
      setAuthenticated(true)
      setPassword("")
    } catch (loginError) {
      setAuthenticated(false)
      setError(loginError instanceof Error ? loginError.message : String(loginError))
    } finally {
      setSubmitting(false)
    }
  }

  onMount(() => {
    void checkSession()
  })

  return (
    <Show when={authenticated()} fallback={<AuthPanel />}>
      {props.children}
    </Show>
  )

  function AuthPanel() {
    const canSubmit = () => Boolean(username().trim() && password() && !submitting() && !checking())

    return (
      <div class="flex min-h-screen w-full items-center justify-center bg-[#f6f8fb] px-5 py-8 text-[#151b23]">
        <form
          data-testid="server-console-login-form"
          class="grid w-full max-w-[420px] gap-4 rounded-md border border-[#d7dee8] bg-white p-5 shadow-[0_20px_48px_rgba(30,42,58,0.12)]"
          onSubmit={submit}
        >
          <div class="flex items-start gap-3">
            <div class="flex size-10 shrink-0 items-center justify-center rounded-md border border-[#c5d2e2] bg-[#edf4fb] text-[#245c8f]">
              <Icon name="server" size="small" />
            </div>
            <div class="min-w-0">
              <p class="text-12-medium uppercase tracking-[0.14em] text-[#607086]">GuLiCode</p>
              <h1 class="mt-1 text-22-semibold text-[#151b23]">Server Console</h1>
            </div>
          </div>

          <label class="grid gap-1 text-12-medium text-[#536173]">
            Username
            <input
              data-testid="server-console-username"
              class="h-10 rounded-md border border-[#d7dee8] bg-white px-3 text-14-regular text-[#151b23] outline-none transition-colors focus:border-[#3478b9]"
              value={username()}
              autocomplete="username"
              disabled={submitting() || checking()}
              onInput={(event) => setUsername(event.currentTarget.value)}
            />
          </label>

          <label class="grid gap-1 text-12-medium text-[#536173]">
            Password
            <input
              data-testid="server-console-password"
              type="password"
              class="h-10 rounded-md border border-[#d7dee8] bg-white px-3 text-14-regular text-[#151b23] outline-none transition-colors focus:border-[#3478b9]"
              value={password()}
              autocomplete="current-password"
              disabled={submitting() || checking()}
              onInput={(event) => setPassword(event.currentTarget.value)}
            />
          </label>

          <Show when={error()}>
            {(message) => (
              <div class="rounded-md border border-[#f1c9c9] bg-[#fff2f2] px-3 py-2 text-12-regular text-[#8b3434]">
                {message()}
              </div>
            )}
          </Show>

          <button
            data-testid="server-console-submit"
            type="submit"
            disabled={!canSubmit()}
            class="inline-flex h-10 items-center justify-center gap-2 rounded-md border px-4 text-14-medium transition-colors"
            classList={{
              "border-[#151b23] bg-[#151b23] text-white hover:bg-[#26313e]": canSubmit(),
              "border-[#d7dee8] bg-[#e7edf4] text-[#66758a]": !canSubmit(),
            }}
          >
            <Icon name="enter" size="small" />
            {checking() ? "Checking" : submitting() ? "Signing in" : "Sign in"}
          </button>
        </form>
      </div>
    )
  }
}

function ServerConsoleShell(props: { fetcher: Fetcher }) {
  const [monitor, setMonitor] = createSignal<ConsoleMonitorResponse | null>(null)
  const [logs, setLogs] = createSignal<ConsoleClientLog[]>([])
  const [selectedUserId, setSelectedUserId] = createSignal<string | null>(null)
  const [loading, setLoading] = createSignal(true)
  const [error, setError] = createSignal<string | null>(null)
  let timer: number | undefined

  const refresh = async () => {
    setLoading(true)
    try {
      const [nextMonitor, nextLogs] = await Promise.all([
        loadUserMonitor(props.fetcher),
        loadClientLogs({ limit: 80 }, props.fetcher),
      ])
      setMonitor(nextMonitor)
      setLogs(nextLogs.logs ?? [])
      setSelectedUserId((current) => chooseSelectedUserId(current, nextMonitor.users))
      setError(null)
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : String(refreshError))
    } finally {
      setLoading(false)
    }
  }

  onMount(() => {
    void refresh()
    timer = window.setInterval(() => {
      void refresh()
    }, 2500)
    onCleanup(() => {
      if (timer) window.clearInterval(timer)
    })
  })

  return (
    <ServerConsoleDashboard
      monitor={monitor()}
      logs={logs()}
      selectedUserId={selectedUserId()}
      loading={loading()}
      error={error()}
      onSelectUser={setSelectedUserId}
      onRefresh={() => void refresh()}
    />
  )
}

export function ServerConsoleDashboard(props: {
  monitor: ConsoleMonitorResponse | null
  logs: ConsoleClientLog[]
  selectedUserId: string | null
  loading?: boolean
  error?: string | null
  onSelectUser: (userId: string) => void
  onRefresh: () => void
}) {
  const users = createMemo(() => props.monitor?.users ?? [])
  const selectedUser = createMemo(() => users().find((item) => item.user.id === props.selectedUserId) ?? users()[0] ?? null)
  const visibleLogs = createMemo(() => {
    const selected = selectedUser()
    if (!selected) return props.logs
    const filtered = props.logs.filter((log) => log.sessionUserId === selected.user.id)
    return filtered.length ? filtered : props.logs
  })

  return (
    <div data-testid="server-console-app" class="min-h-screen bg-[#f6f8fb] text-[#151b23]">
      <header class="border-b border-[#d7dee8] bg-white">
        <div class="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-4 px-5 py-4">
          <div class="min-w-0">
            <p class="text-11-medium uppercase tracking-[0.16em] text-[#607086]">GuLiCode</p>
            <h1 class="mt-1 text-24-semibold text-[#151b23]">Server Console</h1>
          </div>
          <button
            type="button"
            data-testid="server-console-refresh"
            class="inline-flex h-9 items-center gap-2 rounded-md border border-[#c5d2e2] bg-[#edf4fb] px-3 text-13-medium text-[#245c8f] transition-colors hover:border-[#8fb1d4] hover:bg-[#e2eef9]"
            onClick={props.onRefresh}
          >
            <Icon name="reset" size="small" />
            {props.loading ? "Refreshing" : "Refresh"}
          </button>
        </div>
      </header>

      <main class="mx-auto grid max-w-[1440px] gap-4 px-5 py-5">
        <Show when={props.error}>
          {(message) => (
            <div class="rounded-md border border-[#f1c9c9] bg-[#fff2f2] px-3 py-2 text-13-regular text-[#8b3434]">
              {message()}
            </div>
          )}
        </Show>

        <section class="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" aria-label="Server totals">
          <MetricTile label="Users" value={props.monitor?.totals.totalUsers ?? 0} />
          <MetricTile label="Active users" value={props.monitor?.totals.activeUsers ?? 0} />
          <MetricTile label="Sessions" value={props.monitor?.totals.activeSessions ?? 0} />
          <MetricTile label="Mobile online" value={props.monitor?.totals.mobileOnline ?? 0} tone="green" />
          <MetricTile label="Desktop online" value={props.monitor?.totals.desktopOnline ?? 0} tone="blue" />
        </section>

        <div class="grid gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(360px,0.85fr)]">
          <section class="overflow-hidden rounded-md border border-[#d7dee8] bg-white">
            <div class="flex h-11 items-center justify-between border-b border-[#e5ebf2] px-3">
              <h2 class="text-13-semibold text-[#151b23]">Users</h2>
              <span class="text-12-regular text-[#607086]">{users().length} total</span>
            </div>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[760px] border-collapse text-left">
                <thead class="bg-[#f8fafc] text-11-medium uppercase tracking-[0.12em] text-[#607086]">
                  <tr>
                    <th class="px-3 py-2">User</th>
                    <th class="px-3 py-2">Role</th>
                    <th class="px-3 py-2">Status</th>
                    <th class="px-3 py-2">Clients</th>
                    <th class="px-3 py-2 text-right">Sessions</th>
                    <th class="px-3 py-2">Last login</th>
                    <th class="px-3 py-2">Last client log</th>
                  </tr>
                </thead>
                <tbody>
                  <For
                    each={users()}
                    fallback={
                      <tr>
                        <td class="px-3 py-8 text-center text-13-regular text-[#607086]" colSpan={7}>
                          No users
                        </td>
                      </tr>
                    }
                  >
                    {(item) => (
                      <tr
                        data-testid="server-console-user-row"
                        class="border-t border-[#edf1f6] transition-colors hover:bg-[#f8fafc]"
                        classList={{ "bg-[#edf4fb]": selectedUser()?.user.id === item.user.id }}
                      >
                        <td class="px-3 py-2">
                          <button
                            type="button"
                            class="grid max-w-[220px] text-left"
                            onClick={() => props.onSelectUser(item.user.id)}
                          >
                            <span class="truncate text-13-medium text-[#151b23]">{item.user.username}</span>
                            <span class="truncate text-11-regular text-[#607086]">{item.user.id}</span>
                          </button>
                        </td>
                        <td class="px-3 py-2">
                          <Badge tone={item.user.role === "admin" ? "blue" : "neutral"}>{item.user.role}</Badge>
                        </td>
                        <td class="px-3 py-2">
                          <Badge tone={item.user.active ? "green" : "red"}>{item.user.active ? "active" : "disabled"}</Badge>
                        </td>
                        <td class="px-3 py-2">
                          <div class="flex flex-wrap gap-1.5">
                            <Badge tone={item.clients.mobile ? "green" : "neutral"}>mobile</Badge>
                            <Badge tone={item.clients.desktop ? "blue" : "neutral"}>desktop</Badge>
                          </div>
                        </td>
                        <td class="px-3 py-2 text-right text-13-medium text-[#151b23]">{item.activeSessionCount}</td>
                        <td class="px-3 py-2 text-12-regular text-[#536173]">{formatTime(item.lastLoginAt)}</td>
                        <td class="px-3 py-2 text-12-regular text-[#536173]">{formatTime(item.lastClientLogAt)}</td>
                      </tr>
                    )}
                  </For>
                </tbody>
              </table>
            </div>
          </section>

          <section class="grid content-start gap-4">
            <UserDetail user={selectedUser()} />
            <ClientLogs logs={visibleLogs()} />
          </section>
        </div>
      </main>
    </div>
  )
}

function MetricTile(props: { label: string; value: number; tone?: "green" | "blue" }) {
  const tone = () => props.tone ?? "blue"
  return (
    <div class="rounded-md border border-[#d7dee8] bg-white px-4 py-3">
      <div class="text-11-medium uppercase tracking-[0.12em] text-[#607086]">{props.label}</div>
      <div
        class="mt-2 text-28-semibold"
        classList={{
          "text-[#245c8f]": tone() === "blue",
          "text-[#24724a]": tone() === "green",
        }}
      >
        {props.value}
      </div>
    </div>
  )
}

function UserDetail(props: { user: ConsoleUserMonitor | null }) {
  return (
    <section class="overflow-hidden rounded-md border border-[#d7dee8] bg-white" data-testid="server-console-user-detail">
      <div class="flex h-11 items-center justify-between border-b border-[#e5ebf2] px-3">
        <h2 class="text-13-semibold text-[#151b23]">Selected user</h2>
        <Show when={props.user}>
          {(item) => <Badge tone={item().clients.mobile || item().clients.desktop ? "green" : "neutral"}>presence</Badge>}
        </Show>
      </div>
      <Show
        when={props.user}
        fallback={<div class="px-3 py-8 text-center text-13-regular text-[#607086]">No user selected</div>}
      >
        {(item) => (
          <div class="grid gap-3 p-3">
            <div>
              <div class="truncate text-16-semibold text-[#151b23]">{item().user.username}</div>
              <div class="mt-1 truncate text-12-regular text-[#607086]">{item().user.id}</div>
            </div>
            <div class="grid grid-cols-2 gap-2 text-12-regular">
              <InfoCell label="Role" value={item().user.role} />
              <InfoCell label="Active sessions" value={String(item().activeSessionCount)} />
              <InfoCell label="Last login" value={formatTime(item().lastLoginAt)} />
              <InfoCell label="Last log" value={formatTime(item().lastClientLogAt)} />
            </div>
            <div>
              <div class="mb-2 text-12-medium text-[#536173]">Recent sessions</div>
              <div class="grid gap-2">
                <For
                  each={item().sessions}
                  fallback={<div class="rounded-md border border-dashed border-[#d7dee8] px-3 py-4 text-12-regular text-[#607086]">No active sessions</div>}
                >
                  {(session) => (
                    <div class="rounded-md border border-[#e5ebf2] bg-[#f8fafc] px-3 py-2">
                      <div class="flex items-center justify-between gap-3">
                        <Badge tone={session.clientKind === "mobile" ? "green" : session.clientKind === "desktop" ? "blue" : "neutral"}>
                          {session.clientKind ?? "console"}
                        </Badge>
                        <span class="text-11-regular text-[#607086]">...{session.idSuffix}</span>
                      </div>
                      <div class="mt-2 grid gap-1 text-11-regular text-[#536173]">
                        <div>Created {formatTime(session.createdAt)}</div>
                        <div>Expires {formatTime(session.expiresAt)}</div>
                        <Show when={session.userAgent}>
                          {(agent) => <div class="truncate" title={agent()}>{agent()}</div>}
                        </Show>
                      </div>
                    </div>
                  )}
                </For>
              </div>
            </div>
          </div>
        )}
      </Show>
    </section>
  )
}

function ClientLogs(props: { logs: ConsoleClientLog[] }) {
  return (
    <section class="overflow-hidden rounded-md border border-[#d7dee8] bg-white">
      <div class="flex h-11 items-center justify-between border-b border-[#e5ebf2] px-3">
        <h2 class="text-13-semibold text-[#151b23]">Client logs</h2>
        <span class="text-12-regular text-[#607086]">{props.logs.length} shown</span>
      </div>
      <div class="max-h-[420px] overflow-y-auto">
        <For
          each={props.logs.slice(0, 30)}
          fallback={<div class="px-3 py-8 text-center text-13-regular text-[#607086]">No client logs</div>}
        >
          {(log) => (
            <div class="border-t border-[#edf1f6] px-3 py-2 first:border-t-0" data-testid="server-console-client-log">
              <div class="flex items-center justify-between gap-3">
                <div class="min-w-0 truncate text-12-medium text-[#151b23]">{log.event}</div>
                <Badge tone={log.level === "error" ? "red" : log.level === "warning" ? "yellow" : "neutral"}>{log.level}</Badge>
              </div>
              <div class="mt-1 line-clamp-2 text-12-regular text-[#536173]">{log.message}</div>
              <div class="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-11-regular text-[#607086]">
                <span>{formatTime(log.createdAt)}</span>
                <Show when={log.sessionUserId}>
                  {(userId) => <span class="truncate">user {userId()}</span>}
                </Show>
              </div>
            </div>
          )}
        </For>
      </div>
    </section>
  )
}

function InfoCell(props: { label: string; value: string }) {
  return (
    <div class="rounded-md border border-[#e5ebf2] bg-[#f8fafc] px-3 py-2">
      <div class="text-10-medium uppercase tracking-[0.12em] text-[#607086]">{props.label}</div>
      <div class="mt-1 truncate text-12-medium text-[#151b23]">{props.value}</div>
    </div>
  )
}

function Badge(props: ParentProps<{ tone: "green" | "blue" | "red" | "yellow" | "neutral" }>) {
  return (
    <span
      class="inline-flex h-6 items-center rounded-full border px-2 text-11-medium"
      classList={{
        "border-[#b9dfca] bg-[#eefaf3] text-[#24724a]": props.tone === "green",
        "border-[#bed4ec] bg-[#edf4fb] text-[#245c8f]": props.tone === "blue",
        "border-[#f1c9c9] bg-[#fff2f2] text-[#8b3434]": props.tone === "red",
        "border-[#ead89a] bg-[#fff9dd] text-[#755b12]": props.tone === "yellow",
        "border-[#d7dee8] bg-[#f8fafc] text-[#536173]": props.tone === "neutral",
      }}
    >
      {props.children}
    </span>
  )
}

export function chooseSelectedUserId(current: string | null, users: ConsoleUserMonitor[]) {
  if (current && users.some((item) => item.user.id === current)) return current
  return users[0]?.user.id ?? null
}

function formatTime(value: string | null | undefined) {
  if (!value) return "-"
  const timestamp = Date.parse(value)
  if (!Number.isFinite(timestamp)) return value
  return new Intl.DateTimeFormat(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(timestamp))
}
