/**
 * M05 界面测试（PRD 4.3、5.2、7.1、7.2；tasks/M05.md A1–A10）。
 *
 * 全部通过 mock fetch / 注入 EventSource 运行：不连接后端、不调用模型。
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { TimelineList } from '../src/components/TimelineList'
import { AnalysisDrawer } from '../src/components/AnalysisDrawer'
import { ConfigView } from '../src/views/ConfigView'
import { ChatView } from '../src/views/ChatView'
import type { TimelineEntryView } from '../src/api/client'

function jsonResponse(payload: unknown, status = 200) {
  return {
    ok: status < 400,
    status,
    json: async () => payload,
  } as Response
}

function mockFetch(routes: Record<string, unknown>) {
  // 按**路径精确匹配**：`/api/scenes/scn-1` 是 `/api/scenes/scn-1/events` 的前缀，
  // 子串匹配会把场景详情错给子资源。
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

/** jsdom 没有 EventSource，测试注入一个可控实现。 */
class FakeEventSource {
  static instances: FakeEventSource[] = []
  listeners = new Map<string, ((event: MessageEvent) => void)[]>()
  closed = false

  constructor(public url: string) {
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, handler: EventListener) {
    const list = this.listeners.get(type) ?? []
    list.push(handler as (event: MessageEvent) => void)
    this.listeners.set(type, list)
  }

  removeEventListener(type: string, handler: EventListener) {
    const list = this.listeners.get(type) ?? []
    this.listeners.set(
      type,
      list.filter((item) => item !== handler),
    )
  }

  close() {
    this.closed = true
  }

  emit(type: string, data: unknown) {
    for (const handler of this.listeners.get(type) ?? []) {
      handler({ data: typeof data === 'string' ? data : JSON.stringify(data) } as MessageEvent)
    }
  }
}

const AGENTS = [
  {
    agent_id: 'agt-an',
    scene_id: 'scn-1',
    name: '安然',
    order_index: 0,
    snapshot: {
      source_template_id: 'tpl-1',
      name: '安然',
      persona: '主动热情',
      speech_style: '热情',
      initial_goal: '想找人一起度过晚上',
      private_background: '朋友临时取消了聚会',
      captured_at: '2026-09-26T20:00:00+00:00',
    },
    created_at: '2026-09-26T20:00:00+00:00',
  },
  {
    agent_id: 'agt-xu',
    scene_id: 'scn-1',
    name: '许川',
    order_index: 1,
    snapshot: {
      source_template_id: 'tpl-2',
      name: '许川',
      persona: '表达直接',
      speech_style: '短句',
      initial_goal: '想休息',
      private_background: '今天工作很累',
      captured_at: '2026-09-26T20:00:00+00:00',
    },
    created_at: '2026-09-26T20:00:00+00:00',
  },
]

const RUN_STATE = {
  scene_id: 'scn-1',
  status: 'PAUSED',
  pause_reason: 'NO_NEW_INFORMATION',
  role_requests_used: 3,
  max_role_requests: 24,
  analysis_requests_used: 0,
  max_analysis_requests: 4,
  in_flight: false,
  last_committed_seq: 2,
}

const SUMMARY = {
  scene_id: 'scn-1',
  role_requests_used: 3,
  max_role_requests: 24,
  succeeded: 2,
  failed: 1,
  unknown: 0,
  last_failure_kind: 'PROVIDER_ERROR',
}

