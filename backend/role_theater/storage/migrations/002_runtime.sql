-- M04 运行时 schema：事件、消息、行动、游标、预算与命令幂等。
--
-- 设计要点（PRD 4.3 / 5.1～5.4）：
--   * 消息与事件共享场景内单调 seq：由 scene_seq 在同一事务内原子自增；
--   * scene_turns 的 PENDING 行同时承担「占用预算」「标记在途」「崩溃恢复依据」；
--   * message_id 唯一索引防止一份成功行动重复成为公开消息（PRD 5.4）；
--   * scene_commands 以 request_id 为主键实现命令幂等（PRD 5.4）。

CREATE TABLE scene_seq (
    scene_id TEXT    PRIMARY KEY REFERENCES scenes (scene_id) ON DELETE CASCADE,
    last_seq INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE messages (
    message_id           TEXT    PRIMARY KEY,
    scene_id             TEXT    NOT NULL REFERENCES scenes (scene_id) ON DELETE CASCADE,
    seq                  INTEGER NOT NULL,
    actor_id             TEXT    NOT NULL,
    text                 TEXT    NOT NULL,
    reply_to_message_id  TEXT,
    requested_speaker_id TEXT,
    created_at           TEXT    NOT NULL,
    UNIQUE (scene_id, seq)
);

CREATE INDEX idx_messages_scene_seq ON messages (scene_id, seq);

CREATE TABLE events (
    event_id         TEXT    PRIMARY KEY,
    scene_id         TEXT    NOT NULL REFERENCES scenes (scene_id) ON DELETE CASCADE,
    -- 已接受但尚未生效的事件不占序号（NULL），生效时按接受顺序分配。
    seq              INTEGER,
    body             TEXT    NOT NULL,
    visibility       TEXT    NOT NULL CHECK (visibility IN ('ALL', 'TARGETED')),
    target_agent_id  TEXT,
    status           TEXT    NOT NULL CHECK (status IN ('ACCEPTED', 'EFFECTIVE')),
    schema_version   INTEGER NOT NULL,
    accepted_order   INTEGER NOT NULL,
    accepted_at      TEXT    NOT NULL,
    effective_at     TEXT,
    UNIQUE (scene_id, seq),
    UNIQUE (scene_id, accepted_order)
);

CREATE INDEX idx_events_scene_seq ON events (scene_id, seq);

CREATE TABLE scene_turns (
    action_id            TEXT    PRIMARY KEY,
    turn_id              TEXT    NOT NULL,
    attempt_id           TEXT    NOT NULL UNIQUE,
    scene_id             TEXT    NOT NULL REFERENCES scenes (scene_id) ON DELETE CASCADE,
    actor_id             TEXT    NOT NULL,
    status               TEXT    NOT NULL
        CHECK (status IN ('PENDING', 'SUCCEEDED', 'FAILED', 'UNKNOWN')),
    action               TEXT,
    text                 TEXT,
    reply_to_message_id  TEXT,
    requested_speaker_id TEXT,
    message_id           TEXT    REFERENCES messages (message_id),
    input_cursor_seq     INTEGER NOT NULL,
    prompt_template_id   TEXT    NOT NULL,
    requested_model      TEXT,
    returned_model       TEXT,
    provider_request_id  TEXT,
    input_tokens         INTEGER,
    output_tokens        INTEGER,
    cached_tokens        INTEGER,
    usage_unknown        INTEGER NOT NULL DEFAULT 1 CHECK (usage_unknown IN (0, 1)),
    failure_kind         TEXT,
    failure_detail       TEXT,
    sent                 INTEGER NOT NULL DEFAULT 1 CHECK (sent IN (0, 1)),
    budget_consumed      INTEGER NOT NULL DEFAULT 1 CHECK (budget_consumed IN (0, 1)),
    latency_ms           INTEGER,
    created_at           TEXT    NOT NULL,
    finished_at          TEXT
);

-- 一份成功行动只能产生一条公开消息（PRD 5.4）。
CREATE UNIQUE INDEX idx_turns_message_id ON scene_turns (message_id) WHERE message_id IS NOT NULL;
CREATE INDEX idx_turns_scene_created ON scene_turns (scene_id, created_at);
CREATE INDEX idx_turns_pending ON scene_turns (status) WHERE status = 'PENDING';

CREATE TABLE role_cursors (
    scene_id                      TEXT    NOT NULL REFERENCES scenes (scene_id) ON DELETE CASCADE,
    agent_id                      TEXT    NOT NULL,
    processed_seq                 INTEGER NOT NULL DEFAULT 0,
    startup_opportunity_consumed  INTEGER NOT NULL DEFAULT 0
        CHECK (startup_opportunity_consumed IN (0, 1)),
    last_action_at                TEXT,
    last_action_status            TEXT,
    consecutive_requested_priority INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (scene_id, agent_id)
);

CREATE TABLE scene_budget_usage (
    scene_id                TEXT    PRIMARY KEY REFERENCES scenes (scene_id) ON DELETE CASCADE,
    role_requests_used      INTEGER NOT NULL DEFAULT 0,
    analysis_requests_used  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE scene_commands (
    request_id     TEXT    PRIMARY KEY,
    scene_id       TEXT    NOT NULL REFERENCES scenes (scene_id) ON DELETE CASCADE,
    command        TEXT    NOT NULL,
    response_json  TEXT    NOT NULL,
    created_at     TEXT    NOT NULL
);

CREATE INDEX idx_commands_scene ON scene_commands (scene_id, created_at);
