-- M01 初始 schema：角色模板、场景、本场角色快照。
--
-- 设计约束（PRD 1.2 / 3.2 / 8）：
--   * 角色是**集合**：scene_agents 每行一个角色，绝不使用 agent1/agent2/agent3 固定列；
--   * 本场角色保存模板快照 + 模板来源 ID，因此 source_template_id **不设外键**：
--     模板被移除后，已有场景的快照必须继续可用；
--   * scenes.schema_version 现在就写入，避免日后回填（PRD 第 8 节）。

CREATE TABLE agent_templates (
    template_id        TEXT    PRIMARY KEY,
    name               TEXT    NOT NULL,
    persona            TEXT    NOT NULL,
    speech_style       TEXT    NOT NULL,
    initial_goal       TEXT    NOT NULL,
    private_background TEXT    NOT NULL,
    is_preset          INTEGER NOT NULL DEFAULT 0 CHECK (is_preset IN (0, 1)),
    created_at         TEXT    NOT NULL,
    updated_at         TEXT    NOT NULL
);

-- 模板名称唯一（见 tasks/M01.md §3.6 I1）。
CREATE UNIQUE INDEX idx_agent_templates_name ON agent_templates (name);

CREATE TABLE scenes (
    scene_id              TEXT    PRIMARY KEY,
    title                 TEXT    NOT NULL,
    background            TEXT    NOT NULL,
    status                TEXT    NOT NULL
        CHECK (status IN ('READY', 'RUNNING', 'PAUSING', 'STOPPING', 'PAUSED', 'ENDED')),
    pause_reason          TEXT,
    schema_version        INTEGER NOT NULL,
    max_role_requests     INTEGER NOT NULL,
    max_analysis_requests INTEGER NOT NULL,
    -- 非空表示预算与人物设定已锁定（PRD 3.2 / 5.3）。
    budget_locked_at      TEXT,
    preset_key            TEXT,
    created_at            TEXT    NOT NULL,
    started_at            TEXT,
    ended_at              TEXT
);

CREATE INDEX idx_scenes_created_at ON scenes (created_at DESC);

CREATE TABLE scene_agents (
    agent_id                    TEXT    PRIMARY KEY,
    scene_id                    TEXT    NOT NULL
        REFERENCES scenes (scene_id) ON DELETE CASCADE,
    name                        TEXT    NOT NULL,
    order_index                 INTEGER NOT NULL,
    source_template_id          TEXT    NOT NULL,
    snapshot_name               TEXT    NOT NULL,
    snapshot_persona            TEXT    NOT NULL,
    snapshot_speech_style       TEXT    NOT NULL,
    snapshot_initial_goal       TEXT    NOT NULL,
    snapshot_private_background TEXT    NOT NULL,
    snapshot_captured_at        TEXT    NOT NULL,
    created_at                  TEXT    NOT NULL,
    -- 同一场景内名称不可重复（PRD 3.2）；agent_id 才是关联主键。
    UNIQUE (scene_id, name),
    UNIQUE (scene_id, order_index)
);

CREATE INDEX idx_scene_agents_scene ON scene_agents (scene_id, order_index);
