import { describe, expect, it } from 'vitest'

import {
  contractSummary,
  enumValues,
  externalPorts,
  runStates,
  type ActionType,
  type RunState,
} from '../src/api/contracts'

describe('契约摘要（由后端导出，前端不手写枚举）', () => {
  it('显示名与契约版本来自后端契约层', () => {
    expect(contractSummary.app_name).toBe('SceneWeave')
    expect(contractSummary.contract_version).toBe('m00.1')
    expect(contractSummary.schema_version).toBe(1)
  })

  it('运行状态与 PRD 5.2 完全一致', () => {
    expect(runStates).toEqual(['READY', 'RUNNING', 'PAUSING', 'STOPPING', 'PAUSED', 'ENDED'])
  })

  it('行动协议枚举与 PRD 4.2 一致', () => {
    expect(enumValues('ActionType')).toEqual(['SPEAK', 'PASS'])
    expect(enumValues('TurnStatus')).toEqual(['SUCCEEDED', 'FAILED', 'UNKNOWN'])
  })

  it('事件可见性与状态与 PRD 4.3 一致', () => {
    expect(enumValues('EventVisibility')).toEqual(['ALL', 'TARGETED'])
    expect(enumValues('EventStatus')).toEqual(['ACCEPTED', 'EFFECTIVE'])
  })

  it('分析状态五种可区分（PRD 6.2）', () => {
    expect(enumValues('AnalysisStatus')).toEqual([
      'NORMAL',
      'BLOCKED',
      'DEGRADED',
      'FAILED',
      'DISABLED',
    ])
  })

  it('模型失败分类覆盖空输出与截断', () => {
    const kinds = enumValues('ModelFailureKind')

    expect(kinds).toContain('EMPTY_CONTENT')
    expect(kinds).toContain('TRUNCATED')
    expect(kinds).toContain('INVALID_JSON')
    expect(kinds).toContain('UNKNOWN_REQUEST')
  })

  it('只有两个外部端口（不建通用插件系统）', () => {
    expect(externalPorts).toEqual(['ModelPort', 'AnalysisPort'])
  })

  it('长度上限与预算与 PRD 一致', () => {
    expect(contractSummary.limit_codepoints.speak_text).toBe(200)
    expect(contractSummary.limit_codepoints.agent_name).toBe(30)
    expect(contractSummary.limit_codepoints.scene_background).toBe(2000)
    expect(contractSummary.agent_count).toEqual({ min: 2, max: 8, default: 3 })
    expect(contractSummary.budgets.max_role_requests_per_scene).toBe(24)
    expect(contractSummary.budgets.max_analysis_requests_per_scene).toBe(4)
  })

  it('运行参数初值来自后端契约', () => {
    expect(contractSummary.model_params.model).toBe('deepseek-flash')
    expect(contractSummary.model_params.sdk_max_retries).toBe(0)
    expect(contractSummary.model_params.max_output_tokens).toBe(1024)
    expect(contractSummary.model_params.request_timeout_seconds).toBe(90)
    expect(contractSummary.model_params.thinking_enabled).toBe(false)
  })

  it('生成的联合类型可使用契约取值（类型层一致性）', () => {
    const state: RunState = 'PAUSED'
    const action: ActionType = 'PASS'

    expect([state, action]).toEqual(['PAUSED', 'PASS'])
  })
})
