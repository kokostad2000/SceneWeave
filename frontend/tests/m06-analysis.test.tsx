/**
 * M06 分析抽屉接线测试（PRD 6.1、6.2；tasks/M06.md A13）。
 *
 * 用 mock fetch 驱动：不连接后端、不调用外部仓库。
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AnalysisDrawer } from '../src/components/AnalysisDrawer'
import type { AnalysisRecordView, TimelineEntryView } from '../src/api/client'

function jsonResponse(payload: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => payload } as Response
}

function mockFetch(routes: Record<string, unknown>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const path = new URL(String(input), 'http://localhost').pathname
    const payload = routes[path]
    if (payload === undefined) {
      return jsonResponse({ error: 'not_found', detail: `no mock for ${path}` }, 404)
    }
    return jsonResponse(typeof payload === 'function' ? (payload as () => unknown)() : payload)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const AGENTS = [
  {
    agent_id: 'agt-an', scene_id: 'scn-1', name: '安然', order_index: 0,
    snapshot: { source_template_id: 'tpl-1', name: '安然', persona: '主动热情', speech_style: '热情', initial_goal: '想找人一起度过晚上', private_background: '朋友临时取消了聚会', captured_at: '2026-09-26T20:00:00+00:00' },
    created_at: '2026-09-26T20:00:00+00:00',
  },
]

const ENTRIES: TimelineEntryView[] = [
  {
    kind: 'message', seq: 1,
    message: { message_id: 'msg-1', scene_id: 'scn-1', seq: 1, actor_id: 'agt-an', text: '今晚一起吃饭吗？', reply_to_message_id: null, requested_speaker_id: null, created_at: '2026-09-26T20:00:00+00:00' },
    event: null, author_name: '安然',
  },
  {
    kind: 'event', seq: 2, message: null,
    event: { event_id: 'evt-1', scene_id: 'scn-1', seq: 2, body: '客厅的灯突然灭了。', visibility: 'ALL', target_agent_id: null, status: 'EFFECTIVE', schema_version: 1, accepted_at: '2026-09-26T20:00:00+00:00', effective_at: '2026-09-26T20:00:00+00:00' },
    author_name: null,
  },
  {
    kind: 'event', seq: 3, message: null,
    event: { event_id: 'evt-2', scene_id: 'scn-1', seq: 3, body: '只给许川的提示。', visibility: 'TARGETED', target_agent_id: 'agt-xu', status: 'EFFECTIVE', schema_version: 1, accepted_at: '2026-09-26T20:00:00+00:00', effective_at: '2026-09-26T20:00:00+00:00' },
    author_name: null,
  },
]

function emptyList(capability: Record<string, unknown>) {
  return {
    scene_id: 'scn-1',
    capability,
    operations_total: 0,
    provider_attempts_total: 0,
    analysis_requests_used: 0,
    max_analysis_requests: 4,
    records: [],
  }
}

function record(overrides: Partial<AnalysisRecordView> = {}): AnalysisRecordView {
  return {
    analysis_id: 'ana-1',
    scene_id: 'scn-1',
    agent_id: 'agt-an',
    status: 'NORMAL',
    provider_attempts: 1,
    degradation_flags: [],
    error: null,
    created_at: '2026-09-26T20:00:00+00:00',
    material_seqs: [1],
    materials: [{ kind: 'message', source_id: 'message:1:agt-an', author_agent_id: 'agt-an', text: '今晚一起吃饭吗？' }],
    behavior_description: '#1 安然：今晚一起吃饭吗？',
    context: '',
    report: {
      status: 'NORMAL',
      scene_id: 'scn-1',
      agent_id: 'agt-an',
      behavior_labels: ['主动邀请'],
      mechanisms: ['寻求社会连接'],
      alternative_explanations: ['只是礼貌寒暄', '想确认今晚的安排'],
      limitations: ['仅基于公开文本'],
      disclaimer: '仅用于解释虚构角色的文本行为。',
      degradation_flags: [],
      provider_attempts: 1,
      usage: { input_tokens: 12, output_tokens: 8, cached_tokens: null },
      error: null,
    },
    ...overrides,
  }
}

const ROUTES = {
  '/api/scenes/scn-1/analyses/capability': { scene_id: 'scn-1', capability: { enabled: true, external_package_installed: true, reason: null } },
  '/api/scenes/scn-1/analyses': emptyList({ enabled: true, external_package_installed: true, reason: null }),
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('分析抽屉（M06 接线）', () => {
  it('能力可用时提供开始分析按钮', async () => {
    mockFetch(ROUTES)
    render(<AnalysisDrawer open sceneId="scn-1" agents={AGENTS} entries={ENTRIES} onClose={() => undefined} />)

    await waitFor(() => {
      expect(screen.getByTestId('analysis-ready')).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: '开始分析' })).toBeDisabled()
  })

  it('能力不可用时说明具体原因且不显示假的完成状态', async () => {
    mockFetch({
      ...ROUTES,
      '/api/scenes/scn-1/analyses/capability': {
        scene_id: 'scn-1',
        capability: { enabled: false, external_package_installed: false, reason: '外部分析仓库不可用：No module named src' },
      },
    })
    render(<AnalysisDrawer open sceneId="scn-1" agents={AGENTS} entries={ENTRIES} onClose={() => undefined} />)

    const notice = await screen.findByTestId('analysis-not-wired')
    expect(notice).toHaveTextContent('外部分析仓库不可用')
    expect(screen.getByRole('button', { name: '开始分析' })).toBeDisabled()
    expect(screen.queryByText('分析完成')).toBeNull()
  })

  it('只把公开材料列为候选（定向事件被排除）', async () => {
    mockFetch(ROUTES)
    render(<AnalysisDrawer open sceneId="scn-1" agents={AGENTS} entries={ENTRIES} onClose={() => undefined} />)

    await screen.findByTestId('analysis-ready')
    const materials = screen.getByText('选择公开材料（默认不含私有背景与定向事件）').closest('fieldset')!
    expect(within(materials).getByText(/今晚一起吃饭吗/)).toBeInTheDocument()
    expect(within(materials).getByText(/灯突然灭了/)).toBeInTheDocument()
    expect(within(materials).queryByText(/只给许川的提示/)).toBeNull()
  })

  it('提交后展示标签、至少两种替代解释、局限与免责声明', async () => {
    const user = userEvent.setup()
    mockFetch({
      ...ROUTES,
      '/api/scenes/scn-1/analyses': (() => {
        let call = 0
        return () => {
          call += 1
          return call === 1 ? emptyList({ enabled: true, external_package_installed: true, reason: null }) : record()
        }
      })(),
    })
    render(<AnalysisDrawer open sceneId="scn-1" agents={AGENTS} entries={ENTRIES} onClose={() => undefined} />)

    await screen.findByTestId('analysis-ready')
    await user.selectOptions(screen.getByLabelText('分析对象'), 'agt-an')
    await user.click(screen.getAllByRole('checkbox')[0]!)
    await user.click(screen.getByRole('button', { name: '开始分析' }))

    const results = await screen.findByLabelText('分析结果')
    expect(within(results).getByText('主动邀请')).toBeInTheDocument()
    expect(within(results).getByText('寻求社会连接')).toBeInTheDocument()
    expect(within(results).getByText('只是礼貌寒暄')).toBeInTheDocument()
    expect(within(results).getByText('想确认今晚的安排')).toBeInTheDocument()
    expect(within(results).getByText('仅基于公开文本')).toBeInTheDocument()
    expect(within(results).getByText(/仅用于解释虚构角色的文本行为/)).toBeInTheDocument()
    expect(within(results).getByText('正常')).toBeInTheDocument()
  })

  it('降级结果可见，且标明实际模型请求次数', async () => {
    const user = userEvent.setup()
    const degraded = record({
      status: 'DEGRADED',
      degradation_flags: ['insufficient_alternative_explanations'],
    })
    mockFetch({
      ...ROUTES,
      '/api/scenes/scn-1/analyses': (() => {
        let call = 0
        return () => {
          call += 1
          return call === 1 ? emptyList({ enabled: true, external_package_installed: true, reason: null }) : degraded
        }
      })(),
    })
    render(<AnalysisDrawer open sceneId="scn-1" agents={AGENTS} entries={ENTRIES} onClose={() => undefined} />)

    await screen.findByTestId('analysis-ready')
    await user.selectOptions(screen.getByLabelText('分析对象'), 'agt-an')
    await user.click(screen.getAllByRole('checkbox')[0]!)
    await user.click(screen.getByRole('button', { name: '开始分析' }))

    const results = await screen.findByLabelText('分析结果')
    expect(within(results).getByText(/降级结果/)).toBeInTheDocument()
    expect(within(results).getByText(/insufficient_alternative_explanations/)).toBeInTheDocument()
    expect(within(results).getByText(/实际模型请求 1 次/)).toBeInTheDocument()
  })

  it('被本地规则拦截时显示 0 次模型请求', async () => {
    const user = userEvent.setup()
    const blocked = record({
      status: 'BLOCKED',
      provider_attempts: 0,
      error: '选择的材料 #9 不存在或尚未提交',
      materials: [],
      report: {
        status: 'BLOCKED', scene_id: 'scn-1', agent_id: 'agt-an',
        behavior_labels: [], mechanisms: [], alternative_explanations: [],
        limitations: [], disclaimer: '', degradation_flags: ['unknown_material_seq'],
        provider_attempts: 0, usage: { input_tokens: null, output_tokens: null, cached_tokens: null },
        error: '选择的材料 #9 不存在或尚未提交',
      },
    })
    mockFetch({
      ...ROUTES,
      '/api/scenes/scn-1/analyses': (() => {
        let call = 0
        return () => {
          call += 1
          return call === 1 ? emptyList({ enabled: true, external_package_installed: true, reason: null }) : blocked
        }
      })(),
    })
    render(<AnalysisDrawer open sceneId="scn-1" agents={AGENTS} entries={ENTRIES} onClose={() => undefined} />)

    await screen.findByTestId('analysis-ready')
    await user.selectOptions(screen.getByLabelText('分析对象'), 'agt-an')
    await user.click(screen.getAllByRole('checkbox')[0]!)
    await user.click(screen.getByRole('button', { name: '开始分析' }))

    const results = await screen.findByLabelText('分析结果')
    expect(within(results).getByText(/被本地规则拦截/)).toBeInTheDocument()
    expect(within(results).getByText(/实际模型请求 0 次/)).toBeInTheDocument()
  })

  it('把操作数与实际模型请求数分开显示', async () => {
    mockFetch({
      ...ROUTES,
      '/api/scenes/scn-1/analyses': {
        ...emptyList({ enabled: true, external_package_installed: true, reason: null }),
        operations_total: 5,
        provider_attempts_total: 2,
      },
    })
    render(<AnalysisDrawer open sceneId="scn-1" agents={AGENTS} entries={ENTRIES} onClose={() => undefined} />)

    await waitFor(() => {
      expect(screen.getByText(/分析操作数 5｜实际模型请求数 2/)).toBeInTheDocument()
    })
  })
})
