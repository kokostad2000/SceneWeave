-- Preserve existing snapshots and legacy semantics.
ALTER TABLE scenes ADD COLUMN configuration_version INTEGER NOT NULL DEFAULT 1 CHECK(configuration_version IN (1, 2));
