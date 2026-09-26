/**
 * 时间线（PRD 7.1、7.2）。
 *
 * - 完整消息显示，**不做逐字流式渲染**；
 * - 普通台词、公开事件、定向事件、待生效事件、停止原因样式各不相同；
 * - 文本由 React 转义渲染，不执行模型或事件中的 HTML／脚本；
 * - 被最新发言点名的角色只是**高亮**，不伪造“正在思考”的内容。
 */

import type { TimelineEntryView } from '../api/client'
import { EVENT_VISIBILITY_LABELS } from '../lib/labels'

export interface TimelineListProps {
  readonly entries: readonly TimelineEntryView[]
  readonly requestedAgentName?: string | null
  readonly pendingEventIds?: readonly string[]
}

export function TimelineList({ entries, requestedAgentName, pendingEventIds = [] }: TimelineListProps) {
  if (entries.length === 0) {
    return <p className="hint">还没有公开信息。使用下方运行控制开始，或插入一个事件。</p>
  }

  return (
    <ol className="timeline" data-testid="timeline">
      {entries.map((entry) => {
        if (entry.kind === 'message' && entry.message) {
          const message = entry.message
          const highlighted = requestedAgentName !== null && requestedAgentName !== undefined
            && message.requested_speaker_id !== null
            && message.requested_speaker_id !== undefined
          return (
            <li key={`m-${message.seq}`} className="timeline__item timeline__item--message">
              <div className="timeline__meta">
                <span className="timeline__seq">#{message.seq}</span>
                <span className="timeline__author">{entry.author_name ?? message.actor_id}</span>
                {message.reply_to_message_id ? (
                  <span className="tag tag--reply">回复某条发言</span>
                ) : null}
                {highlighted ? <span className="tag tag--requested">点名希望接话</span> : null}
              </div>
              <p className="bubble">{message.text}</p>
            </li>
          )
        }

        const event = entry.event
        if (!event) {
          return null
        }
        const pending = pendingEventIds.includes(event.event_id) || event.status === 'ACCEPTED'
        const classes = [
          'timeline__item',
          'timeline__item--event',
          event.visibility === 'TARGETED' ? 'timeline__item--targeted' : '',
          pending ? 'timeline__item--pending' : '',
        ]
          .filter(Boolean)
          .join(' ')

        return (
          <li key={`e-${event.event_id}`} className={classes}>
            <div className="timeline__meta">
              <span className="timeline__seq">{event.seq === null ? '待生效' : `#${event.seq}`}</span>
              <span className="timeline__author">操作者事件</span>
              <span className="tag tag--visibility">
                {EVENT_VISIBILITY_LABELS[event.visibility] ?? event.visibility}
              </span>
              {pending ? <span className="tag tag--pending">已接受（待生效）</span> : null}
            </div>
            <p className="bubble bubble--event">{event.body}</p>
          </li>
        )
      })}
    </ol>
  )
}
