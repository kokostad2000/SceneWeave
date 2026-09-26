/**
 * 角色侧栏（PRD 7.1、7.2）。
 *
 * 角色卡只显示**名称与执行状态**，不显示任何虚构的心理仪表盘或关系评分。
 * 数据来自只读观察接口 `GET /api/scenes/{id}/agents/status`。
 */

import type { AgentStatusListView, SceneAgent } from '../api/client'

export interface RoleSidebarProps {
  readonly agents: readonly SceneAgent[]
  readonly status: AgentStatusListView | null
  readonly selectedAgentId: string | null
  readonly onSelect: (agentId: string) => void
}

const LAST_STATUS_LABELS: Record<string, string> = {
  SUCCEEDED: '上次行动成功',
  FAILED: '上次行动失败',
  UNKNOWN: '上次行动结果不明',
}

export function RoleSidebar({ agents, status, selectedAgentId, onSelect }: RoleSidebarProps) {
  const byId = new Map((status?.agents ?? []).map((item) => [item.agent_id, item]))

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
                <span className="role-card__state">
                  {executed ? LAST_STATUS_LABELS[info?.last_action_status ?? ''] ?? '已行动' : '尚未行动'}
                </span>
                <span className="role-card__meta">
                  已发言 {info?.speak_count ?? 0} 条
                  {info?.is_requested ? ' · 当前待回应' : ''}
                </span>
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
