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
} from '../api/client'
import { codepointLimits } from '../api/contracts'
import { trimmedCodepointLength } from '../lib/codepoints'

const EMPTY_TEMPLATE = {
  name: '',
  persona: '',
  speech_style: '',
  initial_goal: '',
  private_background: '',
}

export interface ConfigViewProps {
  readonly onOpenScene: (sceneId: string) => void
}

export function ConfigView({ onOpenScene }: ConfigViewProps) {
  const [templates, setTemplates] = useState<AgentTemplate[]>([])
  const [scenes, setScenes] = useState<SceneSummaryView[]>([])
  const [presets, setPresets] = useState<PresetSummaryView[]>([])
  const [draft, setDraft] = useState({ ...EMPTY_TEMPLATE })
  const [editingId, setEditingId] = useState<string | null>(null)
  const [title, setTitle] = useState('三个室友的客厅')
  const [background, setBackground] = useState('晚上，三个室友在客厅相遇，尚未确定今晚做什么。')
  const [selectedTemplates, setSelectedTemplates] = useState<string[]>([])
  const [maxRoleRequests, setMaxRoleRequests] = useState('24')
  const [maxAnalysisRequests, setMaxAnalysisRequests] = useState('4')
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

      <section className="card">
        <h2>角色模板</h2>
        <ul className="template-list">
          {templates.map((template) => (
            <li key={template.template_id} className="row">
              <span>{template.name}</span>
              <span className="row__actions">
                <button
                  type="button"
                  onClick={() => {
                    setEditingId(template.template_id)
                    setDraft({
                      name: template.name,
                      persona: template.persona,
                      speech_style: template.speech_style,
                      initial_goal: template.initial_goal,
                      private_background: template.private_background,
                    })
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
          {templates.length === 0 ? <li className="hint">还没有模板，可在下方新建或直接用预置场景。</li> : null}
        </ul>

        <h3>{editingId ? "编辑模板" : "新建模板"}</h3>
        <div className="grid">
          {(
            [
              ['name', '名称', codepointLimits.agent_name],
              ['persona', '人物设定', codepointLimits.persona],
              ['speech_style', '表达习惯', codepointLimits.speech_style],
              ['initial_goal', '初始目标', codepointLimits.initial_goal],
              ['private_background', '私有背景', codepointLimits.private_background],
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
        <div className="row">
          <span>
            <button
              type="button"
              disabled={draft.name.trim() === ''}
              onClick={() =>
                guard(async () => {
                  if (editingId) {
                    const updated = await updateTemplate(editingId, draft)
                    setMessage(`已更新模板：${updated.name}`)
                    setEditingId(null)
                  } else {
                    const created = await createTemplate(draft)
                    setMessage(`已创建模板：${created.name}`)
                  }
                  setDraft({ ...EMPTY_TEMPLATE })
                  await refresh()
                })
              }
            >
              {editingId ? '保存修改' : '创建模板'}
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
        <h2>创建本场会话</h2>
        <label className="field">
          <span>场景标题</span>
          <input aria-label="场景标题" value={title} onChange={(event) => setTitle(event.target.value)} />
        </label>
        <label className="field">
          <span>
            场景背景（{trimmedCodepointLength(background)}／{codepointLimits.scene_background} 码点）
          </span>
          <textarea
            aria-label="场景背景"
            value={background}
            onChange={(event) => setBackground(event.target.value)}
          />
        </label>

        <fieldset>
          <legend>选择本场角色（2～8 名，当前 {selectedTemplates.length} 名）</legend>
          {templates.map((template) => (
            <label key={template.template_id} className="row">
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
              </span>
            </label>
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
              const detail = await createScene({
                title,
                background,
                agents: selectedTemplates.map((templateId) => ({ template_id: templateId })),
                max_role_requests: Number(maxRoleRequests),
                max_analysis_requests: Number(maxAnalysisRequests),
              })
              setCurrent(detail)
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
            {current.locked ? '已锁定' : '未锁定'}
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
