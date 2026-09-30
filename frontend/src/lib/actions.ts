import type { ActionDraft } from '../api/client'

export function actionLabel(draft: ActionDraft | null | undefined, names: ReadonlyMap<string, string>): string {
  if (!draft) return '暂无'
  if (draft.action === 'PASS') return '沉默'
  if (draft.action === 'SPEAK') return '公共发言'
  const name = names.get(draft.recipient_id ?? '') ?? '另一角色'
  return draft.reply_to_message_id ? `回复${name}私聊` : `私聊${name}`
}
