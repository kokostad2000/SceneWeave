import type { FactStatisticsView } from '../api/client'

export function RecordFacts({ facts, unavailable = false }: { readonly facts: FactStatisticsView | null; readonly unavailable?: boolean }) {
  if (!facts) return <p className="hint">{unavailable ? '记录事实暂时无法读取，请刷新重试。' : '记录事实正在读取…'}</p>
  return <section className="card" aria-label="记录事实">
    <h3>记录事实{facts.viewer_id ? ' · 本人可见集合' : ' · 观察者'}</h3>
    <p>公开消息 {facts.public_messages} · 私聊消息 {facts.private_messages} · 明确回复 {facts.reply_relations.length} · 参与角色 {facts.participant_ids.length}</p>
    <ul>{facts.role_actions.map(role => <li key={role.agent_id}>
      {role.name}：成功行动 {role.succeeded}（公共发言 {role.public_speaks}／主动私聊 {role.private_initiations}／回复私聊 {role.private_replies}／沉默 {role.passes}）；失败 {role.failed}／结果不明 {role.unknown}
    </li>)}</ul>
    <p className="hint">只统计已保存记录，不解释信任、情绪或态度，也不影响角色互动。</p>
  </section>
}
