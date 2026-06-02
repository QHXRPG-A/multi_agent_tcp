const config = window.__GULICODE_BP__ || {}

const state = {
  blueprints: [],
  document: null,
  runId: "",
}

const $ = (id) => document.getElementById(id)

function pretty(value) {
  return JSON.stringify(value, null, 2)
}

function setStatus(text, error = false) {
  const node = $("connection-status")
  node.textContent = text
  node.classList.toggle("error", error)
}

function setResult(value) {
  $("last-result").textContent = typeof value === "string" ? value : pretty(value)
}

function defaultPlanForDocument(documentValue = state.document) {
  const agents = documentValue?.graph?.agent_nodes || {}
  const nodeIds = Object.keys(agents)
  const startNodes = Array.isArray(documentValue?.graph?.start_nodes) && documentValue.graph.start_nodes.length
    ? documentValue.graph.start_nodes
    : nodeIds
  const tasks = {}
  const descriptions = {}
  for (const nodeId of nodeIds) {
    const agent = agents[nodeId] || {}
    descriptions[nodeId] = agent.description || agent.prompt || `Agent ${nodeId}`
    tasks[nodeId] = {
      goal: agent.prompt || `Run ${nodeId}.`,
      expected_output: "A concise result.",
      acceptance: "The task is complete.",
    }
  }
  return {
    user_goal: "Run the selected blueprint.",
    agent_descriptions: descriptions,
    start_nodes: startNodes,
    tasks,
    run_policy: {},
  }
}

function setDefaultPlan(documentValue = state.document) {
  $("plan-editor").value = pretty(defaultPlanForDocument(documentValue))
}

function activeProjectDir() {
  return $("project-dir").value.trim()
}

function activeBlueprintId() {
  return $("blueprint-id").value || config.blueprintId || "default"
}

function activeRunId() {
  return $("run-id").value.trim() || state.runId
}

async function api(command, args = {}) {
  const response = await fetch("/api/blueprint", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      token: config.token,
      command,
      args,
    }),
  })
  const payload = await response.json()
  if (!response.ok || payload.ok === false) {
    const message = payload.error || `request failed: ${command}`
    const error = new Error(payload.code ? `${payload.code}: ${message}` : message)
    error.payload = payload
    throw error
  }
  return payload
}

async function runAction(label, fn) {
  try {
    setStatus(`${label}...`)
    const result = await fn()
    setStatus("Ready")
    setResult(result)
    return result
  } catch (error) {
    setStatus(error.message || String(error), true)
    setResult(error.payload || String(error))
    throw error
  }
}

function renderBlueprints() {
  const select = $("blueprint-id")
  select.innerHTML = ""
  for (const item of state.blueprints) {
    const option = document.createElement("option")
    option.value = item.id || "default"
    option.textContent = item.name ? `${item.name} (${option.value})` : option.value
    select.append(option)
  }
  if (!state.blueprints.length) {
    const option = document.createElement("option")
    option.value = config.blueprintId || "default"
    option.textContent = option.value
    select.append(option)
  }
}

function renderRuns(runs) {
  const root = $("runs")
  root.innerHTML = ""
  for (const run of runs || []) {
    const button = document.createElement("button")
    button.type = "button"
    button.className = "list-item"
    button.innerHTML = `<span class="list-title">${run.runId || run.run_id || "run"}</span><span class="list-meta">${run.status || run.executionMode || ""}</span>`
    button.addEventListener("click", () => {
      const runId = run.runId || run.run_id || ""
      state.runId = runId
      $("run-id").value = runId
    })
    root.append(button)
  }
}

async function loadBlueprints() {
  const projectDir = activeProjectDir()
  const result = await runAction("Loading blueprints", () => api("blueprint.list", { projectDir }))
  state.blueprints = result.blueprints || []
  renderBlueprints()
  return result
}

async function openBlueprint() {
  const projectDir = activeProjectDir()
  const blueprintId = activeBlueprintId()
  const result = await runAction("Opening blueprint", () => api("blueprint.open", { projectDir, blueprintId }))
  state.document = result.document
  $("document-editor").value = pretty(result.document)
  setDefaultPlan(result.document)
  return result
}

async function saveBlueprint() {
  const projectDir = activeProjectDir()
  const document = JSON.parse($("document-editor").value)
  const result = await runAction("Saving blueprint", () => api("blueprint.save", { projectDir, document }))
  state.document = result.document
  $("document-editor").value = pretty(result.document)
  return result
}

