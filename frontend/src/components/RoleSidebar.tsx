/**
 * 角色侧栏（PRD 7.1、7.2）。
 *
 * 角色卡只显示**名称与执行状态**，不显示任何虚构的心理仪表盘或关系评分。
 * 数据来自只读观察接口 `GET /api/scenes/{id}/agents/status`。
 */

import type { AgentStatusListView, SceneAgent } from '../api/client'
import { actionLabel } from '../lib/actions'

export interface RoleSidebarProps {
  readonly agents: readonly SceneAgent[]
  readonly status: AgentStatusListView | null
  readonly selectedAgentId: string | null
  readonly viewerId?: string | null
  readonly onSelect: (agentId: string) => void
}

const LAST_STATUS_LABELS: Record<string, string> = {
  SUCCEEDED: '上次行动成功',
  FAILED: '上次行动失败',
  UNKNOWN: '上次行动结果不明',
}

export function RoleSidebar({ agents, status, selectedAgentId, onSelect, viewerId = null }: RoleSidebarProps) {
  const byId = new Map((status?.agents ?? []).map((item) => [item.agent_id, item]))

  const names = new Map(agents.map(a => [a.agent_id, a.name]))
  return (
    <aside className="sidebar" aria-label="本场角色">
      <h2>本场角色</h2>
      <ul className="sidebar__list">
        {agents.map((agent) => {
          const info = byId.get(agent.agent_id)
          const executed = info?.has_acted === true
          return (
            <li key={agent.agent_id}>
              <button
                type="button"
                className={`role-card${selectedAgentId === agent.agent_id ? ' role-card--active' : ''}${
                  info?.is_requested ? ' role-card--requested' : ''
                }`}
                onClick={() => onSelect(agent.agent_id)}
              >
                <span className="role-card__name">{agent.name}</span>
                <span className="role-card__meta">公开身份：{agent.snapshot.public_profile || '（未提供）'}</span>
                <span className="role-card__state">
                  {viewerId && agent.agent_id !== viewerId ? '公开名册' : info?.generating ? '生成中' : info?.last_failure_kind ? `调用失败：${info.last_failure_kind}` : '等待行动'}
                  {(!viewerId || agent.agent_id === viewerId) ? <small>{executed ? LAST_STATUS_LABELS[info?.last_action_status ?? ''] ?? '已行动' : '尚未行动'}</small> : null}
                </span>
                {(!viewerId || agent.agent_id === viewerId) ? <span className="role-card__meta">最近行动：{actionLabel(info?.last_successful_draft, names)}</span> : null}
                {(!viewerId || agent.agent_id === viewerId) ? <span className="role-card__meta">
                  已发言 {info?.speak_count ?? 0} 条
                  {info?.is_requested ? ' · 当前待回应' : ''}
                </span> : null}
                {(!viewerId || agent.agent_id === viewerId) && typeof info?.prompt_codepoints === 'number' ? <span className="role-card__meta">
                  上下文 {info.prompt_codepoints}／{info.max_prompt_codepoints} 码点
                  {info.prompt_codepoints >= (info.max_prompt_codepoints ?? 32000) ? ' · 已达上限，请新建场景' :
                    info.prompt_codepoints >= (info.max_prompt_codepoints ?? 32000) * 0.8 ? ' · 接近上限' : ''}
                </span> : null}
              </button>
            </li>
          )
        })}
      </ul>
      <p className="hint">
        状态只反映运行事实（是否行动、上次结果、已处理到哪条），不包含任何心理或关系评分。
      </p>
    </aside>
  )
}
