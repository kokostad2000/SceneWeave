-- Additive upgrade: preserve all old records and request evidence verbatim.
ALTER TABLE scenes ADD COLUMN mode TEXT NOT NULL DEFAULT 'simulation'
    CHECK(mode IN ('simulation', 'discussion'));
ALTER TABLE scenes ADD COLUMN mode_config_json TEXT;
ALTER TABLE agent_templates ADD COLUMN public_profile TEXT NOT NULL DEFAULT '';
ALTER TABLE scene_agents ADD COLUMN snapshot_public_profile TEXT NOT NULL DEFAULT '';
ALTER TABLE scene_agents ADD COLUMN discussion_config_json TEXT;
CREATE INDEX idx_scenes_mode ON scenes(mode, created_at);
