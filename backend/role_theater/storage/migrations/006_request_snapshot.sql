-- New requests preserve exact model input and alias table; historical evidence remains untouched.
ALTER TABLE scene_turns ADD COLUMN request_snapshot_json TEXT;
