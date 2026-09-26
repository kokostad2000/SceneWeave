/**
 * 运行控制与事件输入（PRD 5.2、4.3、7.1）。
 *
 * - 生成中（`inFlight`）按钮**仍然可点**：暂停／结束在当前调用边界生效；
 * - 结束请求之后不再提供插入事件的入口；
 * - 命令携带 `request_id`，重复提交由后端幂等处理。
 */

import { useState } from 'react'

import { injectEvent, newRequestId, sendCommand, type ControlCommandType, type EventVisibility, type RunStateView, type SceneAgent } from '../api/client'
import { EVENT_VISIBILITY_LABELS } from '../lib/labels'

export interface ControlBarProps {
  readonly sceneId: string
  readonly state: RunStateView
  readonly agents: readonly SceneAgent[]
  readonly disabled?: boolean
  readonly onChanged: () => void
  readonly onError: (message: string) => void
}

export function ControlBar({ sceneId, state, agents, disabled = false, onChanged, onError }: ControlBarProps) {
  const [busy, setBusy] = useState(false)
  const [eventBody, setEventBody] = useState('')
  const [visibility, setVisibility] = useState<EventVisibility>('ALL')
  const [target, setTarget] = useState<string>('')
  const [notice, setNotice] = useState<string | null>(null)

  const ended = state.status === 'ENDED'

  async function run(command: ControlCommandType) {
    setBusy(true)
    setNotice(null)
    try {
      const ack = await sendCommand(sceneId, newRequestId(command.toLowerCase()), command)
      setNotice(ack.detail ?? null)
      onChanged()
    } catch (error) {
      onError(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  async function submitEvent() {
    const body = eventBody.trim()
    if (body === '') {
      onError('事件正文不能为空')
      return
    }
    if (visibility === 'TARGETED' && target === '') {
      onError('定向事件必须选择一名本场角色')
      return
    }
    setBusy(true)
    setNotice(null)
    try {
      const ack = await injectEvent(sceneId, {
        request_id: newRequestId('event'),
        body,
        visibility,
        target_agent_id: visibility === 'TARGETED' ? target : null,
      })
      setNotice(ack.detail ?? null)
      setEventBody('')
      onChanged()
    } catch (error) {
      onError(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="controls">
      <div className="controls__row">
        <button type="button" onClick={() => run('START')} disabled={disabled || busy || ended || state.status === 'RUNNING'}>
          自动运行
        </button>
        <button type="button" onClick={() => run('STEP')} disabled={disabled || busy || ended || state.in_flight}>
          单步
        </button>
        <button type="button" onClick={() => run('PAUSE')} disabled={disabled || busy || ended || state.status === 'PAUSED'}>
          暂停
        </button>
        <button type="button" onClick={() => run('RESUME')} disabled={disabled || busy || ended || state.status !== 'PAUSED'}>
          继续
        </button>
        <button type="button" onClick={() => run('STOP')} disabled={disabled || busy || ended}>
          结束
        </button>
        <span className="controls__note">
          已用角色请求 {state.role_requests_used}／{state.max_role_requests}
          {state.in_flight ? '（有一次调用进行中）' : ''}
        </span>
      </div>

      {notice ? <p className="hint">{notice}</p> : null}

      <div className="controls__row controls__row--event">
        <input
          aria-label="事件正文"
          className="controls__input"
          placeholder="插入一个事件（如“客厅的灯突然灭了。”）"
          value={eventBody}
          maxLength={1000}
          onChange={(changeEvent) => setEventBody(changeEvent.target.value)}
          disabled={disabled || ended}
        />
        <select
          aria-label="事件可见范围"
          value={visibility}
          onChange={(changeEvent) => setVisibility(changeEvent.target.value as EventVisibility)}
          disabled={disabled || ended}
        >
          <option value="ALL">{EVENT_VISIBILITY_LABELS.ALL}</option>
          <option value="TARGETED">{EVENT_VISIBILITY_LABELS.TARGETED}</option>
        </select>
        {visibility === 'TARGETED' ? (
          <select
            aria-label="事件目标角色"
            value={target}
            onChange={(changeEvent) => setTarget(changeEvent.target.value)}
            disabled={disabled || ended}
          >
            <option value="">选择角色…</option>
            {agents.map((agent) => (
              <option key={agent.agent_id} value={agent.agent_id}>
                {agent.name}
              </option>
            ))}
          </select>
        ) : null}
        <button type="button" onClick={submitEvent} disabled={disabled || busy || ended}>
          提交事件
        </button>
      </div>
      {ended ? <p className="hint">会话已结束，不再接受新事件；历史仍可查看。</p> : null}
    </div>
  )
}
