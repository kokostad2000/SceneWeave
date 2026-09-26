/**
 * 行为分析抽屉（PRD 6.1、7.1）。
 *
 * M05 建立了选材与预览骨架；M06 在这里接线：
 * - 只允许选择**已提交的公开材料**（私有背景与定向事件不进候选）；
 * - 送出前可预览将要发送的原文；
 * - 结果展示行为标签、可能机制、**至少两种替代解释**、局限与免责声明；
 * - 五种状态（normal／blocked／degraded／failed／disabled）与降级标记**可见**；
 * - 能力不可用时明确说明原因，不显示假的“分析完成”。
 */

import { useEffect, useMemo, useState } from 'react'

import {
  createAnalysis,
  fetchAnalysisCapability,
  listAnalyses,
  type AnalysisCapabilityView,
  type AnalysisRecordView,
  type SceneAgent,
  type TimelineEntryView,
} from '../api/client'

export interface AnalysisDrawerProps {
  readonly open: boolean
  readonly sceneId: string | null
  readonly agents: readonly SceneAgent[]
  readonly entries: readonly TimelineEntryView[]
  readonly onClose: () => void
  readonly onError?: (message: string) => void
}

const STATUS_LABELS: Record<string, string> = {
  NORMAL: '正常',
  BLOCKED: '被本地规则拦截（未发送）',
  DEGRADED: '降级结果（外部返回不完整）',
  FAILED: '失败',
  DISABLED: '分析能力不可用',
}

export function AnalysisDrawer({
  open,
  sceneId,
  agents,
  entries,
  onClose,
  onError,
}: AnalysisDrawerProps) {
  const [agentId, setAgentId] = useState<string>('')
  const [selected, setSelected] = useState<number[]>([])
  const [capability, setCapability] = useState<AnalysisCapabilityView['capability'] | null>(null)
  const [records, setRecords] = useState<AnalysisRecordView[]>([])
  const [operationsTotal, setOperationsTotal] = useState(0)
  const [providerAttempts, setProviderAttempts] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  /** 只提供**公开**条目：私有背景与定向事件默认不送分析（PRD 6.1）。 */
  const publicEntries = useMemo(
    () =>
      entries.filter((entry) => {
        if (entry.kind === 'message') return true
        return entry.event?.visibility === 'ALL' && entry.event?.status === 'EFFECTIVE'
      }),
    [entries],
  )

  useEffect(() => {
    if (!open || sceneId === null) return
    const controller = new AbortController()
    fetchAnalysisCapability(sceneId, controller.signal)
      .then((value) => setCapability(value.capability))
      .catch(() => undefined)
    listAnalyses(sceneId, controller.signal)
      .then((value) => {
        setRecords(value.records)
        setOperationsTotal(value.operations_total)
        setProviderAttempts(value.provider_attempts_total)
      })
      .catch(() => undefined)
    return () => controller.abort()
  }, [open, sceneId])

  const preview = useMemo(
    () =>
      publicEntries
        .filter((entry) => selected.includes(entry.seq))
        .map((entry) =>
          entry.kind === 'message'
            ? `#${entry.seq} ${entry.author_name ?? ''}：${entry.message?.text ?? ''}`
            : `#${entry.seq} 事件：${entry.event?.body ?? ''}`,
        )
        .join('\n'),
    [publicEntries, selected],
  )

  if (!open) {
    return null
  }

  function toggle(seq: number) {
    setSelected((previous) =>
      previous.includes(seq)
        ? previous.filter((item) => item !== seq)
        : [...previous, seq].sort((a, b) => a - b),
    )
  }

  async function runAnalysis() {
    if (sceneId === null) return
    setBusy(true)
    setError(null)
    try {
      const record = await createAnalysis(sceneId, { agent_id: agentId, material_seqs: selected })
      setRecords((previous) => [...previous, record])
      setOperationsTotal((total) => total + 1)
      setProviderAttempts((total) => total + record.provider_attempts)
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause)
      setError(message)
      onError?.(message)
    } finally {
      setBusy(false)
    }
  }

  const disabled = capability?.enabled !== true

  return (
    <aside className="drawer" role="dialog" aria-label="行为分析">
      <header className="drawer__header">
        <h2>行为分析</h2>
        <button type="button" onClick={onClose}>
          关闭
        </button>
      </header>

      <p className="hint">
        分析操作数 {operationsTotal}｜实际模型请求数 {providerAttempts}
        （两者分开计数：被本地规则拦截或能力关闭时不会发起请求）
      </p>

      {disabled ? (
        <p className="state state--pending" data-testid="analysis-not-wired">
          分析能力不可用：{capability?.reason ?? '能力未开启'}。当前只能选择材料并预览，不会发起任何分析请求。
        </p>
      ) : (
        <p className="state state--ok" data-testid="analysis-ready">
          分析能力已开启（外部仓库已就绪）。
        </p>
      )}

      <label className="field">
        <span>分析对象</span>
        <select value={agentId} onChange={(event) => setAgentId(event.target.value)}>
          <option value="">选择一名本场角色…</option>
          {agents.map((agent) => (
            <option key={agent.agent_id} value={agent.agent_id}>
              {agent.name}
            </option>
          ))}
        </select>
      </label>

      <fieldset className="drawer__materials">
        <legend>选择公开材料（默认不含私有背景与定向事件）</legend>
        {publicEntries.length === 0 ? (
          <p className="hint">还没有可选的公开材料。</p>
        ) : (
          publicEntries.map((entry) => (
            <label key={`${entry.kind}-${entry.seq}`} className="drawer__material">
              <input
                type="checkbox"
                checked={selected.includes(entry.seq)}
                onChange={() => toggle(entry.seq)}
              />
              <span>
                #{entry.seq} {entry.kind === 'message' ? (entry.author_name ?? '角色发言') : '公开事件'}：
                {entry.kind === 'message' ? entry.message?.text : entry.event?.body}
              </span>
            </label>
          ))
        )}
      </fieldset>

      <section>
        <h3>预览将要送出的材料</h3>
        <pre className="prompt-view" data-testid="analysis-preview">
          {preview === '' ? '（尚未选择材料）' : preview}
        </pre>
        <p className="hint">超出接口长度上限时会提示缩小选择，不会截断或自动总结。</p>
      </section>

      <p className="hint">
        分析结果是只读的独立观察，不进入角色记忆、不改变人设、也不触发调度。
      </p>

      {error ? <p className="state state--error">{error}</p> : null}

      <button
        type="button"
        disabled={busy || agentId === '' || selected.length === 0 || disabled}
        onClick={runAnalysis}
      >
        {busy ? '分析中…' : '开始分析'}
      </button>

      {records.length > 0 ? (
        <section aria-label="分析结果">
          <h3>分析记录</h3>
          {records.map((record) => (
            <AnalysisRecordCard key={record.analysis_id} record={record} />
          ))}
        </section>
      ) : null}
    </aside>
  )
}