function chatRoutes(extra: Record<string, unknown> = {}) {
  return {
    '/api/scenes/scn-1': {
      scene: {
        scene_id: 'scn-1',
        title: '三个室友的客厅',
        background: '晚上，三个室友在客厅相遇。',
        status: 'PAUSED',
        pause_reason: 'NO_NEW_INFORMATION',
        budget: { max_role_requests: 24, max_analysis_requests: 4, locked_at: null },
        schema_version: 1,
        created_at: '2026-09-26T20:00:00+00:00',
        started_at: null,
        ended_at: null,
      },
      agents: AGENTS,
      locked: true,
    },
    '/api/scenes/scn-1/timeline': {
      scene_id: 'scn-1',
      status: { scene_id: 'scn-1', run_state: 'PAUSED', pause_reason: 'NO_NEW_INFORMATION', last_committed_seq: 2, pending_event_count: 1 },
      last_seq: 2,
      role_requests_used: 3,
      max_role_requests: 24,
      analysis_requests_used: 0,
      max_analysis_requests: 4,
      entries: [],
    },
    '/api/scenes/scn-1/state': RUN_STATE,
    '/api/scenes/scn-1/events': [],
    '/api/scenes/scn-1/summary': SUMMARY,
    '/api/scenes/scn-1/agents/status': {
      scene_id: 'scn-1',
      in_flight: false,
      agents: [
        { agent_id: 'agt-an', name: '安然', order_index: 0, has_acted: true, startup_opportunity_consumed: true, processed_seq: 2, last_action_at: '2026-09-26T20:00:00+00:00', last_action_status: 'SUCCEEDED', is_requested: false, speak_count: 2 },
        { agent_id: 'agt-xu', name: '许川', order_index: 1, has_acted: false, startup_opportunity_consumed: false, processed_seq: 0, last_action_at: null, last_action_status: null, is_requested: true, speak_count: 0 },
      ],
    },
    ...extra,
  }
}

beforeEach(() => {
  // jsdom 不提供 EventSource；用可控实现替代（不连接真实后端）。
  vi.stubGlobal('EventSource', FakeEventSource)
})

afterEach(() => {
  vi.unstubAllGlobals()
  FakeEventSource.instances = []
})

// --- A1 时间线渲染与样式区分 ------------------------------------------------

const ENTRIES: TimelineEntryView[] = [
  {
    kind: 'message',
    seq: 1,
    message: {
      message_id: 'msg-1', scene_id: 'scn-1', seq: 1, actor_id: 'agt-an',
      text: '今晚一起吃饭吗？', reply_to_message_id: null, requested_speaker_id: 'agt-xu',
      created_at: '2026-09-26T20:00:00+00:00',
    },
    event: null,
    author_name: '安然',
  },
  {
    kind: 'event',
    seq: 2,
    message: null,
    event: {
      event_id: 'evt-1', scene_id: 'scn-1', seq: 2, body: '客厅的灯突然灭了。',
      visibility: 'ALL', target_agent_id: null, status: 'EFFECTIVE', schema_version: 1,
      accepted_at: '2026-09-26T20:00:00+00:00', effective_at: '2026-09-26T20:00:00+00:00',
    },
    author_name: null,
  },
  {
    kind: 'event',
    seq: 3,
    message: null,
    event: {
      event_id: 'evt-2', scene_id: 'scn-1', seq: 3, body: '只给许川的提示。',
      visibility: 'TARGETED', target_agent_id: 'agt-xu', status: 'ACCEPTED', schema_version: 1,
      accepted_at: '2026-09-26T20:00:00+00:00', effective_at: null,
    },
    author_name: null,
  },
]

describe('时间线', () => {
  it('显示完整消息并标出可见范围与待生效状态', () => {
    render(<TimelineList entries={ENTRIES} requestedAgentName="许川" />)

    expect(screen.getByText('今晚一起吃饭吗？')).toBeInTheDocument()
    expect(screen.getByText('客厅的灯突然灭了。')).toBeInTheDocument()
    expect(screen.getByText('全体可见')).toBeInTheDocument()
    expect(screen.getByText('定向可见')).toBeInTheDocument()
    expect(screen.getByText('已接受（待生效）')).toBeInTheDocument()
    expect(screen.getByText('#1')).toBeInTheDocument()
    expect(screen.getByText('#3')).toBeInTheDocument()
  })

  it('把模型／事件里的 HTML 当作文本渲染，不执行脚本', () => {
    const malicious: TimelineEntryView[] = [
      {
        kind: 'message',
        seq: 1,
        message: {
          message_id: 'msg-x', scene_id: 'scn-1', seq: 1, actor_id: 'agt-an',
          text: '<img src=x onerror="window.__xss=1" />危险内容',
          reply_to_message_id: null, requested_speaker_id: null,
          created_at: '2026-09-26T20:00:00+00:00',
        },
        event: null,
        author_name: '安然',
      },
    ]

    const { container } = render(<TimelineList entries={malicious} />)

    expect(screen.getByText(/危险内容/)).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined()
  })

  it('空时间线给出明确提示而不是假内容', () => {
    render(<TimelineList entries={[]} />)

    expect(screen.getByText(/还没有公开信息/)).toBeInTheDocument()
  })
})

