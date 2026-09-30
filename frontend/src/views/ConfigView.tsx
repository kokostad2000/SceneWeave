/**
 * 配置页（PRD 3.1、3.2、5.3、7.1）。
 *
 * 流程：打开预置场景 → 添加或修改角色 → 创建本场会话。
 * 配置期**不调用模型**（PRD 3.1），这里全部是 M01 接口。
 */

import { useEffect, useState } from 'react'

import {
  addAgent,
  copyTemplate,
  createScene,
  createPresetScene,
  createTemplate,
  deleteTemplate,
  getScene,
  listPresets,
  listScenes,
  listTemplates,
  removeAgent,
  renameAgent,
  updateTemplate,
  type AgentTemplate,
  type SceneDetailView,
  type PresetSummaryView,
  type SceneSummaryView,
  type SceneMode,
  type DiscussionParticipantConfig,
  type SceneRoleProfile,
} from '../api/client'
import { budgets, codepointLimits, agentCountRange } from '../api/contracts'
import { trimmedCodepointLength } from '../lib/codepoints'
import { modeLabel } from '../lib/modes'
import { RoleProfileEditor, emptyRoleProfile, roleProfileOverLimit } from '../components/RoleProfileEditor'

const EMPTY_TEMPLATE = { name: '' }

export interface ConfigViewProps {
  readonly onOpenScene: (sceneId: string) => void
}