function AnalysisRecordCard({ record }: { record: AnalysisRecordView }) {
  const report = record.report
  const labels = report.behavior_labels ?? []
  const mechanisms = report.mechanisms ?? []
  const alternatives = report.alternative_explanations ?? []
  const limitations = report.limitations ?? []
  const flags = record.degradation_flags ?? []
  const degraded = record.status === 'DEGRADED' || flags.length > 0

  return (
    <article className={degraded ? 'card card--degraded' : 'card'}>
      <div className="timeline__meta">
        <span className={`state ${degraded ? 'state--pending' : 'state--ok'}`}>
          {STATUS_LABELS[record.status] ?? record.status}
        </span>
        <span className="hint">实际模型请求 {record.provider_attempts} 次</span>
      </div>

      {record.error ? <p className="hint">说明：{record.error}</p> : null}

      {labels.length > 0 ? (
        <>
          <h4>行为标签</h4>
          <ul>
            {labels.map((label) => (
              <li key={label}>{label}</li>
            ))}
          </ul>
        </>
      ) : null}

      {mechanisms.length > 0 ? (
        <>
          <h4>可能机制</h4>
          <ul>
            {mechanisms.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      ) : null}

      {alternatives.length > 0 ? (
        <>
          <h4>替代解释</h4>
          <ul>
            {alternatives.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      ) : null}

      {limitations.length > 0 ? (
        <>
          <h4>局限</h4>
          <ul>
            {limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      ) : null}

      {flags.length > 0 ? (
        <p className="hint">降级标记：{flags.join('、')}</p>
      ) : null}

      {report.disclaimer ? <p className="hint">{report.disclaimer}</p> : null}
    </article>
  )
}

export default AnalysisDrawer
