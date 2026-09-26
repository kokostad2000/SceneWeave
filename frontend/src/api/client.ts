/**
 * HTTP 客户端。
 *
 * 类型全部来自后端 OpenAPI 生成产物（`./generated/schema.d.ts`），前端不手写
 * 重复的请求／响应结构或枚举（PRD 第 8 节）。
 *
 * 本模块是**唯一**发起 HTTP 请求的地方；SSE 订阅在 `useSceneStream` 中。
 */

import type { components } from './generated/schema'

export type HealthResponse = components['schemas']['HealthResponse']
export type ContractSummary = components['schemas']['ContractSummary']
export type ApiErrorBody = components['schemas']['ApiError']

export type AgentTemplate = components['schemas']['AgentTemplate']
export type AgentSnapshot = components['schemas']['AgentSnapshot']
export type SceneAgent = components['schemas']['SceneAgent']
export type Scene = components['schemas']['Scene']
export type SceneDetailView = components['schemas']['SceneDetailView']
export type SceneListView = components['schemas']['SceneListView']
export type SceneSummaryView = components['schemas']['SceneSummaryView']
export type TemplateListView = components['schemas']['TemplateListView']
export type PresetListView = components['schemas']['PresetListView']
export type PresetSummaryView = components['schemas']['PresetSummaryView']
export type CommandAck = components['schemas']['CommandAck']
export type TimelineView = components['schemas']['TimelineView']
export type TimelineEntryView = components['schemas']['TimelineEntryView']
export type RunStateView = components['schemas']['RunStateView']
export type ViewpointView = components['schemas']['ViewpointView']
export type EventView = components['schemas']['EventView']
export type ScenarioSummaryView = components['schemas']['ScenarioSummaryView']
export type AgentStatusListView = components['schemas']['AgentStatusListView']
export type AnalysisRecordView = components['schemas']['AnalysisRecordView']
export type AnalysisListView = components['schemas']['AnalysisListView']
export type AnalysisCapabilityView = components['schemas']['AnalysisCapabilityView']
export type Message = components['schemas']['Message']
export type StoryEvent = components['schemas']['Event']

export type RunState = components['schemas']['RunState']
export type PauseReason = components['schemas']['PauseReason']
export type EventStatus = components['schemas']['EventStatus']
export type EventVisibility = components['schemas']['EventVisibility']
export type ControlCommandType = components['schemas']['ControlCommandType']

/** 后端基地址。默认留空，由 Vite dev server 把 `/api` 代理到 127.0.0.1:8000。 */
export const API_BASE = import.meta.env.VITE_API_BASE ?? ''

/** 请求失败时抛出；保留状态码与后端错误体，便于界面区分不同失败。 */
export class ApiRequestError extends Error {
  readonly status: number
  readonly body: ApiErrorBody | null

  constructor(status: number, message: string, body: ApiErrorBody | null = null) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
    this.body = body
  }
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { Accept: 'application/json', ...(init.headers ?? {}) },
    signal,
  })

  if (!response.ok) {
    let body: ApiErrorBody | null = null
    try {
      body = (await response.json()) as ApiErrorBody
    } catch {
      body = null
    }
    throw new ApiRequestError(
      response.status,
      body?.detail ? `请求失败：${body.detail}` : `请求 ${path} 失败（HTTP ${response.status}）`,
      body,
    )
  }

  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

function jsonBody(payload: unknown, method = 'POST'): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }
}

// --- M00 健康检查与契约自检 ---

export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return requestJson<HealthResponse>('/api/health', {}, signal)
}

export function fetchContractSummary(signal?: AbortSignal): Promise<ContractSummary> {
  return requestJson<ContractSummary>('/api/contracts/summary', {}, signal)
}

// --- M01 角色模板与场景配置 ---

export function listTemplates(signal?: AbortSignal): Promise<TemplateListView> {
  return requestJson<TemplateListView>('/api/templates', {}, signal)
}

export function createTemplate(
  payload: components['schemas']['TemplateCreateRequest'],
): Promise<AgentTemplate> {
  return requestJson<AgentTemplate>('/api/templates', jsonBody(payload))
}

export function updateTemplate(
  templateId: string,
  payload: components['schemas']['TemplateUpdateRequest'],
): Promise<AgentTemplate> {
  return requestJson<AgentTemplate>(`/api/templates/${templateId}`, jsonBody(payload, 'PATCH'))
}

export function copyTemplate(templateId: string, name?: string): Promise<AgentTemplate> {
  return requestJson<AgentTemplate>(
    `/api/templates/${templateId}/copy`,
    jsonBody(name ? { name } : {}),
  )
}

export function deleteTemplate(templateId: string): Promise<void> {
  return requestJson<void>(`/api/templates/${templateId}`, { method: 'DELETE' })
}

export function listScenes(signal?: AbortSignal): Promise<SceneListView> {
  return requestJson<SceneListView>('/api/scenes', {}, signal)
}

