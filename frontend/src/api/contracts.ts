/**
 * 契约的运行时视图。
 *
 * - **类型**来自后端 OpenAPI 生成的 `schema.d.ts`（唯一来源）。
 * - **取值**来自后端导出的 `contract-summary.json`（由同一个契约层生成）。
 *
 * 因此前端不会与后端各自维护一套枚举；发现不一致时应重新运行
 * `scripts/export_contracts.sh`，而不是在前端手工补齐。
 */

import type { components } from './generated/schema'
import summaryJson from './generated/contract-summary.json'

export type ContractSummary = components['schemas']['ContractSummary']
export type EnumSummary = components['schemas']['EnumSummary']

export type ActionType = components['schemas']['ActionType']
export type EventVisibility = components['schemas']['EventVisibility']
export type EventStatus = components['schemas']['EventStatus']
export type RunState = components['schemas']['RunState']
export type PauseReason = components['schemas']['PauseReason']
export type ControlCommandType = components['schemas']['ControlCommandType']
export type TurnStatus = components['schemas']['TurnStatus']
export type ModelFailureKind = components['schemas']['ModelFailureKind']
export type AnalysisStatus = components['schemas']['AnalysisStatus']
export type SchedulerReason = components['schemas']['SchedulerReason']

export type ActionDraft = components['schemas']['ActionDraft']
export type Event = components['schemas']['Event']
export type Message = components['schemas']['Message']
export type AgentTemplate = components['schemas']['AgentTemplate']
export type Scene = components['schemas']['Scene']
export type ModelActionResponse = components['schemas']['ModelActionResponse']
export type AnalysisReport = components['schemas']['AnalysisReport']

/** 由后端导出的契约摘要；形状由 OpenAPI 类型约束。 */
export const contractSummary = summaryJson as unknown as ContractSummary

/** 读取某个枚举的全部取值；缺失时返回空数组（由契约测试保证不缺失）。 */
export function enumValues(name: string): readonly string[] {
  return contractSummary.enums.find((item: EnumSummary) => item.name === name)?.values ?? []
}

/**
 * 按 Unicode 码点计数的长度上限。
 *
 * 键必须与后端 `CONTRACT_LIMIT_CODEPOINTS` 完全一致——由
 * `tests/contracts.test.ts` 显式核对，缺失即为缺陷。
 */
export interface CodepointLimits {
  readonly agent_name: number
  readonly persona: number
  readonly speech_style: number
  readonly initial_goal: number
  readonly private_background: number
  readonly scene_background: number
  readonly event_body: number
  readonly speak_text: number
  readonly analysis_behavior_description: number
  readonly analysis_context: number
  readonly max_prompt_chars: number
}

export const codepointLimits: CodepointLimits =
  contractSummary.limit_codepoints as unknown as CodepointLimits

/** 角色数量范围 2～8（PRD 1.2）。 */
export const agentCountRange = contractSummary.agent_count

/** 每场预算上限（PRD 5.3）。 */
export const budgets = contractSummary.budgets

/** 首版的两个外部端口（PRD 第 8 节）。 */
export const externalPorts: readonly string[] = contractSummary.ports

export const runStates: readonly string[] = contractSummary.run_states
