-- PC: legacy messages remain PUBLIC, schema 1; no rewrite of prior migration.
ALTER TABLE messages ADD COLUMN visibility TEXT NOT NULL DEFAULT 'PUBLIC' CHECK (visibility IN ('PUBLIC', 'PRIVATE'));
ALTER TABLE messages ADD COLUMN recipient_id TEXT;
ALTER TABLE messages ADD COLUMN conversation_id TEXT;
ALTER TABLE messages ADD COLUMN schema_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE scene_turns ADD COLUMN recipient_id TEXT;
CREATE INDEX idx_messages_conversation ON messages (scene_id, conversation_id, seq);