// --- A2 控制栏：生成中仍可暂停／结束 ---------------------------------------

describe('聊天页控制栏', () => {
  it('生成中仍可点击暂停与结束', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch(
      chatRoutes({
        '/api/scenes/scn-1/state': { ...RUN_STATE, status: 'RUNNING', pause_reason: null, in_flight: true },
        '/api/scenes/scn-1/commands': { request_id: 'r', command: 'PAUSE', accepted: true, deduplicated: false, run_state: 'PAUSING', pause_reason: null, event_id: null, event_status: null, detail: '将在当前调用结束时暂停' },
      }),
    )
    render(<ChatView sceneId="scn-1" modelConfigured onSelectScene={() => undefined} />)

    await screen.findByRole('heading', { name: '三个室友的客厅' })
    const pause = await screen.findByRole('button', { name: '暂停' })
    const stop = screen.getByRole('button', { name: '结束' })

    expect(pause).toBeEnabled()
    expect(stop).toBeEnabled()

    await user.click(pause)
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/commands'),
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })

  it('结束后的会话不再提供事件提交入口', async () => {
    mockFetch(chatRoutes({ '/api/scenes/scn-1/state': { ...RUN_STATE, status: 'ENDED', pause_reason: null } }))
    render(<ChatView sceneId="scn-1" modelConfigured onSelectScene={() => undefined} />)

    await screen.findByRole('heading', { name: '三个室友的客厅' })

    expect(screen.getByRole('button', { name: '提交事件' })).toBeDisabled()
    expect(screen.getByText(/会话已结束，不再接受新事件/)).toBeInTheDocument()
  })

  it('显示停止原因与实际调用计数', async () => {
    mockFetch(chatRoutes())
    render(<ChatView sceneId="scn-1" modelConfigured onSelectScene={() => undefined} />)

    await screen.findByText(/停止原因/)
    expect(screen.getByText(/无新信息（不是会话结束）/)).toBeInTheDocument()
    expect(screen.getByTestId('call-counts')).toHaveTextContent('成功 2／失败 1／结果不明 0')
  })

  it('未配置凭证时明确标识模拟模式，不冒充真实模型输出', async () => {
    mockFetch(chatRoutes())
    render(<ChatView sceneId="scn-1" modelConfigured={false} onSelectScene={() => undefined} />)

    const badge = await screen.findByTestId('mock-badge')
    expect(badge).toHaveTextContent('模拟模式')
    expect(badge).toHaveTextContent('不代表真实模型输出')
  })

  it('历史（只读）模式不渲染运行控制', async () => {
    mockFetch(chatRoutes())
    render(<ChatView sceneId="scn-1" readOnly modelConfigured onSelectScene={() => undefined} />)

    await screen.findByRole('heading', { name: '三个室友的客厅' })

    expect(screen.queryByRole('button', { name: '单步' })).toBeNull()
    expect(screen.getByText(/历史模式只读取已保存数据/)).toBeInTheDocument()
  })
})

// --- A3 角色侧栏与视角 ------------------------------------------------------