async function validateBlueprint() {
  const projectDir = activeProjectDir()
  const blueprintId = activeBlueprintId()
  const text = $("document-editor").value.trim()
  const document = text ? JSON.parse(text) : undefined
  const result = await runAction("Validating blueprint", () =>
    api("blueprint.validate", { projectDir, blueprintId, document }),
  )
  $("status-view").textContent = pretty(result)
  activateTab("status")
  return result
}

async function listRuns() {
  const projectDir = activeProjectDir()
  const blueprintId = activeBlueprintId()
  const result = await runAction("Listing runs", () => api("blueprint.listRuns", { projectDir, blueprintId }))
  renderRuns(result.runs || [])
  return result
}

async function startRun(executionMode) {
  const projectDir = activeProjectDir()
  const blueprintId = activeBlueprintId()
  const plan = JSON.parse($("plan-editor").value || "{}")
  const result = await runAction("Starting run", () =>
    api("blueprint.start", { projectDir, blueprintId, plan, executionMode }),
  )
  state.runId = result.runId || result.run_id || result.id || ""
  if (state.runId) $("run-id").value = state.runId
  $("status-view").textContent = pretty(result)
  activateTab("status")
  return result
}

async function refreshStatus() {
  const runId = activeRunId()
  const result = await runAction("Reading status", () => api("blueprint.status", { runId }))
  $("status-view").textContent = pretty(result)
  activateTab("status")
  return result
}

async function refreshEvents() {
  const runId = activeRunId()
  const result = await runAction("Reading events", () => api("blueprint.recentEvents", { runId, limit: 50 }))
  $("events-view").textContent = pretty(result)
  activateTab("events")
  return result
}

async function refreshDiff() {
  const runId = activeRunId()
  const result = await runAction("Reading diff", () => api("blueprint.runDiff", { runId }))
  $("diff-view").textContent = pretty(result)
  activateTab("diff")
  return result
}

async function endRun(action) {
  const runId = activeRunId()
  const result = await runAction("Ending run", () => api("blueprint.end", { runId, action }))
  $("status-view").textContent = pretty(result)
  activateTab("status")
  return result
}

async function agentInfo() {
  const nodeId = $("node-id").value.trim()
  const runId = activeRunId()
  const result = await runAction("Reading agent info", () => api("blueprint.agentInfo", { runId, nodeId }))
  $("status-view").textContent = pretty(result)
  activateTab("status")
  return result
}

async function queueMessage() {
  const runId = activeRunId()
  const nodeId = $("node-id").value.trim()
  const text = $("agent-message").value
  return runAction("Queueing message", () =>
    api("blueprint.queueAgentMessage", { runId, nodeId, text, mode: "default" }),
  )
}

function activateTab(name) {
  for (const tab of document.querySelectorAll(".tab")) {
    tab.classList.toggle("active", tab.dataset.tab === name)
  }
  for (const panel of document.querySelectorAll("[data-tab-panel]")) {
    panel.classList.toggle("hidden", panel.dataset.tabPanel !== name)
  }
}

function bind() {
  $("project-dir").value = config.projectDir || ""
  setDefaultPlan()
  renderBlueprints()

  $("load-blueprints").addEventListener("click", () => void loadBlueprints())
  $("open-blueprint").addEventListener("click", () => void openBlueprint())
  $("save-blueprint").addEventListener("click", () => void saveBlueprint())
  $("validate-blueprint").addEventListener("click", () => void validateBlueprint())
  $("refresh-runs").addEventListener("click", () => {
    const actions = [listRuns()]
    if (activeRunId()) actions.push(refreshStatus())
    void Promise.allSettled(actions)
  })
  $("list-runs").addEventListener("click", () => void listRuns())
  $("start-live").addEventListener("click", () => void startRun("live"))
  $("start-status").addEventListener("click", () => void startRun("status"))
  $("run-status").addEventListener("click", () => void refreshStatus())
  $("run-events").addEventListener("click", () => void refreshEvents())
  $("run-diff").addEventListener("click", () => void refreshDiff())
  $("run-complete").addEventListener("click", () => void endRun("complete"))
  $("run-cancel").addEventListener("click", () => void endRun("cancel"))
  $("agent-info").addEventListener("click", () => void agentInfo())
  $("queue-message").addEventListener("click", () => void queueMessage())

  for (const tab of document.querySelectorAll(".tab")) {
    tab.addEventListener("click", () => activateTab(tab.dataset.tab))
  }

  if (config.projectDir) {
    void loadBlueprints()
  }
}

bind()
