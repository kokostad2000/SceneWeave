-- M06 行为分析记录。
--
-- 设计约束（PRD 6.1 / 6.2 / 5.3）：
--   * 记录由本项目按 scene_id / agent_id 隔离；
--   * **不写外部画像**：persist_profile 强制关闭，因此这里没有画像表；
--   * provider_attempts 与实际发送一致：本地边界拦截时为 0（PRD 5.3）；
--   * 分析记录**不进入**角色上下文，也不触发调度——它只被只读接口读取。

CREATE TABLE analysis_records (
    analysis_id          TEXT    PRIMARY KEY,
    scene_id             TEXT    NOT NULL REFERENCES scenes (scene_id) ON DELETE CASCADE,
    agent_id             TEXT    NOT NULL,
    status               TEXT    NOT NULL
        CHECK (status IN ('NORMAL', 'BLOCKED', 'DEGRADED', 'FAILED', 'DISABLED')),
    -- 选中的材料（JSON 数组：kind / source_id / author_agent_id / text），保留原文与来源。
    materials_json       TEXT    NOT NULL DEFAULT '[]',
    material_seqs_json   TEXT    NOT NULL DEFAULT '[]',
    behavior_description TEXT    NOT NULL DEFAULT '',
    context              TEXT    NOT NULL DEFAULT '',
    report_json          TEXT    NOT NULL,
    provider_attempts    INTEGER NOT NULL DEFAULT 0,
    degradation_flags    TEXT    NOT NULL DEFAULT '[]',
    input_tokens         INTEGER,
    output_tokens        INTEGER,
    cached_tokens        INTEGER,
    error                TEXT,
    created_at           TEXT    NOT NULL
);

CREATE INDEX idx_analysis_scene_agent ON analysis_records (scene_id, agent_id, created_at);