export function ConfigView({ onOpenScene }: ConfigViewProps) {
  const [mode, setMode] = useState<SceneMode>('simulation')
  const [publicInformation, setPublicInformation] = useState('')
  const [topic, setTopic] = useState('')
  const [materials, setMaterials] = useState('')
  const [participants, setParticipants] = useState<Record<string, DiscussionParticipantConfig>>({})
  const [profiles, setProfiles] = useState<Record<string, SceneRoleProfile>>({})
  const [templates, setTemplates] = useState<AgentTemplate[]>([])
  const [scenes, setScenes] = useState<SceneSummaryView[]>([])
  const [presets, setPresets] = useState<PresetSummaryView[]>([])
  const [draft, setDraft] = useState({ ...EMPTY_TEMPLATE })
  const [editingId, setEditingId] = useState<string | null>(null)
  const [title, setTitle] = useState('三个室友的客厅')
  const [background, setBackground] = useState('晚上，三个室友在客厅相遇，尚未确定今晚做什么。')
  const [selectedTemplates, setSelectedTemplates] = useState<string[]>([])
  // 默认预算来自后端契约摘要（人工裁决 2026-09-26：角色请求默认上调为 200），
  // 前端不再手写这个数字，避免与服务端默认值漂移。
  const [maxRoleRequests, setMaxRoleRequests] = useState(
    String(budgets.max_role_requests_per_scene),
  )
  const [maxAnalysisRequests, setMaxAnalysisRequests] = useState(
    String(budgets.max_analysis_requests_per_scene),
  )
  const [current, setCurrent] = useState<SceneDetailView | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function refresh() {
    const [templateList, sceneList, presetList] = await Promise.all([
      listTemplates(),
      listScenes(),
      listPresets(),
    ])
    setTemplates(templateList.templates ?? [])
    setScenes(sceneList.scenes ?? [])
    setPresets(presetList.presets ?? [])
  }

  useEffect(() => {
    refresh().catch((cause: unknown) => setError(String(cause)))
  }, [])

  async function guard(action: () => Promise<void>) {
    setError(null)
    setMessage(null)
    try {
      await action()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    }
  }

  const overLimit = (value: string, limit: number) => trimmedCodepointLength(value) > limit

  return (
    <div className="view view--config">
      <section className="card" aria-label="选择观察模式">
        <h2>想观察什么？</h2>
        <div className="mode-choices">
          <button type="button" aria-pressed={mode === 'simulation'} onClick={() => { setMode('simulation'); setCurrent(null) }}>
            <b>角色互动沙盒</b><span>创建情境，观察角色的信息、交流与行为如何发展</span>
          </button>
          <button type="button" aria-pressed={mode === 'discussion'} onClick={() => { setMode('discussion'); setCurrent(null) }}>
            <b>议题聊天室</b><span>给出议题，观察观点、论据、分歧与共识如何演变</span>
          </button>
        </div>
        <p className="hint">当前创建：{modeLabel[mode]}。创建后模式固定，两种模式共用交流与运行控制。</p>
      </section>
      {mode === 'simulation' ? (
      <section className="card">
        <h2>预置场景</h2>
        {presets.map((preset) => (
          <div key={preset.key} className="row">
            <span>
              <b>{preset.title}</b>（{preset.agent_names.join('、')}）
              <span className="hint"> {preset.background}</span>
            </span>
            <button
              type="button"
              onClick={() =>
                guard(async () => {
                  const detail = await createPresetScene(preset.key)
                  setCurrent(detail)
                  setMessage(`已用预置场景创建会话：${detail.scene.title}`)
                  await refresh()
                })
              }
            >
              用预置场景创建会话
            </button>
          </div>
        ))}
      </section>
      ) : null}

      <section className="card">
        <h2>人物目录</h2>
        <p className="hint">选择人物只复用名称；公开身份、人设、目标与背景在本场填写。旧版设定保留供历史兼容，不自动带入新场景。</p>
        <ul className="template-list">
          {templates.map((template) => (
            <li key={template.template_id} className="row">
              <span>{template.name}</span>
              <span className="row__actions">
                <button
                  type="button"
                  onClick={() => {
                    setEditingId(template.template_id)
                    setDraft({ name: template.name })
                  }}
                >
                  编辑
                </button>
                <button
                  type="button"
                  onClick={() =>
                    guard(async () => {
                      await copyTemplate(template.template_id)
                      await refresh()
                    })
                  }
                >
                  复制
                </button>
                <button
                  type="button"
                  onClick={() =>
                    guard(async () => {
                      await deleteTemplate(template.template_id)
                      setSelectedTemplates((previous) =>
                        previous.filter((item) => item !== template.template_id),
                      )
                      await refresh()
                    })
                  }
                >
                  移除
                </button>
              </span>
            </li>
          ))}
          {templates.length === 0 ? <li className="hint">还没有人物，可在下方新建或使用预置场景。</li> : null}
        </ul>

        <h3>{editingId ? "编辑人物名称" : "新建人物"}</h3>
        <div className="grid">
          {(
            [
              ['name', '名称', codepointLimits.agent_name],
            ] as const
          ).map(([key, label, limit]) => (
            <label key={key} className="field">
              <span>
                {label}（{trimmedCodepointLength(draft[key])}／{limit} 码点）
              </span>
              <input
                aria-label={label}
                value={draft[key]}
                onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
                className={overLimit(draft[key], limit) ? 'input--invalid' : undefined}
              />
            </label>
          ))}
        </div>
        <p className="hint">人物目录不预填行为设定；所有本场资料可留空。</p>
        <div className="row">
          <span>
            <button
              type="button"
              disabled={draft.name.trim() === ''}
              onClick={() =>
                guard(async () => {
                  if (editingId) {
                    const updated = await updateTemplate(editingId, draft)
                    setMessage(`已更新人物：${updated.name}`)
                    setEditingId(null)
                  } else {
                    const created = await createTemplate(draft)
                    setMessage(`已创建人物：${created.name}`)
                  }
                  setDraft({ ...EMPTY_TEMPLATE })
                  await refresh()
                })
              }
            >
              {editingId ? '保存修改' : '创建人物'}
            </button>
            {editingId ? (
              <button
                type="button"
                onClick={() => {
                  setEditingId(null)
                  setDraft({ ...EMPTY_TEMPLATE })
                }}
              >
                取消编辑
              </button>
            ) : null}
          </span>
        </div>
      </section>

      <section className="card">
        <h2>创建本场会话 · {modeLabel[mode]}</h2>
        <label className="field"><span>场景标题</span>
          <input aria-label="场景标题" value={title} onChange={e => setTitle(e.target.value)} />
        </label>
        {mode === 'simulation' ? <>
          <label className="field"><span>场景背景（{trimmedCodepointLength(background)}／{codepointLimits.scene_background} 码点）</span>
            <textarea aria-label="场景背景" value={background} onChange={e => setBackground(e.target.value)} />
          </label>
          <label className="field"><span>公共信息（全场公开）</span>
            <textarea aria-label="公共信息" value={publicInformation} onChange={e => setPublicInformation(e.target.value)} />
          </label>
        </> : <>
          <label className="field"><span>议题（必填，全场公开）</span><textarea aria-label="议题" value={topic} onChange={e => setTopic(e.target.value)} /></label>
          <label className="field"><span>背景／材料（可空，全场公开）</span><textarea aria-label="背景／材料" value={materials} onChange={e => setMaterials(e.target.value)} /></label>
        </>}
        <p className="hint">公共场景输入合计最多 {codepointLimits.scene_background} 码点（含字段间换行）。</p>

        <fieldset>
          <legend>选择本场角色（2～8 名，当前 {selectedTemplates.length} 名）</legend>
          {templates.map((template) => (
            <div key={template.template_id}>
            <label className="row">
              <span>
                <input
                  type="checkbox"
                  checked={selectedTemplates.includes(template.template_id)}
                  onChange={() =>
                    setSelectedTemplates((previous) =>
                      previous.includes(template.template_id)
                        ? previous.filter((item) => item !== template.template_id)
                        : [...previous, template.template_id],
                    )
                  }
                />{' '}
                {template.name}
                <small>仅复用人物名称</small>
              </span>
            </label>
            {selectedTemplates.includes(template.template_id) ? <RoleProfileEditor name={template.name}
              value={profiles[template.template_id] ?? emptyRoleProfile()}
              onChange={value => setProfiles(prev => ({ ...prev, [template.template_id]: value }))} /> : null}
            {mode === 'discussion' && selectedTemplates.includes(template.template_id) ? <div className="grid participant-fields">
              <label className="field"><span>关注点（可空，仅 {template.name} 本人可见）</span>
                <textarea aria-label={`${template.name}的讨论关注点`} value={participants[template.template_id]?.focus ?? ''}
                  onChange={e => setParticipants(prev => ({ ...prev, [template.template_id]: { ...prev[template.template_id], focus: e.target.value } }))} />
              </label>
              <label className="field"><span>初始观点（可空、可调整，仅 {template.name} 本人可见）</span>
                <textarea aria-label={`${template.name}的初始观点`} value={participants[template.template_id]?.initial_position ?? ''}
                  onChange={e => setParticipants(prev => ({ ...prev, [template.template_id]: { focus: prev[template.template_id]?.focus ?? "", initial_position: e.target.value || null } }))} />
              </label>
            </div> : null}
            </div>
          ))}
        </fieldset>

        <div className="grid">
          <label className="field">
            <span>角色请求上限</span>
            <input
              aria-label="角色请求上限"
              type="number"
              value={maxRoleRequests}
              onChange={(event) => setMaxRoleRequests(event.target.value)}
            />
          </label>
          <label className="field">
            <span>分析请求上限</span>
            <input
              aria-label="分析请求上限"
              type="number"
              value={maxAnalysisRequests}
              onChange={(event) => setMaxAnalysisRequests(event.target.value)}
            />
          </label>
        </div>

        <button
          type="button"
          onClick={() =>
            guard(async () => {
              const publicText = (mode === 'simulation' ? [background, publicInformation] : [topic, materials]).map(v => v.trim()).filter(Boolean).join('\n')
              if (!title.trim()) throw new Error('场景标题不能为空')
              if (mode === 'discussion' && !topic.trim()) throw new Error('议题不能为空')
              if (overLimit(publicText, codepointLimits.scene_background)) throw new Error('公共场景输入超过码点上限')
              if (selectedTemplates.length < agentCountRange.min! || selectedTemplates.length > agentCountRange.max!) throw new Error('请选择 2～8 名角色')
              if (mode === 'discussion' && selectedTemplates.some(id => overLimit(participants[id]?.focus ?? '', codepointLimits.discussion_focus) || overLimit(participants[id]?.initial_position ?? '', codepointLimits.initial_position))) throw new Error('讨论关注点或初始观点超过码点上限')
              if (selectedTemplates.some(id => roleProfileOverLimit(profiles[id] ?? emptyRoleProfile()))) throw new Error('本场设定超过码点上限')
              const detail = await createScene({
                configuration_version: 2,
                chat_policy_version: 2,
                title,
                background: publicText,
                mode,
                mode_config: mode === 'simulation' ? { situation: background, public_information: publicInformation } : { topic, materials },
                agents: selectedTemplates.map((templateId) => ({ template_id: templateId, role_profile: profiles[templateId] ?? emptyRoleProfile(),
                  ...(mode === 'discussion' ? { discussion_config: participants[templateId] ?? { focus: '', initial_position: null } } : {}) })),
                max_role_requests: Number(maxRoleRequests),
                max_analysis_requests: Number(maxAnalysisRequests),
              })
              setCurrent(detail)
              onOpenScene(detail.scene.scene_id)
              setMessage(`已创建会话：${detail.scene.title}（${detail.agents.length} 名角色）`)
              await refresh()
            })
          }
        >
          创建会话
        </button>
        <p className="hint">预算上限在创建时设定，首次角色请求开始后锁定。</p>
      </section>

      {current ? (
        <section className="card">
          <h2>本场角色（{current.scene.title}）</h2>
          <p className="hint">
            模板快照已冻结：之后修改模板不会影响本场。锁定状态：
            {current.locked ? '已锁定' : '未锁定'} · {(current.scene.configuration_version ?? 1) === 2 ? '本场独立设定' : '旧版模板快照'}
          </p>
          <ul>
            {current.agents.map((agent) => (
              <li key={agent.agent_id} className="row">
                <span>
                  {agent.name}（来自模板「{agent.snapshot.name}」）
                </span>
                <span className="row__actions">
                  <button
                    type="button"
                    onClick={() =>
                      guard(async () => {
                        const name = window.prompt('新的角色名称', agent.name)
                        if (!name) return
                        await renameAgent(current.scene.scene_id, agent.agent_id, name)
                        setCurrent(await getScene(current.scene.scene_id))
                      })
                    }
                  >
                    改名
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      guard(async () => {
                        await removeAgent(current.scene.scene_id, agent.agent_id)
                        setCurrent(await getScene(current.scene.scene_id))
                      })
                    }
                  >
                    移除
                  </button>
                </span>
              </li>
            ))}
          </ul>

          <div className="row">
            <select
              aria-label="从模板新增角色"
              value=""
              onChange={(event) =>
                guard(async () => {
                  if (event.target.value === '') return
                  await addAgent(current.scene.scene_id, { template_id: event.target.value })
                  setCurrent(await getScene(current.scene.scene_id))
                })
              }
            >
              <option value="">从模板新增角色…</option>
              {templates.map((template) => (
                <option key={template.template_id} value={template.template_id}>
                  {template.name}
                </option>
              ))}
            </select>
            <button type="button" onClick={() => onOpenScene(current.scene.scene_id)}>
              进入聊天页
            </button>
          </div>
        </section>
      ) : null}

      <section className="card">
        <h2>历史会话</h2>
        <ul>
          {scenes.map((scene) => (
            <li key={scene.scene_id} className="row">
              <span>
                {scene.title}（{scene.agent_count} 名角色，{scene.status}
                {scene.budget_locked ? '，预算已锁定' : ''}）
              </span>
              <button type="button" onClick={() => onOpenScene(scene.scene_id)}>
                打开
              </button>
            </li>
          ))}
          {scenes.length === 0 ? <li className="hint">还没有会话。</li> : null}
        </ul>
      </section>

      {message ? <p className="state state--ok">{message}</p> : null}
      {error ? <p className="state state--error">{error}</p> : null}
    </div>
  )
}
