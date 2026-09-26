/**
 * 聊天页 / 历史页（PRD 7.1、7.2、5.4）。
 *
 * - 时间线为主体，角色信息侧栏按需展开，底部保留运行控制；
 * - `readOnly` 模式供历史页复用：**只读取已保存数据，不调用模型**；
 * - 收到 SSE 提交后只刷新视图：页面刷新不重启任务，浏览器断开不停止后台场景。
 */

import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  createPresetScene,
  fetchAgentStatus,
  fetchEvents,
  fetchRunState,
  fetchSummary,
  fetchTimeline,
  getScene,
  type EventView,
  type RunStateView,
  type SceneDetailView,
  type ScenarioSummaryView,
  type TimelineEntryView,
  type AgentStatusListView,
  type TimelineView,
} from '../api/client'
import { AnalysisDrawer } from '../components/AnalysisDrawer'
import { ControlBar } from '../components/ControlBar'
import { RoleSidebar } from '../components/RoleSidebar'
import { TimelineList } from '../components/TimelineList'
import { ViewpointPanel } from '../components/ViewpointPanel'
import { useSceneStream } from '../hooks/useSceneStream'
import { pauseReasonLabel, runStateLabel, runStateTone } from '../lib/labels'

export interface ChatViewProps {
  readonly sceneId: string | null
  readonly readOnly?: boolean
  readonly modelConfigured: boolean | null
  readonly onSelectScene: (sceneId: string) => void
}

