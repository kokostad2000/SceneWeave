-- Existing scenes keep their original rules; new scenes explicitly store policy 2.
ALTER TABLE scenes ADD COLUMN chat_policy_version INTEGER NOT NULL DEFAULT 1
    CHECK (chat_policy_version IN (1, 2));
ALTER TABLE role_cursors ADD COLUMN last_success_order INTEGER NOT NULL DEFAULT 0
    CHECK (last_success_order >= 0);
ALTER TABLE role_cursors ADD COLUMN last_success_action TEXT
    CHECK (last_success_action IN ('SPEAK', 'PRIVATE', 'PASS'));
