import type { AgentSnapshot, SceneRoleProfile } from '../api/client'
import { codepointLimits } from '../api/contracts'
import { trimmedCodepointLength } from '../lib/codepoints'

const fields = [
  ['public_profile', '公开身份／自我介绍', codepointLimits.public_profile],
  ['persona', '人物设定', codepointLimits.persona],
  ['speech_style', '表达习惯', codepointLimits.speech_style],
  ['initial_goal', '初始目标', codepointLimits.initial_goal],
  ['private_background', '私有背景', codepointLimits.private_background],
] as const

export function emptyRoleProfile(): SceneRoleProfile {
  return { public_profile: '', persona: '', speech_style: '', initial_goal: '', private_background: '' }
}

export function profileFromSnapshot(snapshot: AgentSnapshot): SceneRoleProfile {
  return { public_profile: snapshot.public_profile, persona: snapshot.persona,
    speech_style: snapshot.speech_style, initial_goal: snapshot.initial_goal,
    private_background: snapshot.private_background }
}

export function roleProfileOverLimit(profile: SceneRoleProfile): boolean {
  return fields.some(([key, , limit]) => trimmedCodepointLength(profile[key] ?? '') > limit)
}

export function RoleProfileEditor({ name, value, onChange }: {
  name: string; value: SceneRoleProfile; onChange: (value: SceneRoleProfile) => void
}) {
  return <fieldset className="participant-fields">
    <legend>{name}的本场设定（均可空）</legend>
    <div className="grid">{fields.map(([key, label, limit]) => <label className="field" key={key}>
      <span>{label} · {key === 'public_profile' ? '全场公开' : '仅本人可见'}（{trimmedCodepointLength(value[key] ?? '')}／{limit} 码点）</span>
      <textarea aria-label={`${name}的本场${label}`} value={value[key] ?? ''}
        onChange={event => onChange({ ...value, [key]: event.target.value })} />
    </label>)}</div>
  </fieldset>
}
