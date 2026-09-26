/**
 * 历史页（PRD 7.1、5.4）。
 *
 * 复用聊天页的**只读模式**：只读取已保存数据，不调用模型，也不提供运行控制。
 */

import { ChatView } from './ChatView'

export interface HistoryViewProps {
  readonly sceneId: string | null
  readonly modelConfigured: boolean | null
  readonly onSelectScene: (sceneId: string) => void
}

export function HistoryView({ sceneId, modelConfigured, onSelectScene }: HistoryViewProps) {
  return (
    <ChatView
      sceneId={sceneId}
      readOnly
      modelConfigured={modelConfigured}
      onSelectScene={onSelectScene}
    />
  )
}
