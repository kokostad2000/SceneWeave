import { useCallback, useEffect, useState } from 'react'

import { fetchHealth, listScenes, type SceneSummaryView } from './api/client'
import { contractSummary } from './api/contracts'
import { ChatView } from './views/ChatView'
import { ConfigView } from './views/ConfigView'
import { HistoryView } from './views/HistoryView'

type Tab = 'config' | 'chat' | 'history'

const TABS: { key: Tab; label: string }[] = [
  { key: 'config', label: '配置' },
  { key: 'chat', label: '聊天' },
  { key: 'history', label: '历史' },
]

/**
 * SceneWeave 应用外壳。
 *
 * 三个视图对应 PRD 7.1 的页面结构：配置页、聊天页（时间线 + 角色侧栏 + 底部控制 +
 * 分析抽屉）、历史页（聊天页只读模式）。视图切换与历史查看都**不调用模型**。
 */
export function App() {
  const [tab, setTab] = useState<Tab>('config')
  const [sceneId, setSceneId] = useState<string | null>(null)
  const [scenes, setScenes] = useState<SceneSummaryView[]>([])
  const [modelConfigured, setModelConfigured] = useState<boolean | null>(null)
  const [backendError, setBackendError] = useState<string | null>(null)

  const refreshScenes = useCallback(async () => {
    try {
      const list = await listScenes()
      setScenes(list.scenes)
      setBackendError(null)
    } catch (cause) {
      setBackendError(cause instanceof Error ? cause.message : String(cause))
    }
  }, [])

  useEffect(() => {
    fetchHealth()
      .then((health) => setModelConfigured(health.model_configured))
      .catch(() => setModelConfigured(null))
    refreshScenes().catch(() => undefined)
  }, [refreshScenes])

  const openScene = useCallback(
    (id: string) => {
      setSceneId(id)
      setTab('chat')
      refreshScenes().catch(() => undefined)
    },
    [refreshScenes],
  )

  return (
    <div className="page">
      <header className="page__header">
        <h1>SceneWeave</h1>
        <p className="page__subtitle">角色互动沙盒</p>
        <nav className="tabs" aria-label="页面">
          {TABS.map((item) => (
            <button
              key={item.key}
              type="button"
              className={tab === item.key ? 'tab tab--active' : 'tab'}
              onClick={() => setTab(item.key)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </header>

      {backendError ? (
        <p className="state state--error">
          后端未连接：{backendError}。请在 <code>backend/</code> 运行
          <code> uv run uvicorn role_theater.main:app --port 8000</code>。
        </p>
      ) : null}

      {tab === 'config' ? (
        <ConfigView onOpenScene={openScene} />
      ) : tab === 'chat' ? (
        <>
          {scenes.length > 0 ? (
            <label className="field">
              <span>当前会话</span>
              <select
                aria-label="当前会话"
                value={sceneId ?? ''}
                onChange={(event) => setSceneId(event.target.value === '' ? null : event.target.value)}
              >
                <option value="">选择会话…</option>
                {scenes.map((scene) => (
                  <option key={scene.scene_id} value={scene.scene_id}>
                    {scene.title}（{scene.agent_count} 名角色，{scene.status}）
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <ChatView sceneId={sceneId} modelConfigured={modelConfigured} onSelectScene={openScene} />
        </>
      ) : (
        <HistoryView sceneId={sceneId} modelConfigured={modelConfigured} onSelectScene={setSceneId} />
      )}

      <footer className="page__footer">
        <p className="hint">
          契约版本 {contractSummary.contract_version}｜外部端口 {contractSummary.ports.join('、')}｜
          长度校验按 Unicode 码点计数，与后端一致。
        </p>
        <p className="hint">
          已实现 M00–M04（工程与契约、角色与场景、可见性与调度、模型适配、运行与事件）。
          行为分析结果展示与发布资料属后续模块；界面中不存在冒充真实模型输出的模拟结果。
        </p>
      </footer>
    </div>
  )
}

export default App
