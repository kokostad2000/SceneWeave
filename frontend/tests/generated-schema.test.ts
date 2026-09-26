import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

// vitest 在 jsdom 环境下 `import.meta.url` 不是 file:// 协议，因此用工作目录定位
// （测试命令固定从 `frontend/` 运行）。
const schemaPath = resolve(process.cwd(), 'src/api/generated/schema.d.ts')

/**
 * 生成产物必须提交并且覆盖**完整**契约层，而不只是 M00 的两个路由；否则
 * M01～M06 的前端类型会各自手写，违反 PRD 第 8 节。
 */
describe('OpenAPI 生成的 TypeScript 类型', () => {
  const source = readFileSync(schemaPath, 'utf8')

  it('包含 M00 路由的响应类型', () => {
    expect(source).toContain('HealthResponse')
    expect(source).toContain('ContractSummary')
  })

  it('包含行动与事件结构', () => {
    expect(source).toContain('ActionDraft')
    expect(source).toContain('ActionRecord')
    expect(source).toContain('Event:')
    expect(source).toContain('EventSubmission')
  })

  it('包含两个外部端口的请求／响应结构', () => {
    expect(source).toContain('ModelActionRequest')
    expect(source).toContain('ModelActionResponse')
    expect(source).toContain('AnalysisRequest')
    expect(source).toContain('AnalysisReport')
  })

  it('包含 M01 角色模板与场景配置的结构', () => {
    for (const model of [
      'TemplateCreateRequest',
      'TemplateUpdateRequest',
      'TemplateCopyRequest',
      'TemplateListView',
      'AgentSpecRequest',
      'SceneCreateRequest',
      'PresetSceneCreateRequest',
      'PresetSummaryView',
      'SceneSummaryView',
      'SceneListView',
      'SceneDetailView',
      'AgentCreateRequest',
      'AgentRenameRequest',
    ]) {
      expect(source).toContain(model)
    }
  })

  it('M01 场景创建请求把角色建模为数组，而不是固定字段', () => {
    // 角色是集合：不使用 agent1／agent2／agent3 之类固定字段（PRD 3.2）。
    expect(source).toContain('agents: components["schemas"]["AgentSpecRequest"][]')
    expect(source).not.toMatch(/\bagent\d\b/)
  })

  it('M01 场景详情返回角色集合与锁定标记', () => {
    expect(source).toContain('locked: boolean')
    expect(source).toContain('agents: components["schemas"]["SceneAgent"][]')
  })

  it('包含全部枚举取值', () => {
    for (const value of ['SPEAK', 'PASS', 'TARGETED', 'EFFECTIVE', 'PAUSING', 'DEGRADED']) {
      expect(source).toContain(value)
    }
  })

  it('不包含任何密钥或环境变量名', () => {
    expect(source).not.toContain('api_key')
    expect(source).not.toContain('SCENEWEAVE_')
  })
})
