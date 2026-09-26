/**
 * 应用外壳测试（PRD 7.1 页面结构）。
 *
 * 三个视图共用同一条后端；这里用 mock fetch 验证页面切换、后端不可用提示，
 * 以及“不伪造真实模型输出”的责任说明。
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from '../src/App'

function jsonResponse(payload: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => payload } as Response
}

const HEALTH = {
  status: 'ok',
  app_name: 'SceneWeave',
  app_version: '0.1.0',
  contract_version: 'm00.1',
  run_state: 'READY',
  analysis_enabled: false,
  model_configured: false,
}

function mockBackend(overrides: Record<string, unknown> = {}) {
  const routes: Record<string, unknown> = {
    '/api/health': HEALTH,
    '/api/scenes/presets': { presets: [] },
    '/api/templates': { templates: [] },
    '/api/scenes': { scenes: [] },
    ...overrides,
  }
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    for (const [pattern, payload] of Object.entries(routes)) {
      if (url.includes(pattern)) {
        return jsonResponse(payload)
      }
    }
    return jsonResponse({ error: 'not_found' }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('应用外壳', () => {
  it('显示产品名称与三个页面入口', async () => {
    mockBackend()
    render(<App />)

    // 等首屏请求落地，避免测试结束后仍有状态更新（act 警告）。
    await waitFor(() => {
      expect(screen.getByText(/契约版本/)).toBeInTheDocument()
    })
    expect(screen.getByRole('heading', { name: 'SceneWeave' })).toBeInTheDocument()
    expect(screen.getByText('角色互动沙盒')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '配置' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '聊天' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '历史' })).toBeInTheDocument()
  })

  it('切换到聊天页时给出可执行的下一步，而不是假内容', async () => {
    mockBackend()
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: '聊天' }))

    await waitFor(() => {
      expect(screen.getByText('还没有打开会话')).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: '用预置场景创建会话' })).toBeInTheDocument()
  })

  it('后端不可用时明确指出，而不是显示假完成态', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('connect ECONNREFUSED')
      }),
    )
    render(<App />)

    await waitFor(() => {
      expect(screen.getByText(/后端未连接/)).toBeInTheDocument()
    })
  })

  it('页脚声明契约版本与“无模拟输出”的责任边界', async () => {
    mockBackend()
    render(<App />)

    expect(await screen.findByText(/契约版本 m00.1/)).toBeInTheDocument()
    expect(screen.getByText(/界面中不存在冒充真实模型输出的模拟结果/)).toBeInTheDocument()
  })
})
