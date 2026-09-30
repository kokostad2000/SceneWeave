import type { ConversationView } from '../api/client'

export function ConversationMenu({ conversations, channel, onSelect }: {
  readonly conversations: readonly ConversationView[]
  readonly channel: string
  readonly onSelect: (channel: string) => void
}) {
  return <nav className="conversation-menu card" aria-label="交流频道">
    <h3>交流</h3>
    <button type="button" aria-current={channel === 'public' ? 'page' : undefined} onClick={() => onSelect('public')}>公共频道</button>
    <details open><summary>私聊</summary>
      <ul>{conversations.map(c => <li key={c.conversation_id}>
        <button type="button" aria-current={channel === c.conversation_id ? 'page' : undefined} onClick={() => onSelect(c.conversation_id)}>
          {c.participant_names.join(' ↔ ')}
        </button>
      </li>)}</ul>
      {conversations.length === 0 ? <p className="hint">暂无私聊会话</p> : null}
    </details>
    <button type="button" aria-current={channel === 'all' ? 'page' : undefined} onClick={() => onSelect('all')}>全场时间线</button>
  </nav>
}
