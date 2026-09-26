/**
 * SSE 订阅（PRD 第 8 节、7.1）。
 *
 * 规则：
 * - 只按 `seq` 追加**已提交**条目，并按 `seq` 去重（断线重连靠 `since_seq` 追赶）；
 * - 心跳是注释行，EventSource 不会把它当作消息，因此不会进入剧情；
 * - 生成中（收到新发言）只是刷新数据，**不伪造**“模型正在思考”的内容。
 */

import { useEffect, useRef, useState } from 'react'

import { streamUrl, type TimelineEntryView } from '../api/client'

export interface SceneStreamState {
  readonly entries: TimelineEntryView[]
  readonly lastSeq: number
  readonly connected: boolean
  readonly error: string | null
}

export interface StreamMessage {
  readonly kind: 'message' | 'event'
  readonly seq: number
  readonly payload: Record<string, unknown>
  readonly author_name?: string | null
}

/** 允许测试注入 EventSource 实现（jsdom 不提供）。 */
export type EventSourceFactory = (url: string) => EventSource

const defaultFactory: EventSourceFactory = (url) => new EventSource(url)

export function useSceneStream(
  sceneId: string | null,
  initialSeq: number,
  factory: EventSourceFactory = defaultFactory,
): SceneStreamState {
  const [entries, setEntries] = useState<TimelineEntryView[]>([])
  const [lastSeq, setLastSeq] = useState(initialSeq)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const seqRef = useRef(initialSeq)

  useEffect(() => {
    if (sceneId === null) {
      setEntries([])
      setLastSeq(initialSeq)
      seqRef.current = initialSeq
      setConnected(false)
      return
    }

    setEntries([])
    seqRef.current = initialSeq
    setLastSeq(initialSeq)

    const source = factory(streamUrl(sceneId, initialSeq))

    const onTimeline = (raw: MessageEvent) => {
      let parsed: StreamMessage
      try {
        parsed = JSON.parse(raw.data) as StreamMessage
      } catch {
        setError('收到无法解析的推送数据')
        return
      }
      // 按 seq 去重：重连后可能重复收到同一条。
      if (parsed.seq <= seqRef.current) {
        return
      }
      seqRef.current = parsed.seq
      setLastSeq(parsed.seq)
      setEntries((previous) => [...previous, toEntry(parsed)])
    }

    source.addEventListener('timeline', onTimeline as EventListener)
    source.addEventListener('open', () => {
      setConnected(true)
      setError(null)
    })
    source.addEventListener('error', () => {
      setConnected(false)
      // EventSource 会自行重连；这里不自动停止后台场景（PRD 5.4）。
      setError('SSE 连接中断，正在重连（后台场景不会因此停止）')
    })
    source.addEventListener('closed', () => {
      setConnected(false)
    })

    return () => {
      source.removeEventListener('timeline', onTimeline as EventListener)
      source.close()
    }
  }, [sceneId, initialSeq, factory])

  return { entries, lastSeq, connected, error }
}

function toEntry(message: StreamMessage): TimelineEntryView {
  return {
    kind: message.kind,
    seq: message.seq,
    message: message.kind === 'message' ? (message.payload as never) : null,
    event: message.kind === 'event' ? (message.payload as never) : null,
    author_name: message.author_name ?? null,
  }
}
