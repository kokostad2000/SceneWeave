/**
 * 角色视角（PRD 7.2）。
 *
 * 直接展示后端 `GET /agents/{id}/viewpoint` 返回的上下文——它与调用器**实际使用**
 * 的是同一份 ContextBuilder 输出，因此前端不会、也不允许再实现一套权限。
 */

import { useEffect, useState } from 'react'

import { fetchViewpoint, type ViewpointView } from '../api/client'

export interface ViewpointPanelProps {
  readonly sceneId: string
  readonly agentId: string
  readonly agentName: string
}

export function ViewpointPanel({ sceneId, agentId, agentName }: ViewpointPanelProps) {
  const [viewpoint, setViewpoint] = useState<ViewpointView | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    setViewpoint(null)
    setError(null)
    fetchViewpoint(sceneId, agentId, controller.signal)
      .then(setViewpoint)
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : String(cause))
        }
      })
    return () => controller.abort()
  }, [sceneId, agentId])

  return (
    <section className="panel" aria-label={`角色视角：${agentName}`}>
      <h2>角色视角：{agentName}</h2>
      <p className="hint">
        下面就是调用模型时实际使用的上下文（同一份构建结果），不是前端另行推算的权限视图。
      </p>
      {error ? <p className="state state--error">{error}</p> : null}
      {viewpoint ? (
        <>
          <dl className="facts">
            <dt>提示模板</dt>
            <dd>{viewpoint.prompt_template_id}</dd>
            <dt>输入快照截止序号</dt>
            <dd>#{viewpoint.cutoff_seq}</dd>
            <dt>公开名册</dt>
            <dd>{viewpoint.public_roster.join('、')}</dd>
            <dt>可见条目</dt>
            <dd>
              {viewpoint.visible_seq.length === 0
                ? '（暂无）'
                : viewpoint.visible_seq.map((seq, index) => `#${seq} ${viewpoint.visible_kinds[index]}`).join('，')}
            </dd>
          </dl>
          <pre className="prompt-view">{viewpoint.prompt}</pre>
        </>
      ) : !error ? (
        <p className="hint">正在读取…</p>
      ) : null}
    </section>
  )
}
