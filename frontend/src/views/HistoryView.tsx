/** 共用 Scene 集合与 ChatView，只读筛选不触发模型。 */
import { useEffect, useState } from 'react'
import { listScenes, type SceneMode, type SceneSummaryView } from '../api/client'
import { readView, saveView } from '../lib/viewState'
import { modeLabel } from '../lib/modes'
import { ChatView } from './ChatView'

export interface HistoryViewProps {
  readonly sceneId: string | null
  readonly modelConfigured: boolean | null
  readonly onSelectScene: (sceneId: string) => void
}

export function HistoryView({ sceneId, modelConfigured, onSelectScene }: HistoryViewProps) {
  const [filter, setFilter] = useState<SceneMode | ''>(() => {
    const saved = readView<string>('history-mode', '')
    return saved === 'simulation' || saved === 'discussion' ? saved : ''
  })
  const [scenes, setScenes] = useState<SceneSummaryView[]>([])
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    let active = true
    setLoading(true)
    setError(null)
    setScenes([])
    saveView('history-mode', filter)
    listScenes(controller.signal, filter || undefined)
      .then(value => { if (active) setScenes(value.scenes) })
      .catch(cause => { if (active) setError(String(cause)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false; controller.abort() }
  }, [filter, revision])
  const filteredScenes = scenes.filter(s => !filter || s.mode === filter)
  const visibleId = !loading && filteredScenes.some(s => s.scene_id === sceneId) ? sceneId : null
  return <div>
    <section className="card" aria-label="历史筛选">
      <h2>历史会话</h2>
      <label className="field"><span>观察模式</span>
        <select aria-label="历史模式筛选" value={filter} onChange={e => setFilter(e.target.value as SceneMode | '')}>
          <option value="">全部</option><option value="simulation">情境模拟</option><option value="discussion">议题讨论</option>
        </select>
      </label>
      <button type="button" onClick={() => setRevision(v => v + 1)}>刷新历史</button>
      {error ? <p className="state state--error">{error}</p> : null}
      {loading ? <p>读取历史…</p> : <ul>{filteredScenes.map(scene => <li key={scene.scene_id} className="row">
        <span>{scene.title} · {modeLabel[scene.mode ?? 'simulation']}</span>
        <button type="button" onClick={() => onSelectScene(scene.scene_id)}>回看</button>
      </li>)}</ul>}
      {!loading && !scenes.length ? <p className="hint">此筛选下还没有会话。</p> : null}
    </section>
    <ChatView key={`${visibleId}:${revision}`} sceneId={visibleId} readOnly modelConfigured={modelConfigured} onSelectScene={onSelectScene} />
  </div>
}
