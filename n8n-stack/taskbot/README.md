# taskbot

A single-user Telegram bot that turns plain-language messages ("gym at 11pm",
"done with the math homework", "what's today") into a managed task list, an
optional Google Calendar mirror, and a proactive morning plan / evening review.
Sibling service to `newsfeed-api/` in the `n8n-stack`.

## It already works

Once the stack is deployed (`docker compose up -d taskbot`), taskbot is a fully
usable task manager **with zero setup** — it reuses the stack's
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `SERVICE_API_KEY`, and the same LLM
provider settings as `newsfeed-api` (`LLM_PROVIDER`, default `gemini`, with
`GEMINI_API_KEY`; set `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` to use
Claude instead). Just open Telegram and text the bot. It only ever responds to
messages from `TELEGRAM_CHAT_ID` and silently ignores every other chat.

A web app is also available — see [Web app](#web-app) below.

The two things below are optional polish:

1. **Timezone** — until you set it, the bot runs on UTC and says so in its first
   reply and every morning plan.
2. **Google Calendar mirror** — until you set it up, all task management and the
   morning/evening messages work over Telegram; only the calendar sync is
   skipped. Even once configured, sync is **opt-in per task** — see below.

## 1. Set the timezone (recommended, no calendar needed)

Edit the stack `.env` (`~/homeserver/n8n-stack/.env`):

```bash
cd ~/homeserver/n8n-stack
# set TASKBOT_TZ to your IANA zone, e.g. Asia/Bangkok
sed -i 's/^TASKBOT_TZ=.*/TASKBOT_TZ=Asia\/Bangkok/' .env
docker compose restart taskbot
```

`TASKBOT_TZ` drives all "today" / "tomorrow" / "11pm" resolution and the cron
times for the morning plan (`TASKBOT_MORNING_TIME`, default `07:30`) and evening
review (`TASKBOT_EVENING_TIME`, default `21:00`). An invalid zone falls back to
UTC with a warning.

## 2. Google Calendar mirror (optional, opt-in per task)

This is the **only** part of setup that needs you at a browser — it can't be
automated on the headless box. When configured, tasks/events are mirrored to a
dedicated secondary calendar called **Tasks** (the bot never reads or touches
your primary calendar) — but **only when you explicitly ask for it**. A plain
`gym at 6pm` or `math homework tomorrow` stays app-only (Telegram + the
[web app](#web-app)). Say `gym at 6pm, add it to my calendar` (or, for a task
you already added, `put the gym one on my calendar`, or tap the 📅 button in
the web app) to sync that one. Once a task is on the calendar, editing it
(reschedule / rename / convert / complete / delete) keeps the calendar entry in
sync automatically — you don't have to re-ask each time.

### 2a. Google Cloud project

1. Create a project at <https://console.cloud.google.com/>.
2. **Enable the Google Calendar API** for the project.
3. **OAuth consent screen**: User type "External". Then **click "Publish app" /
   set it to "In production"** — a single-user self-use app needs no Google
   verification, and leaving it in "Testing" makes the refresh token expire
   after 7 days.
4. **Credentials → Create credentials → OAuth client ID → application type
   "Desktop app"**. Note the **client id** and **client secret**.
5. Put them in the box `.env`:

   ```
   GOOGLE_CLIENT_ID=...apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=...
   ```

### 2b. Authorize (run once, on a laptop with a browser)

The box has no browser, so run the one-time OAuth flow on your laptop from a
checkout of this repo:

```bash
cd n8n-stack/taskbot
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
GOOGLE_CLIENT_ID=...apps.googleusercontent.com \
GOOGLE_CLIENT_SECRET=... \
  .venv/bin/python -m app.authorize
```

It opens your browser, you approve, and it prints two lines. It also
creates (or finds) the **Tasks** calendar and prints its id:

```
--- paste into the box .env ---
GOOGLE_REFRESH_TOKEN=1//0g...
GOOGLE_CALENDAR_ID=abc123@group.calendar.google.com
```

### 2c. Enable it on the box

Paste those two lines into `~/homeserver/n8n-stack/.env` and restart:

```bash
cd ~/homeserver/n8n-stack
docker compose restart taskbot
```

Calendar sync is now live. `gcal` reads `GOOGLE_REFRESH_TOKEN`,
`GOOGLE_CALENDAR_ID`, `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` straight from
the environment — nothing is copied into the database. (A `google_oauth` table
exists in the schema for a future version that will manage the token in-DB, but
the current code does not read or write it in production.)

If a token refresh ever fails, the failure is **logged, not DMed** — the bot
keeps working for everything except the calendar. If calendar events stop
appearing, check `docker compose logs taskbot` for a `gcal sync failed` line and
re-run `python -m app.authorize` on a machine with a browser to mint a fresh
`GOOGLE_REFRESH_TOKEN`.

## Message vocabulary

You only ever type plain sentences. There are no slash commands. The bot uses an
LLM (Gemini by default, Claude optional) to map each message to an ordered list
of these actions:

| You say | Action | Effect |
| --- | --- | --- |
| `math homework today` / `finish the report` | add task | untimed task on a day (default: today); **app-only** unless you say "add to calendar" |
| `gym at 11pm` / `call mom tomorrow 14:30` | add event | timed task (default 60 min); **app-only** unless you say "add to calendar" |
| `gym at 6pm, add it to my calendar` | add event (opt-in) | same as above, plus a timed calendar event right away |
| `put the gym one on my calendar` | calendar sync | syncs an *existing* task/event to the calendar with no other change |
| `done with the gym` / `finished the homework` | complete | marks it done; if already on the calendar, event renamed `✓ <title>` |
| `delete the math homework` / `cancel the call` | delete | cancels the task; if already on the calendar, event removed |
| `move gym to 9pm` / `reschedule the report to friday` | reschedule | updates the slot; if already on the calendar, event patched — otherwise stays app-only |
| `what's today` / `show my day` / `what do i have tomorrow` | list day | replies with that day's tasks and timed items |
| `make the gym all-day` / `rename "call mom" to "call mom about tickets"` | convert / rename | flips a timed event to an all-day task, or changes a task's wording; keeps syncing if already on the calendar |
| anything unclear | (a question) | replies asking which task / what you meant; no state change |

You can put several things in one message (`watch a video all day, gym at 6pm,
buy milk`) and correct the bot in your next message (`no, make the gym 7pm`) —
it remembers the last few turns and edits what it just did.

For complete / delete / reschedule / convert / rename the model matches your
words against your open tasks. If nothing matches, or two match equally, the bot
asks which one.

## Web app

A day-planner web page lives at the same service, reachable anywhere over
Tailscale (no LAN exposure, no separate login — the tailnet is the perimeter,
same as `rag-api`):

**<https://pan-homeserver.tail9ee4c5.ts.net:8448/>**

It shows a 7-day date strip, the day's timed and all-day items, a text box that
runs the exact same natural-language pipeline as Telegram (so it shares
history, logging, and the calendar opt-in rule below), and per-task
checkbox-to-complete, 📅-to-sync, ×-to-delete controls. Works on phone or
desktop, light/dark follows your system theme, no app install.

Because it's the same backend, **anything typed in the web app or in Telegram
behaves identically** — including the calendar opt-in rule: new tasks/events
stay app-only until you explicitly say "add to calendar" or tap 📅.

## How it's wired

```
Telegram  ──getUpdates (long poll, 30s)──▶  poller  ──▶  plan (Gemini / Claude)
   ▲                                                          │
   └── sendMessage ◀── reply ◀── actions (tasks table) ◀──────┘
                                     │
                                     ▼
                        gcal client (optional) ──▶ Google "Tasks" calendar

APScheduler ──▶ morning plan (07:30) · evening review (21:00)
```

- **poller** — async background task; `getUpdates(offset, timeout=30)` in a
  loop, persists the offset in `bot_state` so a restart never drops or
  reprocesses a message; drops any chat that isn't `TELEGRAM_CHAT_ID`.
- **planner** — one structured LLM call per message (Gemini `response_schema` by
  default, or a Claude tool-use call when `LLM_PROVIDER=anthropic`): message +
  recent turns + open tasks → an ordered list of actions. Strict JSON, validated
  with pydantic; any provider error degrades to a polite "having trouble" reply
  and the poller keeps running.
- **actions** — pure functions over the `taskbot` Postgres database (own DB,
  schema applied idempotently on every boot); `execute_plan` runs the planned
  actions in order — `add_task` / `add_event` / `complete` / `delete` /
  `reschedule` / `convert` (timed → all-day) / `rename` / `list_day` — and
  returns a reply line per action plus the rows to mirror to the calendar.
- **gcal** — `google-auth` + `google-api-python-client`; credentials come
  straight from the `GOOGLE_*` env vars. Every function is a no-op when
  `GOOGLE_REFRESH_TOKEN` is unset, a refresh/API error is logged and swallowed
  (never breaks a reply), and the mirror is one-way (tasks → calendar only).
- **scheduler** — APScheduler cron jobs pinned to `TASKBOT_TZ`: morning plan
  and evening review. There is **no nightly rollover**: a task keeps its date
  and simply stays on the board, flagged "N days late", until it is ticked or
  removed (`db.carried_over`). Tasks with no date at all are "anytime" tasks
  (`db.anytime_tasks`) and also stay until done. `jobs.rollover_unfinished`
  still exists but is no longer scheduled.

Every inbound and outbound message is written to `message_log` for prompt
tuning; rows older than `TASKBOT_LOG_RETENTION_DAYS` (default 30) are pruned by a
nightly 03:30 job.

### HTTP endpoints

Bound to `127.0.0.1:8002` on the host (localhost / n8n only — no public
exposure).

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/healthz` | none | `{"status":"ok"}` — DB ping |
| `POST` | `/jobs/morning-plan` | `X-API-Key: $SERVICE_API_KEY` | run the morning plan now (sends the Telegram message) |
| `POST` | `/jobs/evening-review` | `X-API-Key: $SERVICE_API_KEY` | run the evening review now |
| `GET` | `/` | none | the [web app](#web-app) page |
| `GET` | `/api/tasks?day=YYYY-MM-DD` | none (tailnet-only) | that day's tasks as JSON, with a computed `synced` flag |
| `GET` | `/api/board?day=YYYY-MM-DD` | none (tailnet-only) | one screen for the UI: `day_tasks`, plus (when `day` is today) `carried` (late, with `late_days`) and `anytime`; `done` = completed that day |
| `POST` | `/api/tasks` | none (tailnet-only) | `{"title", "due_date"}` instant add, no LLM; `due_date: null` = anytime |
| `PATCH` | `/api/tasks/{id}` | none (tailnet-only) | `{"title"?, "due_date"?}` rename / move; `due_date: null` = anytime; timed tasks can't be moved here |
| `POST` | `/api/tasks/{id}/restore` | none (tailnet-only) | undo a tick or a removal |
| `POST` | `/api/message` | none (tailnet-only) | `{"text": "..."}` → runs the same pipeline as Telegram, returns `{"reply": ...}` |
| `POST` | `/api/tasks/{id}/complete` | none (tailnet-only) | mark a task done |
| `DELETE` | `/api/tasks/{id}` | none (tailnet-only) | cancel a task |
| `POST` | `/api/tasks/{id}/calendar` | none (tailnet-only) | sync an existing task to Google Calendar now |

```bash
curl -s http://127.0.0.1:8002/healthz
KEY=$(grep -E '^SERVICE_API_KEY=' ~/homeserver/n8n-stack/.env | cut -d= -f2)
curl -s -X POST -H "X-API-Key: $KEY" http://127.0.0.1:8002/jobs/morning-plan
```

## Tests

```bash
cd ~/homeserver/n8n-stack/taskbot
.venv/bin/python -m pytest -q
```

All externals are mocked (monkeypatched `httpx.post` for Telegram, a fake
Gemini / Anthropic client, a fake gcal client; `respx` is in
`requirements-dev.txt` and available for future HTTP-level tests). The DB-layer tests are skipped unless
`TASKBOT_TEST_DB_URL` points at a scratch Postgres database.
