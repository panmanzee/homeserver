-- taskbot schema. Apply against the dedicated `taskbot` database.
-- Safe to re-run; the app applies it on every boot.

CREATE TABLE IF NOT EXISTS tasks (
    id               bigserial PRIMARY KEY,
    title            text NOT NULL,
    notes            text,
    status           text NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'done', 'cancelled')),
    due_date         date,                    -- untimed task "for a day"
    scheduled_start  timestamptz,             -- set for timed items ("gym at 11pm")
    scheduled_end    timestamptz,
    estimate_minutes integer,
    gcal_event_id    text,                    -- NULL until synced to the Tasks calendar
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    completed_at     timestamptz
);
CREATE INDEX IF NOT EXISTS tasks_open_idx ON tasks (due_date)
    WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS bot_state (
    id            integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    tg_offset     bigint NOT NULL DEFAULT 0,   -- next getUpdates offset
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS google_oauth (
    id             integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    refresh_token  text NOT NULL,
    calendar_id    text NOT NULL,
    updated_at     timestamptz NOT NULL DEFAULT now()
);

-- optional audit trail; handy while tuning the parser prompt
CREATE TABLE IF NOT EXISTS message_log (
    id            bigserial PRIMARY KEY,
    direction     text NOT NULL CHECK (direction IN ('in', 'out')),
    tg_message_id bigint,
    text          text,
    intent        jsonb,
    created_at    timestamptz NOT NULL DEFAULT now()
);

INSERT INTO bot_state (id, tg_offset) VALUES (1, 0) ON CONFLICT (id) DO NOTHING;