export function ChatView({ sceneId, readOnly = false, modelConfigured, onSelectScene }: ChatViewProps) {
  const [detail, setDetail] = useState<SceneDetailView | null>(null)
  const [timeline, setTimeline] = useState<TimelineView | null>(null)
  const [state, setState] = useState<RunStateView | null>(null)
  const [events, setEvents] = useState<EventView[]>([])
  const [summary, setSummary] = useState<ScenarioSummaryView | null>(null)
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const stream = useSceneStream(readOnly ? null : sceneId, 0)
  const agentStatus = useAgentStatus(sceneId, stream.entries.length)

  const reload = useCallback(async () => {
    if (sceneId === null) {
      setDetail(null)
      setTimeline(null)
      setState(null)
      setEvents([])
      return
    }
    const [sceneDetail, sceneTimeline, sceneState, sceneEvents, sceneSummary] = await Promise.all([
      getScene(sceneId),
      fetchTimeline(sceneId),
      fetchRunState(sceneId),
      fetchEvents(sceneId),
      fetchSummary(sceneId),
    ])
    setDetail(sceneDetail)
    setTimeline(sceneTimeline)
    setState(sceneState)
    setEvents(sceneEvents)
    setSummary(sceneSummary)
  }, [sceneId])

  useEffect(() => {
    setError(null)
    reload().catch((cause: unknown) => setError(cause instanceof Error ? cause.message : String(cause)))
  }, [reload])

  // SSE 有新条目时刷新一次状态（不重启任何任务）。
  useEffect(() => {
    if (stream.entries.length === 0) return
    reload().catch(() => undefined)
  }, [stream.entries.length, reload])

  const entries: TimelineEntryView[] = useMemo(() => {
    const bySeq = new Map<number, TimelineEntryView>()
    for (const entry of timeline?.entries ?? []) {
      bySeq.set(entry.seq, entry)
    }
    for (const entry of stream.entries) {
      bySeq.set(entry.seq, entry)
    }
    return [...bySeq.values()].sort((a, b) => a.seq - b.seq)
  }, [timeline, stream.entries])

  const pendingEvents = events.filter((item) => item.status === 'ACCEPTED')
  const requestedAgentId = useMemo(() => {
    const messages = entries.filter((entry) => entry.kind === 'message' && entry.message)
    if (messages.length === 0) return null
    return messages[messages.length - 1]?.message?.requested_speaker_id ?? null
  }, [entries])
  const requestedAgentName = useMemo(
    () => detail?.agents.find((agent) => agent.agent_id === requestedAgentId)?.name ?? null,
    [detail, requestedAgentId],
  )

  async function createDemoScene() {
    setError(null)
    try {
      const created = await createPresetScene()
      onSelectScene(created.scene.scene_id)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    }
  }

  if (sceneId === null) {
    return (
      <div className="view">
        <section className="card">
          <h2>还没有打开会话</h2>
          <p className="hint">可以先用预置“三个室友的客厅”创建一个会话，或在配置页创建。</p>
          <button type="button" onClick={createDemoScene}>
            用预置场景创建会话
          </button>
        </section>
      </div>
    )
  }

  return (
    <div className="view view--chat">
      <header className="chat__header">
        <h2>{detail?.scene.title ?? '加载中…'}</h2>
        <span className={`state ${state ? runStateTone(state.status) : ''}`}>
          {state ? runStateLabel(state.status) : '—'}
        </span>
        {state?.pause_reason ? (
          <span className="state state--reason">停止原因：{pauseReasonLabel(state.pause_reason)}</span>
        ) : null}
        {readOnly ? <span className="tag">历史（只读）</span> : null}
        {modelConfigured === false ? (
          <span className="state state--mock" data-testid="mock-badge">
            模拟模式：未配置模型凭证，当前为确定性 Mock，不代表真实模型输出
          </span>
        ) : null}
        {stream.error && !readOnly ? <span className="hint">{stream.error}</span> : null}
      </header>

      {error ? <p className="state state--error">{error}</p> : null}

      <div className="chat__body">
        <main className="chat__main">
          <TimelineList entries={entries} requestedAgentName={requestedAgentName} />
          {pendingEvents.length > 0 ? (
            <section className="card">
              <h3>待生效事件（调用结束后按接受顺序生效）</h3>
              <ul>
                {pendingEvents.map((item) => (
                  <li key={item.event.event_id}>#{item.event.seq ?? '待定'} {item.event.body}</li>
                ))}
              </ul>
            </section>
          ) : null}
        </main>

        <RoleSidebar
          agents={detail?.agents ?? []}
          status={agentStatus}
          selectedAgentId={selectedAgentId}
          onSelect={(agentId) => setSelectedAgentId(agentId === selectedAgentId ? null : agentId)}
        />
      </div>

      {detail ? (
        <section className="card">
          <h3>本场角色（快照）</h3>
          <ul className="snapshot-list">
            {detail.agents.map((agent) => (
              <li key={agent.agent_id}>
                <b>{agent.name}</b>
                <span className="hint">
                  模板「{agent.snapshot.name}」，私有背景 {agent.snapshot.private_background === '' ? '（未设定）' : '已设定'}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {summary ? (
        <p className="hint" data-testid="call-counts">
          实际调用计数：成功 {summary.succeeded}／失败 {summary.failed}／结果不明 {summary.unknown}
          （上限 {summary.max_role_requests}）
          {summary.last_failure_kind ? `；最近一次失败：${summary.last_failure_kind}` : ''}
        </p>
      ) : null}

      {selectedAgentId && sceneId ? (
        <ViewpointPanel
          sceneId={sceneId}
          agentId={selectedAgentId}
          agentName={detail?.agents.find((agent) => agent.agent_id === selectedAgentId)?.name ?? ''}
        />
      ) : null}

      {readOnly ? (
        <p className="hint">历史模式只读取已保存数据，不调用模型，也不提供运行控制。</p>
      ) : state ? (
        <ControlBar
          sceneId={sceneId}
          state={state}
          agents={detail?.agents ?? []}
          onChanged={() => {
            reload().catch(() => undefined)
          }}
          onError={setError}
        />
      ) : null}

      <div className="chat__drawer-toggle">
        <button type="button" onClick={() => setDrawerOpen(true)}>
          打开行为分析抽屉
        </button>
      </div>

      <AnalysisDrawer
        open={drawerOpen}
        sceneId={sceneId}
        agents={detail?.agents ?? []}
        entries={entries}
        onClose={() => setDrawerOpen(false)}
        onError={setError}
      />
    </div>
  )
}

/** 读取角色执行状态（只读观察接口；有新提交时刷新一次）。 */
function useAgentStatus(
  sceneId: string | null,
  revision: number,
): AgentStatusListView | null {
  const [status, setStatus] = useState<AgentStatusListView | null>(null)

  useEffect(() => {
    if (sceneId === null) {
      setStatus(null)
      return
    }
    const controller = new AbortController()
    fetchAgentStatus(sceneId, controller.signal)
      .then(setStatus)
      .catch(() => undefined)
    return () => controller.abort()
  }, [sceneId, revision])

  return status
}
