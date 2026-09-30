/**
 * 界面文案映射。
 *
 * 所有枚举取值都来自后端契约（`contract-summary.json` / 生成类型），
 * 前端不另立一套状态名；这里只把它们翻译成中文标签。
 */

import type { EventStatus, EventVisibility, PauseReason, RunState } from '../api/client'

export const RUN_STATE_LABELS: Record<RunState, string> = {
  READY: '待开始',
  RUNNING: '运行中',
  PAUSING: '暂停中',
  STOPPING: '结束中',
  PAUSED: '已暂停',
  ENDED: '已结束',
}

export const PAUSE_REASON_LABELS: Record<PauseReason, string> = {
  NO_NEW_INFORMATION: '无新信息（不是会话结束）',
  COLLECTIVE_SILENCE: '所有角色本轮均未发言',
  MANUAL: '人工暂停',
  PROVIDER_ERROR: '接口错误',
  CONTEXT_LIMIT: '上下文超限',
  PROCESS_INTERRUPT: '进程中断',
}

export const EVENT_STATUS_LABELS: Record<EventStatus, string> = {
  ACCEPTED: '已接受（待生效）',
  EFFECTIVE: '已生效',
}

export const EVENT_VISIBILITY_LABELS: Record<EventVisibility, string> = {
  ALL: '全体可见',
  TARGETED: '定向可见',
}

export function runStateLabel(state: RunState): string {
  return RUN_STATE_LABELS[state] ?? state
}

export function pauseReasonLabel(reason: PauseReason | null | undefined): string {
  if (!reason) {
    return ''
  }
  return PAUSE_REASON_LABELS[reason] ?? reason
}

/** 运行状态对应的样式类（错误、待生效、停止原因与普通台词必须有不同样式）。 */
export function runStateTone(state: RunState): string {
  if (state === 'ENDED') return 'tone-ended'
  if (state === 'PAUSED') return 'tone-paused'
  if (state === 'PAUSING' || state === 'STOPPING') return 'tone-transition'
  if (state === 'RUNNING') return 'tone-running'
  return 'tone-ready'
}
