import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatView } from '../src/views/ChatView'
import { ControlBar } from '../src/components/ControlBar'
import { RoleSidebar } from '../src/components/RoleSidebar'
import { TimelineList } from '../src/components/TimelineList'
import { pauseReasonLabel } from '../src/lib/labels'
import type { AgentStatusListView, RunStateView, SceneAgent, TimelineEntryView } from '../src/api/client'

const time = '2026-09-29T00:00:00+00:00'
const agents: SceneAgent[] = ['甲', '乙'].map((name, index) => ({
  agent_id: `a${index}`, scene_id: 's', name, order_index: index, created_at: time,
  snapshot: { source_template_id: `t${index}`, name, persona: '', speech_style: '',
    initial_goal: '', private_background: '', public_profile: '', captured_at: time },
}))
const state: RunStateView = { scene_id: 's', status: 'PAUSED', pause_reason: 'COLLECTIVE_SILENCE',
  role_requests_used: 2, max_role_requests: 200, analysis_requests_used: 0, max_analysis_requests: 4,
  in_flight: false, last_committed_seq: 0 }
function response(value: unknown) { return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } }) }
beforeEach(() => sessionStorage.clear())
afterEach(() => vi.unstubAllGlobals())

it('全员沉默文案提供继续入口并发送一次显式命令', async () => {
  const fetch = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ accepted: true, run_state: 'RUNNING', deduplicated: false }))
  vi.stubGlobal('fetch', fetch)
  render(<ControlBar sceneId="s" state={state} agents={agents} onChanged={() => undefined} onError={() => undefined} />)
  expect(pauseReasonLabel('COLLECTIVE_SILENCE')).toBe('所有角色本轮均未发言')
  expect(screen.getByText(/点击“继续”或“单步”/)).toBeInTheDocument()
  await userEvent.setup().click(screen.getByRole('button', { name: '继续' }))
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
  expect(JSON.parse(String(fetch.mock.calls[0]?.[1]?.body)).command).toBe('RESUME')
})

it('上下文接近上限可见，角色视角隐藏他人的使用量', () => {
  const status: AgentStatusListView = { scene_id: 's', in_flight: false, agents: agents.map((agent, index) => ({
    agent_id: agent.agent_id, name: agent.name, order_index: index,
    generating: false, has_acted: false, is_requested: false, processed_seq: 0,
    speak_count: 0, startup_opportunity_consumed: false,
    prompt_codepoints: index === 0 ? 26000 : 12345, max_prompt_codepoints: 32000,
  })) }
  const { rerender } = render(<RoleSidebar agents={agents} status={status} selectedAgentId={null} onSelect={() => undefined} />)
  expect(screen.getByText(/上下文 26000／32000 码点 · 接近上限/)).toBeInTheDocument()
  expect(screen.getByText(/上下文 12345／32000/)).toBeInTheDocument()
  rerender(<RoleSidebar agents={agents} status={status} selectedAgentId="a0" viewerId="a0" onSelect={() => undefined} />)
  expect(screen.queryByText(/12345/)).not.toBeInTheDocument()
})

it('1000码点分段正文完整显示且HTML保持转义', () => {
  const suffix = '\n第二段 <img src=x onerror=alert(1)>'
  const text = '字'.repeat(1000 - [...suffix].length) + suffix
  const entries: TimelineEntryView[] = [{ kind: 'message', seq: 1, author_name: '甲', message: {
    schema_version: 2, message_id: 'm', scene_id: 's', seq: 1, actor_id: 'a0', visibility: 'PUBLIC', text, created_at: time,
  } }]
  const { container } = render(<TimelineList entries={entries} />)
  expect(container.querySelector('.bubble')?.textContent).toBe(text)
  expect(container.querySelector('img')).toBeNull()
})

it.each([1, 2])('历史场景显示保存的聊天规则版本 %i 且不发送控制命令', async version => {
  const detail = { scene: { scene_id: 's', title: '历史', mode: 'simulation', background: '',
    configuration_version: 2, chat_policy_version: version, status: 'PAUSED',
    budget: { max_role_requests: 200, max_analysis_requests: 4 }, created_at: time }, agents, locked: true }
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const path = new URL(String(input), 'http://localhost').pathname
    if (path === '/api/scenes/s') return response(detail)
    if (path.endsWith('/state')) return response(state)
    if (path.endsWith('/timeline')) return response({ entries: [], conversations: [], actions: [] })
    if (path.endsWith('/events')) return response([])
    if (path.endsWith('/agents/status')) return response({ scene_id: 's', agents: [] })
    if (path.endsWith('/statistics')) return response({ public_messages: 0, private_messages: 0, participant_ids: [], reply_relations: [], role_actions: [] })
    if (path.endsWith('/summary')) return response({ succeeded: 0, failed: 0, unknown: 0, max_role_requests: 200 })
    return response({})
  })
  vi.stubGlobal('fetch', fetch)
  render(<ChatView sceneId="s" readOnly modelConfigured={false} onSelectScene={() => undefined} />)
  expect(await screen.findByText(version === 2 ? /自由续聊 · 每条最多 1000/ : /旧版规则 · 每条最多 200/)).toBeInTheDocument()
  expect(fetch.mock.calls.some(call => String(call[0]).includes('/commands'))).toBe(false)
})
