-- 连续点名次数属于场景；旧角色计数无法准确还原全场连续调度历史。
-- 升级从 0 起算，保留既有消息、行动、游标位置与预算。
CREATE TABLE scene_scheduler_state (
    scene_id TEXT PRIMARY KEY REFERENCES scenes (scene_id) ON DELETE CASCADE,
    consecutive_requested_priority INTEGER NOT NULL DEFAULT 0
        CHECK (consecutive_requested_priority BETWEEN 0 AND 2)
);

INSERT INTO scene_scheduler_state (scene_id, consecutive_requested_priority)
SELECT scene_id, 0 FROM scenes;

UPDATE role_cursors SET consecutive_requested_priority = 0;
