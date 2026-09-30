/**
 * 聊天页 / 历史页（PRD 7.1、7.2、5.4）。
 *
 * - 时间线为主体，角色信息侧栏按需展开，底部保留运行控制；
 * - `readOnly` 模式供历史页复用：**只读取已保存数据，不调用模型**；
 * - 收到 SSE 提交后只刷新视图：页面刷新不重启任务，浏览器断开不停止后台场景。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

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
  fetchStatistics,
  type FactStatisticsView,
  updateAgentProfile,
  type SceneRoleProfile,
  type DiscussionParticipantConfig,
} from '../api/client'
import { RoleProfileEditor, emptyRoleProfile, profileFromSnapshot, roleProfileOverLimit } from '../components/RoleProfileEditor'
import { codepointLimits } from '../api/contracts'
import { trimmedCodepointLength } from '../lib/codepoints'
import { AnalysisDrawer } from '../components/AnalysisDrawer'
import { RecordFacts } from '../components/RecordFacts'
import { modeLabel } from '../lib/modes'
import { ConversationMenu } from '../components/ConversationMenu'
import { readView, saveView } from '../lib/viewState'
import { actionLabel } from '../lib/actions'
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
  const [facts, setFacts] = useState<FactStatisticsView | null>(null)
  const [factsUnavailable, setFactsUnavailable] = useState(false)
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(() => { const saved = readView<unknown>(`viewer:${sceneId}`, null); return typeof saved === 'string' ? saved : null })
  const [channel, setChannel] = useState('all')
  const [dataKey, setDataKey] = useState('')
  const key = `${sceneId}:${selectedAgentId ?? 'observer'}`
  const currentKey = useRef(key)
  currentKey.current = key
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editingAgentId, setEditingAgentId] = useState<string | null>(null)
  const [profileDraft, setProfileDraft] = useState<SceneRoleProfile>(emptyRoleProfile)
  const [discussionDraft, setDiscussionDraft] = useState<DiscussionParticipantConfig>({ focus: '', initial_position: null })
  const [savingProfile, setSavingProfile] = useState(false)

  const stream = useSceneStream(readOnly || selectedAgentId ? null : sceneId, 0)
  const [agentStatus, setAgentStatus] = useState<AgentStatusListView | null>(null)

  const reload = useCallback(async () => {
    if (sceneId === null) {
      setDetail(null)
      setTimeline(null)
      setState(null)
      setEvents([])
      return
    }
    const [sceneDetail, sceneTimeline, sceneState, sceneEvents, sceneSummary, sceneAgentStatus] = await Promise.all([
      getScene(sceneId),
      fetchTimeline(sceneId, undefined, selectedAgentId),
      fetchRunState(sceneId),
      fetchEvents(sceneId, undefined, selectedAgentId),
      selectedAgentId ? Promise.resolve(null) : fetchSummary(sceneId),
      fetchAgentStatus(sceneId, undefined, selectedAgentId),
    ])
    if (currentKey.current !== key) return
    setDataKey(key)
    setDetail(sceneDetail)
    setTimeline(sceneTimeline)
    setState(sceneState)
    setEvents(sceneEvents)
    setSummary(sceneSummary)
    setAgentStatus(sceneAgentStatus)
    try {
      const value = await fetchStatistics(sceneId, undefined, selectedAgentId)
      if (currentKey.current === key) { setFacts(value); setFactsUnavailable(false) }
    } catch {
      if (currentKey.current === key) { setFacts(null); setFactsUnavailable(true) }
    }
  }, [sceneId, selectedAgentId, key])

  useEffect(() => {
    setError(null)
    setEditingAgentId(null)
    setTimeline(null)
    setFacts(null)
    setFactsUnavailable(false)
    setEvents([])
    const saved = readView<unknown>(`channel:${key}`, 'all')
    setChannel(typeof saved === 'string' ? saved : 'all')
    saveView(`viewer:${sceneId}`, selectedAgentId)
    setDrawerOpen(false)
    reload().catch((cause: unknown) => setError(cause instanceof Error ? cause.message : String(cause)))
  }, [reload])

  // SSE 有新条目时刷新一次状态（不重启任何任务）。
  useEffect(() => {
    if (stream.entries.length === 0) return
    reload().catch(() => undefined)
  }, [stream.entries.length, reload])

  // 角色模式只读后端过滤结果；轮询同时刷新 PASS／失败和生成状态。
  useEffect(() => {
    if (readOnly || !sceneId) return
    const timer = window.setInterval(() => { reload().catch(() => undefined) }, 1500)
    return () => window.clearInterval(timer)
  }, [reload, readOnly, sceneId])

  const entries: TimelineEntryView[] = useMemo(() => {
    if (dataKey !== key) return []
    const bySeq = new Map<number, TimelineEntryView>()
    for (const entry of timeline?.entries ?? []) {
      bySeq.set(entry.seq, entry)
    }
    for (const entry of selectedAgentId ? [] : stream.entries) {
      bySeq.set(entry.seq, entry)
    }
    return [...bySeq.values()].sort((a, b) => a.seq - b.seq)
  }, [timeline, stream.entries, selectedAgentId, dataKey, key])

  const names = new Map((detail?.agents ?? []).map(a => [a.agent_id, a.name]))
  const conversations = dataKey === key ? timeline?.conversations ?? [] : []
  const currentConversation = conversations.find(c => c.conversation_id === channel)
  const shownEntries = entries.filter(e => channel === 'all' || (channel === 'public'
    ? (e.message ? e.message.visibility !== 'PRIVATE' : e.event?.visibility === 'ALL')
    : e.message?.conversation_id === channel))
  // 操作者事件遵守频道范围，定向事件不进入公共频道，任何事件都不进入私聊。
  const pendingEvents = (dataKey === key ? events : []).filter((item) => item.status === 'ACCEPTED'
    && (channel === 'all' || (channel === 'public' && item.event.visibility === 'ALL')))
  const requestedAgentId = useMemo(() => {
    const messages = entries.filter((entry) => entry.kind === 'message' && entry.message)
    if (messages.length === 0) return null
    return selectedAgentId ? null : messages[messages.length - 1]?.message?.recipient_id ?? messages[messages.length - 1]?.message?.requested_speaker_id ?? null
  }, [entries, selectedAgentId])
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
          <p className="hint">{readOnly ? '请选择已有历史会话。' : '可以先用预置“三个室友的客厅”创建一个会话，或在配置页创建。'}</p>
          {!readOnly ? (
          <button type="button" onClick={createDemoScene}>
            用预置场景创建会话
          </button>
          ) : null}
        </section>
      </div>
    )
  }

  return (
    <div className="view view--chat">
      <header className="chat__header">
        <h2>{detail?.scene.title ?? '加载中…'}</h2>
        {detail ? <span className="tag">{modeLabel[detail.scene.mode ?? 'simulation']}</span> : null}
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

      {detail && dataKey === key ? <section className="card" aria-label="场景信息">
        <h3>{detail.scene.mode === 'discussion' ? '议题与材料' : '情境与公共信息'}</h3>
        {detail.scene.mode === 'discussion' && detail.scene.mode_config && 'topic' in detail.scene.mode_config ? <>
          <p>议题：{detail.scene.mode_config.topic}</p><p>背景／材料：{detail.scene.mode_config.materials || '（未提供）'}</p>
        </> : <p>{detail.scene.background || '（未提供）'}</p>}
        <p className="hint">全场公开 · 模式在创建时固定</p>
        <p className="hint">{detail.scene.chat_policy_version === 2
          ? '自由续聊 · 每条最多 1000 码点 · 全员沉默后暂停'
          : '旧版规则 · 每条最多 200 码点 · 无新信息时暂停'}</p>
      </section> : null}

      <div className="perspective-bar">
        <button type="button" onClick={() => setSelectedAgentId(null)} aria-pressed={selectedAgentId === null}>观察者视角</button>
        <span>{selectedAgentId ? `角色视角：${names.get(selectedAgentId) ?? ''} · 仅本人可见材料` : '观察全场'}</span>
      </div>
      <div className="chat__body">
        <ConversationMenu conversations={conversations} channel={channel} onSelect={value => { setChannel(value); saveView(`channel:${key}`, value) }} />
        <main className="chat__main">
          <h3>{channel === 'public' ? '公共频道' : channel === 'all' ? (selectedAgentId ? '本人可见时间线' : '全场时间线') : currentConversation?.participant_names.join(' ↔ ') ?? '会话已切换'}</h3>
          {currentConversation ? <p className="hint">仅双方可见</p> : null}
          <div key={`${key}:${channel}`} className="chat__messages" role="region" aria-label="频道消息" tabIndex={0}>
            <TimelineList entries={shownEntries} requestedAgentName={requestedAgentName} names={names} />
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
          </div>
        </main>

        <RoleSidebar
          agents={dataKey === key ? detail?.agents ?? [] : []}
          status={dataKey === key ? agentStatus : null}
          selectedAgentId={selectedAgentId}
          viewerId={selectedAgentId}
          onSelect={(agentId) => setSelectedAgentId(agentId === selectedAgentId ? null : agentId)}
        />
      </div>

      {detail && dataKey === key ? (
        <section className="card">
          <h3>本场角色（快照）</h3>
          <p className="hint">{(detail.scene.configuration_version ?? 1) === 2
            ? '本场设定独立保存，人物目录变更不会带入；首次角色请求后锁定。'
            : '旧版会话保留原模板快照；更换设定请新建场景，旧聊天历史仍会影响后续对话。'}</p>
          <ul className="snapshot-list">
            {detail.agents.filter(a => !selectedAgentId || a.agent_id === selectedAgentId).map((agent) => (
              <li key={agent.agent_id}>
                <b>{agent.name}</b>
                <details><summary>私人配置（仅本人及本机观察者可检查）</summary>
                  <p>人物设定：{agent.snapshot.persona || '（未提供）'}</p>
                  <p>表达习惯：{agent.snapshot.speech_style || '（未提供）'}</p>
                  <p>初始目标：{agent.snapshot.initial_goal || '（未提供）'}</p>
                  <p>私有背景：{agent.snapshot.private_background || '（未提供）'}</p>
                  {agent.discussion_config ? <><p>讨论关注点：{agent.discussion_config.focus || '（未提供）'}</p>
                    <p>初始观点（可调整）：{agent.discussion_config.initial_position || '未预设立场'}</p></> : null}
                </details>
                <span className="hint">
                  来源人物「{agent.snapshot.name}」，私有背景 {agent.snapshot.private_background === '' ? '（未设定）' : '已设定'}
                </span>
                {!readOnly && !selectedAgentId && !detail.locked && detail.scene.status === 'READY' && detail.scene.configuration_version === 2 ? <>
                  <button type="button" onClick={() => {
                    setEditingAgentId(agent.agent_id)
                    setProfileDraft(profileFromSnapshot(agent.snapshot))
                    setDiscussionDraft(agent.discussion_config ?? { focus: '', initial_position: null })
                  }}>编辑{agent.name}的本场设定</button>
                  {editingAgentId === agent.agent_id ? <div>
                    <RoleProfileEditor name={agent.name} value={profileDraft} onChange={setProfileDraft} />
                    {detail.scene.mode === 'discussion' ? <div className="grid">
                      <label className="field"><span>讨论关注点 · 仅本人可见</span><textarea aria-label={`${agent.name}的本场讨论关注点`}
                        value={discussionDraft.focus ?? ''} onChange={e => setDiscussionDraft(prev => ({ ...prev, focus: e.target.value }))} /></label>
                      <label className="field"><span>初始观点 · 可空、可调整、仅本人可见</span><textarea aria-label={`${agent.name}的本场初始观点`}
                        value={discussionDraft.initial_position ?? ''} onChange={e => setDiscussionDraft(prev => ({ ...prev, initial_position: e.target.value || null }))} /></label>
                    </div> : null}
                    <button type="button" disabled={savingProfile} onClick={async () => {
                      setError(null)
                      if (roleProfileOverLimit(profileDraft) || trimmedCodepointLength(discussionDraft.focus ?? '') > codepointLimits.discussion_focus || trimmedCodepointLength(discussionDraft.initial_position ?? '') > codepointLimits.initial_position) {
                        setError('本场设定超过码点上限'); return
                      }
                      setSavingProfile(true)
                      try {
                        await updateAgentProfile(detail.scene.scene_id, agent.agent_id, { role_profile: profileDraft,
                          ...(detail.scene.mode === 'discussion' ? { discussion_config: discussionDraft } : {}) })
                        if (currentKey.current === key) { setEditingAgentId(null); await reload() }
                      } catch (cause) { if (currentKey.current === key) setError(cause instanceof Error ? cause.message : String(cause)) }
                      finally { setSavingProfile(false) }
                    }}>保存本场设定</button>
                    <button type="button" onClick={() => setEditingAgentId(null)}>取消编辑</button>
                  </div> : null}
                </> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <RecordFacts facts={dataKey === key ? facts : null} unavailable={dataKey === key && factsUnavailable} />

      {dataKey === key && summary && !selectedAgentId ? (
        <p className="hint" data-testid="call-counts">
          实际调用计数：成功 {summary.succeeded}／失败 {summary.failed}／结果不明 {summary.unknown}
          （上限 {summary.max_role_requests}）
          {summary.last_failure_kind ? `；最近一次失败：${summary.last_failure_kind}` : ''}
        </p>
      ) : null}

      {selectedAgentId && sceneId ? (
        <ViewpointPanel key={selectedAgentId}
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
          agents={dataKey === key ? detail?.agents ?? [] : []}
          onChanged={() => {
            reload().catch(() => undefined)
          }}
          onError={setError}
        />
      ) : null}

      {(dataKey === key && timeline?.actions?.length) ? <details className="card"><summary>行动记录</summary>
        <ul>{timeline.actions.map(a => <li key={a.action_id}>{names.get(a.actor_id)}：{a.status === 'SUCCEEDED' ? actionLabel(a.draft, names) : a.status === 'PENDING' ? '生成中' : `调用失败：${a.failure_kind ?? a.status}`}</li>)}</ul>
      </details> : null}
      <div className="chat__drawer-toggle">
        <button type="button" disabled={selectedAgentId !== null} onClick={() => setDrawerOpen(true)}>
          打开行为分析抽屉
        </button>
      </div>

      {selectedAgentId ? <p className="hint">切回观察者视角选择公开材料分析。</p> : null}
      <AnalysisDrawer key={key}
        open={drawerOpen}
        sceneId={sceneId}
        mode={detail?.scene.mode}
        agents={dataKey === key ? detail?.agents ?? [] : []}
        entries={entries}
        onClose={() => setDrawerOpen(false)}
        onError={setError}
      />
    </div>
  )
}