export function listPresets(signal?: AbortSignal): Promise<PresetListView> {
  return requestJson<PresetListView>('/api/scenes/presets', {}, signal)
}

export function getScene(sceneId: string, signal?: AbortSignal): Promise<SceneDetailView> {
  return requestJson<SceneDetailView>(`/api/scenes/${sceneId}`, {}, signal)
}

export function createScene(
  payload: components['schemas']['SceneCreateRequest'],
): Promise<SceneDetailView> {
  return requestJson<SceneDetailView>('/api/scenes', jsonBody(payload))
}

export function createPresetScene(presetKey = 'roommates'): Promise<SceneDetailView> {
  return requestJson<SceneDetailView>('/api/scenes/preset', jsonBody({ preset_key: presetKey }))
}

export function addAgent(
  sceneId: string,
  payload: components['schemas']['AgentCreateRequest'],
): Promise<SceneAgent> {
  return requestJson<SceneAgent>(`/api/scenes/${sceneId}/agents`, jsonBody(payload))
}

export function renameAgent(sceneId: string, agentId: string, name: string): Promise<SceneAgent> {
  return requestJson<SceneAgent>(
    `/api/scenes/${sceneId}/agents/${agentId}`,
    jsonBody({ name }, 'PATCH'),
  )
}

export function removeAgent(sceneId: string, agentId: string): Promise<void> {
  return requestJson<void>(`/api/scenes/${sceneId}/agents/${agentId}`, { method: 'DELETE' })
}

// --- M04 运行控制、事件与观察 ---

export function sendCommand(
  sceneId: string,
  requestId: string,
  command: ControlCommandType,
): Promise<CommandAck> {
  return requestJson<CommandAck>(
    `/api/scenes/${sceneId}/commands`,
    jsonBody({ request_id: requestId, command }),
  )
}

export function injectEvent(
  sceneId: string,
  payload: {
    request_id: string
    body: string
    visibility: EventVisibility
    target_agent_id?: string | null
  },
): Promise<CommandAck> {
  return requestJson<CommandAck>(`/api/scenes/${sceneId}/events`, jsonBody(payload))
}

export function fetchTimeline(sceneId: string, signal?: AbortSignal): Promise<TimelineView> {
  return requestJson<TimelineView>(`/api/scenes/${sceneId}/timeline`, {}, signal)
}

export function fetchRunState(sceneId: string, signal?: AbortSignal): Promise<RunStateView> {
  return requestJson<RunStateView>(`/api/scenes/${sceneId}/state`, {}, signal)
}

export function fetchEvents(sceneId: string, signal?: AbortSignal): Promise<EventView[]> {
  return requestJson<EventView[]>(`/api/scenes/${sceneId}/events`, {}, signal)
}

export function fetchSummary(sceneId: string, signal?: AbortSignal): Promise<ScenarioSummaryView> {
  return requestJson<ScenarioSummaryView>(`/api/scenes/${sceneId}/summary`, {}, signal)
}

export function fetchViewpoint(
  sceneId: string,
  agentId: string,
  signal?: AbortSignal,
): Promise<ViewpointView> {
  return requestJson<ViewpointView>(
    `/api/scenes/${sceneId}/agents/${agentId}/viewpoint`,
    {},
    signal,
  )
}

/** 每个本场角色的执行状态（只读观察，PRD 7.1）。 */
export function fetchAgentStatus(
  sceneId: string,
  signal?: AbortSignal,
): Promise<AgentStatusListView> {
  return requestJson<AgentStatusListView>(`/api/scenes/${sceneId}/agents/status`, {}, signal)
}

// --- M06 行为分析（只读观察） ---

export function createAnalysis(
  sceneId: string,
  payload: { agent_id: string; material_seqs: number[] },
): Promise<AnalysisRecordView> {
  return requestJson<AnalysisRecordView>(`/api/scenes/${sceneId}/analyses`, jsonBody(payload))
}

export function listAnalyses(sceneId: string, signal?: AbortSignal): Promise<AnalysisListView> {
  return requestJson<AnalysisListView>(`/api/scenes/${sceneId}/analyses`, {}, signal)
}

export function fetchAnalysisCapability(
  sceneId: string,
  signal?: AbortSignal,
): Promise<AnalysisCapabilityView> {
  return requestJson<AnalysisCapabilityView>(
    `/api/scenes/${sceneId}/analyses/capability`,
    {},
    signal,
  )
}

/** SSE 订阅地址：追赶从 `since_seq` 开始，支持断线重连与去重。 */
export function streamUrl(sceneId: string, sinceSeq: number): string {
  return `${API_BASE}/api/scenes/${sceneId}/stream?since_seq=${sinceSeq}`
}

/** 生成幂等命令 ID（重放同一 ID 不会新增模型请求）。 */
export function newRequestId(prefix: string): string {
  const random =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : Math.random().toString(16).slice(2)
  return `${prefix}-${random}`
}