describe('角色侧栏与视角', () => {
  it('角色卡显示名称与执行状态，不含心理评分', async () => {
    mockFetch(chatRoutes())
    render(<ChatView sceneId="scn-1" modelConfigured onSelectScene={() => undefined} />)

    const sidebar = await screen.findByLabelText('本场角色')
    expect(within(sidebar).getByText('安然')).toBeInTheDocument()
    expect(within(sidebar).getByText('上次行动成功')).toBeInTheDocument()
    expect(within(sidebar).getByText('尚未行动')).toBeInTheDocument()
    expect(within(sidebar).getByText(/不包含任何心理或关系评分/)).toBeInTheDocument()
  })

  it('点击角色后展示与调用器一致的上下文', async () => {
    const user = userEvent.setup()
    mockFetch(
      chatRoutes({
        '/api/scenes/scn-1/agents/agt-an/viewpoint': {
          scene_id: 'scn-1', agent_id: 'agt-an', agent_name: '安然',
          prompt_template_id: 'role_action@m02', cutoff_seq: 2,
          public_roster: ['安然', '许川'], visible_seq: [1, 2], visible_kinds: ['message', 'event'],
          prompt: '你正在扮演虚构角色「安然」。\n## 你的私有资料（仅你可见）',
        },
      }),
    )
    render(<ChatView sceneId="scn-1" modelConfigured onSelectScene={() => undefined} />)

    const sidebar = await screen.findByLabelText('本场角色')
    await user.click(within(sidebar).getByRole('button', { name: /安然/ }))

    await waitFor(() => {
      expect(screen.getByLabelText('角色视角：安然')).toBeInTheDocument()
    })
    expect(screen.getByText(/同一份构建结果/)).toBeInTheDocument()
    expect(screen.getByText(/你正在扮演虚构角色/)).toBeInTheDocument()
  })
})

// --- A4 分析抽屉（M05 基础界面，不假装完成） --------------------------------

describe('行为分析抽屉', () => {
  it('未接线时明确说明，不显示假的完成状态', () => {
    render(
      <AnalysisDrawer open sceneId="scn-1" agents={AGENTS} entries={ENTRIES} onClose={() => undefined} />,
    )

    // M06 起抽屉已接线：能力不可用时按钮**禁用**并给出原因，而不是消失，
    // 也绝不显示任何假的完成状态。
    expect(screen.getByTestId('analysis-not-wired')).toHaveTextContent('分析能力不可用')
    expect(screen.queryByText(/分析完成/)).toBeNull()
    expect(screen.getByRole('button', { name: '开始分析' })).toBeDisabled()
  })

  it('只允许选择公开材料，定向事件不进候选', () => {
    render(
      <AnalysisDrawer open sceneId="scn-1" agents={AGENTS} entries={ENTRIES} onClose={() => undefined} />,
    )

    const materials = screen.getByText('选择公开材料（默认不含私有背景与定向事件）').closest('fieldset')!
    expect(within(materials).getByText(/今晚一起吃饭吗/)).toBeInTheDocument()
    expect(within(materials).getByText(/客厅的灯突然灭了/)).toBeInTheDocument()
    expect(within(materials).queryByText(/只给许川的提示/)).toBeNull()
  })

  it('预览只包含被勾选的条目', async () => {
    const user = userEvent.setup()
    render(
      <AnalysisDrawer open sceneId="scn-1" agents={AGENTS} entries={ENTRIES} onClose={() => undefined} />,
    )

    await user.click(screen.getAllByRole('checkbox')[0]!)

    await waitFor(() => {
      expect(screen.getByTestId('analysis-preview')).toHaveTextContent('#1 安然：今晚一起吃饭吗？')
    })
    // 未勾选的条目不得出现在预览里。
    expect(screen.getByTestId('analysis-preview')).not.toHaveTextContent('灯突然灭了')
  })
})

// --- A5 配置页 --------------------------------------------------------------

const TEMPLATES = {
  templates: [
    {
      template_id: 'tpl-1', name: '安然', persona: '主动热情', speech_style: '热情',
      initial_goal: '想找人一起度过晚上', private_background: '朋友临时取消了聚会',
      created_at: '2026-09-26T20:00:00+00:00', updated_at: '2026-09-26T20:00:00+00:00',
    },
  ],
}

describe('配置页', () => {
  it('列出预置场景、模板与会话，并可创建预置会话', async () => {
    const user = userEvent.setup()
    mockFetch({
      '/api/scenes/presets': {
        presets: [
          { key: 'roommates', title: '三个室友的客厅', background: '晚上……', agent_names: ['安然', '许川', '陈禾'] },
          { key: 'convenience_store', title: '深夜便利店的三个顾客', background: '临近午夜……', agent_names: ['林小满', '周远', '郑好'] },
          { key: 'campsite', title: '周末露营地的三个人', background: '周末下午……', agent_names: ['何澜', '苏木', '涂山'] },
        ],
      },
      '/api/templates': TEMPLATES,
      '/api/scenes/preset': {
        scene: { scene_id: 'scn-new', title: '三个室友的客厅', background: 'b', status: 'READY', pause_reason: null, budget: { max_role_requests: 24, max_analysis_requests: 4, locked_at: null }, schema_version: 1, created_at: '2026-09-26T20:00:00+00:00', started_at: null, ended_at: null },
        agents: AGENTS, locked: false,
      },
      '/api/scenes': { scenes: [] },
    })
    const opened: string[] = []
    render(<ConfigView onOpenScene={(id) => opened.push(id)} />)

    await screen.findByText(/三个室友的客厅/)
    // 三个预置场景都列出，且各自可独立创建（人工裁决补齐，见 B6 决议）。
    expect(screen.getByText(/深夜便利店的三个顾客/)).toBeInTheDocument()
    expect(screen.getByText(/周末露营地的三个人/)).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: '用预置场景创建会话' })).toHaveLength(3)
    await user.click(screen.getAllByRole('button', { name: '用预置场景创建会话' })[0]!)

    await waitFor(() => {
      expect(screen.getByText(/已用预置场景创建会话/)).toBeInTheDocument()
    })
    expect(screen.getByText(/本场角色（三个室友的客厅）/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '进入聊天页' }))
    expect(opened).toEqual(['scn-new'])
  })

  it('按码点统计模板字段长度', async () => {
    mockFetch({
      '/api/templates': { templates: [] },
      '/api/scenes/presets': { presets: [] },
      '/api/scenes': { scenes: [] },
    })
    const user = userEvent.setup()
    render(<ConfigView onOpenScene={() => undefined} />)

    const nameInput = await screen.findByLabelText('名称')
    await user.type(nameInput, '😀😀')

    await waitFor(() => {
      expect(screen.getByText('名称（2／30 码点）')).toBeInTheDocument()
    })
  })

  it('预算默认值取自后端契约（角色请求 200、分析 4），创建时原样提交', async () => {
    // 人工裁决 2026-09-26：角色请求上限默认由 24 上调为 200，分析仍为 4。
    // 前端不得手写这两个数字，默认值必须来自 contract-summary.json。
    const calls: { path: string; method: string; body: Record<string, unknown> | null }[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = new URL(String(input), 'http://localhost').pathname
        const method = init?.method ?? 'GET'
        calls.push({
          path,
          method,
          body: init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null,
        })
        if (path === '/api/templates') return jsonResponse({ templates: [] })
        if (path === '/api/scenes/presets') return jsonResponse({ presets: [] })
        if (path === '/api/scenes' && method === 'GET') return jsonResponse({ scenes: [] })
        if (path === '/api/scenes' && method === 'POST') {
          return jsonResponse({
            scene: {
              scene_id: 'scn-x',
              title: '三个室友的客厅',
              background: 'b',
              status: 'READY',
              pause_reason: null,
              budget: { max_role_requests: 200, max_analysis_requests: 4, locked_at: null },
              schema_version: 1,
              created_at: '2026-09-26T20:00:00+00:00',
              started_at: null,
              ended_at: null,
            },
            agents: [],
            locked: false,
          })
        }
        return jsonResponse({ error: 'not_found', detail: path }, 404)
      }),
    )

    const user = userEvent.setup()
    render(<ConfigView onOpenScene={() => undefined} />)

    expect(await screen.findByLabelText('角色请求上限')).toHaveValue(200)
    expect(screen.getByLabelText('分析请求上限')).toHaveValue(4)

    await user.click(screen.getByRole('button', { name: '创建会话' }))

    await waitFor(() => {
      expect(calls.some((call) => call.method === 'POST' && call.path === '/api/scenes')).toBe(true)
    })
    const created = calls.find((call) => call.method === 'POST' && call.path === '/api/scenes')
    expect(created?.body?.max_role_requests).toBe(200)
    expect(created?.body?.max_analysis_requests).toBe(4)
  })
})
