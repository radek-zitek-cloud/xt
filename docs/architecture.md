# xt architecture: how it works

What the code does as of **v0.15.0** (2026-09-29), after real runs with a newsroom team and xt's
own product team, and the fixes they led to. Release-by-release changes are in
[CHANGELOG.md](../CHANGELOG.md); how to use xt is in the [user guide](user-guide.md).

## In one paragraph

xt runs a hierarchical team of AI agents, each in its own [Herdr](https://herdr.dev) workspace, in
any harness Herdr supports (claude, codex, pi, ...). The human talks to one agent, the
**liaison**. The liaison turns requests into **goals** for the **lead**. The lead designs the team,
writes its roles and skills, and gets members hired and tasked. Agents never talk to each other
directly and never call Herdr themselves: they run `xt` commands that only write files in the team's
repo. A **supervisor** process (`xt watch`) does everything that touches Herdr or the human's
desktop: delivering messages, starting and stopping agents, waking scheduled agents, watching
liveness, and alerting and notifying the human. The team's whole state (roster, roles, skills,
goals, the message log) is in the repo, so any agent can lose its memory and recover.

## The pieces

```
 human ──(types in its pane)──▶ liaison ──goal──▶ lead ──task──▶ members
   ▲  │                            │  ▲             ▲               │
   │  │ xt tui / inbox / answer /  │  └──── report / done ──────────┘
   │  │ approve / status           │ question (ask to the human)
   │  ▼                            ▼
 ┌─────────────── team repo (a clone of xt, owned by the user) ───────────────┐
 │ team.toml  roles/  skills/  goals/  members/        .xt/ (runtime, ignored) │
 │   log/*.jsonl (message log = ledger)   state/ queue, jobs, approvals, …    │
 └──────────────────────────────▲───────────────────────────────▲──────────────┘
          agents' `xt …` commands│ write files only               │ reads/writes
                                 │                    ┌───────────┴───────────┐
   desktop notifications ◀───────┼────────────────────│ xt watch (supervisor) │── Herdr CLI ──▶ Herdr
   (questions, approvals, alerts)│                    └───────────────────────┘   (--session <team>)
```

| Piece | What it is |
|---|---|
| **Herdr** | Runs the terminal panes, starts harnesses (`agent start --kind`), tells xt each agent's state (idle, working, blocked, done), and injects prompts. Every xt call is `herdr --session <team session> …`, so xt never depends on inherited `HERDR_*` environment variables. |
| **`bin/xt`** | Launcher. Runs the repo's own `.venv` (re-synced from `uv.lock` when that changes), and keeps uv's cache inside the repo, since some sandboxes can't write `~/.cache`. |
| **`xt` CLI** (`src/xt/`) | Python, run through uv. Commands for the human and for agents; `xt --version` prints the version from `pyproject.toml`. |
| **Supervisor** (`xt watch`) | A long-running loop in its own Herdr workspace. The only part of xt that calls Herdr on agents' behalf, and the one that notifies the human. |
| **TUI** (`xt tui`, bare `xt`) | The human's lazygit-style view and controls (Textual). |
| **Harness adapters** (`harnesses/*.toml`) | Per harness: Herdr kind, start arguments, model flag, startup dialogs to answer, known limits. |
| **Team repo** | A clone of xt that `xt init` turns into the user's own repo (`origin` renamed `upstream`, so `git pull upstream main` brings xt updates). |
| **mise** | Puts `bin/` on PATH inside the repo and provides uv. |

### The source, module by module

| File | Its job |
|---|---|
| `bin/xt` | The launcher (above). |
| `bin/xt-clone.sh` | Clones xt for a new team and runs `xt init` (see Starting a team). |
| `bin/xt-statusline` | Claude Code status-line command: records the plan's usage windows (runs `planusage`). |
| `src/xt/__init__.py` | The package; reads `__version__` from the installed `pyproject.toml` version. |
| `src/xt/__main__.py` | `python -m xt`: calls `cli.main`. |
| `src/xt/cli.py` | Every `xt` command: argument parsing, `--as` identity checks (the human's own terminal), and the small commands (`send`, `log`, `status`, `inbox`, `approve`, …). |
| `src/xt/context.py` | `Ctx`: one command's paths, team, ledger and Herdr client, loaded once. |
| `src/xt/paths.py` | Where everything lives in a team repo (`.xt/state`, `.xt/log`, …), finding the root (`XT_ROOT`, else the enclosing xt checkout), and `XtError`, the user-facing error. |
| `src/xt/team.py` | `team.toml`: the roster, policy, notify, log and default settings, schedules and their windows (`next_due`), and the new-team template. |
| `src/xt/ledger.py` | The message log (append-only daily JSONL) and the ledger of open goals, tasks and questions derived from it; rotation and archiving. |
| `src/xt/dispatch.py` | `xt send`: the reporting-chain policy, the envelope and reply hint, delivery now or through the queue, and what's waiting on the human. |
| `src/xt/goals.py` | Goal drafts and dispatch (`xt goal new`, `dispatch`, `list`). |
| `src/xt/goaldone.py` | One notification per goal the human dispatched, and the Inbox's done marker (`state/inbox_seen.json`). |
| `src/xt/inbox.py` | The human's Inbox in three groups (Needs you, New, Friction) for the TUI and `xt inbox`, and friction's read marker. |
| `src/xt/choices.py` | Decision questions with options: validation, rendering, and turning a numeric answer into the option's text. |
| `src/xt/brief.py` | `xt brief`: the recovery summary, included in every first prompt. |
| `src/xt/skills.py` | The team's skills index for first prompts and briefs. |
| `src/xt/spawn.py` | Starting agents (`do_spawn`: workspace, startup dialogs, first prompt, landed check), spawn requests and their approvals, stop and retire. |
| `src/xt/permissions.py` | Claude Code settings files: which file applies (`effective`), the preflight check, the start note. |
| `src/xt/adapters.py` | Harness adapters from `harnesses/*.toml`: start arguments (settings file, connector block or opt-in, model flag), dialogs, limits. |
| `src/xt/herdr.py` | The thin wrapper over the `herdr` CLI, always with `--session`. |
| `src/xt/jobs.py` | Herdr work agents ask for (spawn, start, retire), queued for the supervisor. |
| `src/xt/watch.py` | `xt watch`, the supervisor: its tick (below), alerts, heartbeat, wake-ups, notifications, usage recording. |
| `src/xt/alerts.py` | Alerts for the human, raised and cleared by key. |
| `src/xt/up.py` | `xt up`, `xt down` and `xt restart`: bringing the team to its resting state and back. |
| `src/xt/init.py` | `xt init`: turning a fresh clone into a team repo. |
| `src/xt/reset.py` | `xt reset` and `xt checkpoint`: a fresh context for one agent, only after it has saved its notes. |
| `src/xt/usage.py` | Live context per agent, from its harness's session log. |
| `src/xt/turns.py` | Per-turn usage and cost estimates, attributed to goals; the account allowance lines. |
| `src/xt/planusage.py` | Claude plan usage from the status line (standard library only). |
| `src/xt/versions.py` | Published, installed and running xt versions. |
| `src/xt/switch.py` | `xt version use` and `rollback`: state format checks, snapshots, merge and revert. |
| `src/xt/tui/app.py` | The TUI (Textual): panels, keys, dialogs, and the actions it takes as the human. |
| `src/xt/tui/model.py` | What the TUI shows: the team's files and live state turned into panel rows and the Status pane. |
| `src/xt/tui/clipboard.py` | The system clipboard for the TUI's text boxes. |
| `src/xt/tui/lazy.tcss` | The TUI's stylesheet. |
| `src/xt/tui/__init__.py` | The TUI package. |

## Files in a team repo

| Committed (the team's durable state) | Runtime, gitignored (`.xt/`) |
|---|---|
| `team.toml`: roster and settings | `log/YYYY-MM-DD.jsonl`: the message log (append-only); `log/archive/` gzipped old days |
| `roles/<role>.md`: role briefs (`lead` and `liaison` ship; the lead writes the rest) | `state/ledger.json`: id counter + open goals, tasks and questions (rebuildable from the log) |
| `skills/<name>/SKILL.md`: team skills (`.agents/skills` and `.claude/skills` link here) | `state/queue.json`: messages waiting for delivery |
| `goals/drafts/*.md`, `goals/<slug>.md`: goal briefs | `state/jobs.json`: Herdr work requested by agents |
| `members/<name>/`: per-agent notes (`notes.md`) and work files | `state/approvals.json`: hires and schedules waiting for the human |
| whatever the team produces (e.g. `output/`) | `state/live.json`: the supervisor's latest `agent list` |
| | `state/watch.log` (+ `watch.log.1`): the supervisor's events, rotated at 512 KB |
| | `state/sessions.json`: which harness session log belongs to which agent (per start); `state/model_windows.json`: pi's model windows, cached a day |
| | `usage/YYYY-MM-DD.jsonl`: per-turn usage records; `state/usage_offsets.json`, `state/allowance.json`, `state/claude_plan.json` (Claude plan windows from the status line) |
| | `state/alerts.json`, `expected.json`, `stopped.json`, `nudges.json`, `wakes.json`, `notified.json`, `goal_notices.json`, `inbox_seen.json`, `watch.pid`, `lock` |

xt's own files (`bin/`, `src/`, `tests/`, `docs/`, `protocol.md`, `harnesses/`, `roles/lead.md`,
`roles/liaison.md`, `prices.toml`, `pyproject.toml`, `uv.lock`, `mise.toml`, `CHANGELOG.md`, `LICENSE`) come from
upstream and aren't edited by the team, so upstream merges rarely conflict.

### `team.toml`

```toml
[team]      name, session (the Herdr session this team lives in)
[policy]    spawn_approval, max_agents, heartbeat_minutes, schedule_approval, min_wake_minutes
[log]       raw_days, delete_after_days, daily_alert_mb, message_max_kb
[notify]    enabled, command (e.g. "notify-send --app-name=xt {title} {body}"), quiet (e.g. "21:00-07:00")
[defaults]  liaison / lead harness (and optional model); permissions? (settings file for every Claude agent)
[[agent]]   name, role, harness, model?, reports_to, status (active | retired),
            wake_every? (e.g. "30m"), wake_message?, wake_between? (e.g. "05:00-21:00"), wake_at? (e.g. "09:30"; set with `xt schedule`),
            permissions? (e.g. "settings/carol.json"; Claude Code only), connectors? (account connectors opted in)
```

`reports_to` is the communication chain: human ↔ liaison ↔ lead ↔ members (sub-leads possible).
Runtime facts such as pane ids never go in `team.toml`. A section left out uses xt's defaults.

## Starting a team

`bin/xt-clone.sh <team>`:
1. Clones xt from GitHub (with `gh` when it's logged in, otherwise plain `git clone`), runs `mise trust`.
2. `xt init`: checks prerequisites; asks for the team name and Herdr session, the liaison's and
   lead's harness and model (codex recommended), and whether hires need approval; renames `origin`
   to `upstream`; writes `team.toml` and the team folders; commits.
3. Starts the team's Herdr session headless if needed (`herdr --session <team> server`).
4. `xt up`: starts the supervisor workspace and the liaison. The lead starts only when the first
   goal is dispatched.
5. Attaches the human to the session.

## Starting an agent (`do_spawn`)

Used for the liaison, the lead, and every member; always run by the human's `xt` or by the
supervisor, never inside an agent's shell.

1. `herdr workspace create` (cwd = team repo), then `herdr agent start <name> --kind <kind>` with the
   adapter's arguments (e.g. pi `-a`, model flag).
2. **Startup dialogs.** Harnesses can open a dialog before they accept input, and a prompt typed
   into it is lost. Adapters declare the dialogs and the keys that answer them; xt reads the pane
   and answers:
   - codex "Trust this folder?": `enter` ("Trust and continue" is preselected). Can't be skipped
     with `-c` config.
   - claude "Is this a project you created or one you trust?": `down`, `enter` ("No, exit" is
     preselected). Herdr refuses `agent start` with `agent_not_ready` while it's up; xt answers
     it and waits for the agent to become idle instead of giving up.
   - pi: started with `-a`, so no dialog (and repo skills load).
3. **First prompt.** Identity ("You are **name**, an agent in the xt team …"), a precedence
   statement (for team coordination the xt protocol wins over any other instructions the agent
   has), `protocol.md`, the role brief, the skills index, and `xt brief` for that agent.
4. **Landed check.** The prompt counts as delivered only if Herdr sees the agent start working
   *and* the prompt's text appears on the agent's screen. Otherwise xt retries once, then raises a
   `noprompt:<name>` alert. (Without this, a codex liaison twice ran with no identity and acted as
   a plain assistant.)
5. The agent is added to the "expected" set, so the supervisor can tell a crash from a stop.

**What goes into the start command.** Before step 1, `permissions.effective` picks the agent's
settings file (its own `permissions` line, else `[defaults] permissions` when the harness takes one;
a Codex or pi agent with its own line is refused), `permissions.preflight` checks it (inside the
repo, JSON, known `defaultMode`, well-formed rules; a bad file refuses the start) and
`Adapter.start_args` builds the arguments: the adapter's own `args`, then `--settings <file>` (the
adapter's `settings_flag`), then the connector block (or, for an opt-in, a refusal of every other
connector's tools), then the adapter's `model_flag` with the agent's `model`. The start note in the
ledger records the file's path, a short hash of its content and its mode. A spawn *request*
(`request_spawn`, e.g. the lead's `xt spawn … --permissions FILE`) runs the same check before it
asks the human, and the approval names the file or warns that a Claude agent would start without
one. The model tables don't reach the harness: the adapter's `context_windows` and `prices.toml`
are only read back by `usage` and `turns` to show context and estimate cost.

An agent keeps the instructions of its first prompt until it's restarted, so a team picks up
changed roles or a new xt version only after a restart (`xt down`, then `xt`).

## Messages

Agents talk only through `xt send <to> --as <me> --type … [--ref id]` (or `xt done <id>`).

| Type | Meaning |
|---|---|
| `goal` | What the human wants; liaison → lead only. Opens a ledger item. |
| `task` | A unit of work, sent down the chain; `--ref <goal>`. Opens a ledger item. |
| `ask` | A question, up or down. An `ask` to the human (only the liaison can send one) opens a **question** item, see below. |
| `report` | Progress, results, answers; `--ref` says what it's about. |
| `done` | Closes an open item; the owner's final report. Goes to whoever opened it, or up the sender's chain if it can't reach them (e.g. a goal the human dispatched directly). The asker may also close its own question. |
| `note` | Logged for the sender only, never delivered (the liaison records what the human said this way). |
| `friction` | Any agent's feedback about xt or its harness (`xt friction`): logged to the human, shown in the Inbox and `xt inbox`, never delivered to a pane, outside the reporting chain. |
| `system`, `alert`, `approval`, `nudge`, `wake` | From xt itself. |

- **Policy:** a sender may message its `reports_to` and its own reports; the human may message
  anyone. Only the liaison (or human) opens goals; tasks go downward only; the liaison can't spawn
  or retire. Messages over 4 KB are refused (put payloads in files and send the path).
- **Identity:** agents pass `--as <name>` (told in the first prompt). `--as human` works only from
  the human's own terminal: a process with a controlling terminal (stdin may be a heredoc or pipe),
  no `XT_AGENT` in its environment (xt exports it in every agent's pane before the harness
  starts) and no harness (claude, codex, pi) among its ancestors. Claude Code's and pi's shell
  tools have no terminal at all; Codex can put a pseudo-terminal on a command's stdin, but the
  command still has no controlling terminal. (The ancestry signal can't see through Codex's PID
  namespace; the controlling terminal and the marker don't depend on it.)
- **Envelope:** delivered text is stamped `[xt #42 task from:lead to:carol ref:#3]`, with a reply
  hint that passes the text on stdin in a quoted heredoc (`<<'XT_END'`), so the agent's shell leaves
  backticks and `$(…)` alone. Unstamped text in a pane comes from the human typing there.
- **Delivery:** an agent's `xt send` only appends to the log and the queue. The supervisor delivers
  when the recipient is idle: **everything queued for it in one prompt**, oldest first, with
  messages about since-closed items marked *stale*. Messages from the human (and the supervisor's
  own) are delivered directly if the recipient is idle. Messages to the human are never typed
  anywhere: they appear in the TUI's Inbox and `xt inbox`, and questions, approvals and alerts
  also trigger a notification.

## Context per agent

`src/xt/usage.py` reads how full each agent's conversation is from its harness's own session log.
Each harness adapter declares where its logs are (`sessions`, a glob under `~`), their
`session_format` (`codex`, `claude`, `pi`) and, where the log doesn't state it, `context_windows`
per model. An agent is linked to its log by its first prompt ("You are **name**, an agent in the
xt team "team""), looking only at logs written since xt last started it (the ledger's `started …`
entry), so a restart moves it to the new session; Codex's "guardian" sub-sessions (its automatic
reviewer) repeat the prompt and are skipped. The link is kept in `state/sessions.json`. From the
log's tail xt takes the latest usage record: Codex's `token_count` (latest turn's total out of
`model_context_window`, marked approximate), Claude Code's `message.usage` (input, cache and
output tokens, skipping subagent turns; window from the adapter's table), pi's message `usage`
(window from `pi --list-models`, cached a day). Only counters are read. Anything missing is
reported as unknown, never guessed. The TUI's Team panel and agent detail, `xt status` and the
lead's and liaison's briefs show it; members' briefs don't.

## Usage and cost

`src/xt/turns.py` records per-turn usage. About once a minute the supervisor reads the new lines
of every active agent's logs: its main session and, for Codex, the automatic-reviewer ("guardian")
sub-sessions that carry its first prompt, recorded as auxiliary (Claude's subagent turns too).
Each model call becomes one record in `.xt/usage/YYYY-MM-DD.jsonl` (the local day it completed):
agent, harness, model, input / cached / cache-write / output tokens, auxiliary or not, the goal,
and an estimate. Read positions are kept in `state/usage_offsets.json`; repeated counts (Codex)
and repeated message ids (Claude logs one API message per content block) aren't counted twice.
A turn belongs to the goal of the latest message the agent sent or received before it (following
tasks and `--ref`s up to the goal); scheduled work outside any goal has none. Estimates use
`prices.toml` (public list prices with their source and date) or pi's own per-message cost; a
model without a price leaves its tokens unpriced. The latest account allowance a harness reports
(Codex `rate_limits`) is kept in `state/allowance.json` and shown once per harness. Totals are
added up on read: today per agent and team, and per goal over its lifetime.

Claude Code logs no rate limits; it passes them only to a status-line command. `src/xt/planusage.py`
(standard library only) is that command's logic, run by `bin/xt-statusline` with the system Python
for a Claude agent whose settings file has a `statusLine` entry. It keeps each window's latest
`used_percentage`, `resets_at` and the time it was read in `state/claude_plan.json`, replaced
atomically (temporary file, then rename), under `XT_ROOT` or else the checkout the script is in. A
call without `rate_limits` leaves the file alone. `xt status` and the TUI show it with the Codex
allowance: a passed reset, a reading over 3 hours old or timestamped later than now, an
out-of-range value, or a missing or broken file shows no percentage.

## The ledger and recovery

The message log is the ledger. Every message gets a sequential id; `goal`/`task` open an item with
an owner; `done` closes it. `state/ledger.json` keeps the open items and can be rebuilt from the
log, so rotation never loses them. Logs are gzipped after 30 days and never deleted by default.

**Questions for the human.** When the liaison needs a decision, it sends
`xt send human --type ask --ref <what it's about>`. That opens a question owned by the human. It
closes when the human replies with `--ref` to it (`xt answer <id>`, or `s` on it in the TUI; the
answer reaches the liaison as a `report`), or when the liaison withdraws it with `done` (the human
answered in its pane, or the question was superseded, e.g. by a lead's auto-pick). Open questions
show first in the Inbox with their age, in `xt inbox` and `xt status`, and in the brief.

`xt brief [name]` summarises the team (with schedules), live state, open work, drafts and recent
messages in about 2k tokens; the liaison's and lead's briefs add **Waiting on the human** (open
questions, pending approvals and alerts, with the exact commands). Every first prompt includes the
brief, and any agent runs it after a restart or context loss; nothing depends on an agent's own
memory. Agents may read their own brief and their reports' briefs. `xt log` gives the history: the newest
20 matching messages by default, `--full` for all of it.

## Versions, state format and snapshots

`versions.py` keeps three numbers apart: the **published** release (checked upstream by the
supervisor every few hours, cached in `state/versions.json`), the **installed** one (the team repo's
`pyproject.toml`) and the **running** ones (the supervisor's, and the xt that started each agent).
`xt status`, the brief and the TUI title show them.

`xt version use <tag>` (`switch.py`) merges an upstream release tag into the team repo. It runs
only for the human, with the team fully down and the team's tracked files committed. The mutable
state in `.xt/state/` has a **format number** (`state/format.json`, stamped by `xt up`; format 1
since 0.12.0): the target tag must declare that it reads the team's format (`STATE_FORMATS` in its
own `switch.py`), and xt never migrates state. Before the merge xt takes a **verified snapshot**:
a copy of `.xt/state/` in `.xt/snapshots/<time>-before-<tag>/` with a manifest of hashes, checked
against the original. It also records a fingerprint of the append-only ledger (`.xt/log/`, never
copied back). The merge is `--no-ff`; a conflict aborts it and leaves the previous version.
`xt version rollback` reverts what the switch committed, after checking that the previous version
reads the team's state format and that the ledger still continues from its fingerprint. The state
stays as it is (same format, and it matches the ledger); the snapshot is kept for recovery by hand,
never copied back automatically. Switches are recorded in `state/switches.json`.

## The supervisor, one tick every 3 seconds

1. Reload `team.toml`.
2. **Run jobs**: spawns, lazy lead starts, and retires that agents asked for. Then message the
   requester "Done: …" or "Failed: …".
3. Read `herdr agent list`; save it to `state/live.json` (agents in sandboxes read it there).
4. **Drain the queue**: batch-deliver to every recipient that is idle.
5. **Check agents** and raise alerts once each, clearing them when resolved:
   - an agent blocked (usually an approval prompt in its pane);
   - an expected agent missing (crashed, or closed outside xt);
   - goals open but the lead not running (no job starting it, and not stopped by the human).
6. **Volume**: alert if today's log passes the limit (a likely message loop).
7. **Heartbeat** (every `heartbeat_minutes`): an idle owner of an open item it hasn't worked on for
   that long (no report or ask about it, no task sent under it; a new item counts from when it
   opened) gets a `nudge`; after two unanswered nudges the human gets an alert instead. Not nudged:
   an item with open subtasks (its owner is waiting on its reports, who get nudged themselves), and
   items waiting on an open question to the human (the question refers to the item, or to a message
   about it, up to four hops).
8. **Scheduled wake-ups**: an agent with `wake_every` gets a `wake` message (its `wake_message`)
   when the interval has passed and it's idle with nothing queued, so a wake-up never interrupts
   work. The clock starts when the supervisor first sees the schedule and is kept in
   `state/wakes.json`, so restarting the supervisor doesn't reset it. An optional `wake_between`
   window (local time, may wrap midnight) limits wake-ups to those hours; an agent that became due
   outside it gets a single wake-up when the window opens. Daily or longer
   schedules with a window (or `wake_at`) are anchored to that local time: the next wake is the
   first such time after the last one, whenever the schedule was approved, following the wall
   clock across daylight-saving changes (`team.next_due`). Schedules are set with `xt schedule` by
   the human or the agent's lead. Each wake-up is a billed agent turn, so a lead's schedule is
   refused below `min_wake_minutes` (default 15) and, with `schedule_approval` (default on), waits
   in the human's Inbox like a hire; the human sets any schedule directly, and switching one off
   needs no approval. This is how a periodic role like a monitor or a scout works, since agents
   only act when prompted.
9. **Notifications**: each new question, approval request or alert for the human runs the
   `[notify]` command (default `notify-send`; any command with `{title}`/`{body}`, e.g. an ntfy
   `curl`), except inside the `quiet` window. Counting starts when the supervisor first runs; what
   arrives in quiet hours stays in the Inbox without a notification. A goal the liaison opened
   notifies once when it closes (`src/xt/goaldone.py`, `state/goal_notices.json`): the liaison's
   report to the human about it after the closure (its `--ref` is the goal or the lead's `done`) is
   the notification; a closure without one within 5 minutes notifies with the closing summary's
   first line. Reports about a goal that's still open, or after its notification, don't notify.
   Other liaison reports to the human (not about a goal) notify once per `ref`. `state/inbox_seen.json` holds the message id
   up to which the human has seen the Inbox's New group (`upto`: the TUI moves it when the human
   leaves the Inbox panel, `xt inbox` in the human's terminal after printing), and friction's read
   marker (`friction_upto` and the ids seen one by one above it, `friction_seen`; see
   `src/xt/inbox.py`). The supervisor's first run starts both at the end of the log.
10. **Rotation**, hourly.

Every event the supervisor prints in its pane is also appended to `state/watch.log`, which the
TUI's Supervisor panel and `xt log --watch` show.

It **alerts, it never repairs**: no automatic restarts. A crash is a bug to look at.

### Why agents never call Herdr

Codex runs an agent's shell commands in a sandbox that blocks Herdr's socket ("Operation not
permitted"). When a codex liaison dispatched a goal, it couldn't start the lead. So agent-issued
xt commands only write files: messages go to the queue, and spawn/start/retire requests go to
`state/jobs.json` for the supervisor. `xt brief` and `xt status` fall back to `state/live.json`
when Herdr is unreachable. The human's own commands still act directly.

## Goals, end to end

1. The human talks to the liaison in its pane. The liaison records the request (`xt note`) and
   keeps a draft in `goals/drafts/<slug>.md` updated as they talk.
2. The liaison reads the draft back; on the human's go, `xt goal dispatch <slug>` freezes it as
   `goals/<slug>.md` and sends a `goal` to the lead. If the lead isn't running, the supervisor
   starts it, and the goal is in its first brief.
3. The lead plans, writes role briefs into `roles/` and skills into `skills/`, and requests hires
   (and schedules for periodic roles). With approvals on (the default), each waits for the human
   (`xt approve <id>…`, or `a` in the TUI's Inbox). The supervisor starts the agents.
4. The lead sends `task`s; members report and `done` them. Decisions only the human can make go up
   to the liaison, which asks them as questions.
5. The lead integrates, makes sure anything that keeps running after the goal is described in
   roles or skills (not in the goal brief), and sends `done` for the goal to the liaison, who
   tells the human with an xt report (the goal's one notification; see Notifications). Tasks still
   open under the goal are closed with it.

**Standing rules.** When the human sets a rule that lets the team act without them (e.g. an
auto-pick when they don't answer), the lead asks the liaison for a goal under that rule, and the
liaison dispatches it without a read-back, naming the rule, and tells the human afterwards.

**Friction.** Agents add one `Friction:` line to a `done` or report when something got in the way
(never "no issues"). The lead makes small, clear fixes to its team's roles and skills, records
them in `members/lead/lessons.md` (and flags friction that comes back), sends bigger changes to
the human as proposals, and summarises a goal's friction in its `done`. Friction with xt or a
harness goes to the human with `xt friction`.

## The human's controls

- Talk to the liaison in its Herdr pane (or type into any agent's pane: that's unstamped and
  legitimate).
- `xt tui` (also what bare `xt` opens after `xt up`), refreshed every 2 s. Six panels of fixed
  size (focus shows by frame colour and a reversed title; `/` filters the focused one; rows are
  cut at the panel's width in cells and end with a dim age, `model.fit`): **Goals** (drafts, then
  open goals with task progress; detail shows the tasks and the goal brief, or the draft), **Team** (live
  state and schedules; detail shows open work, recent messages and the last lines of the agent's
  screen), **Tasks** (open, then recently closed; detail shows the thread), **Inbox** (three
  groups: Needs you with open questions, pending approvals and alerts; New with goals done and
  reports to the human since they last looked; unread Friction, with seen friction folded; the
  counts in its title), **Log** (newest first),
  and **Supervisor** under the detail pane (the supervisor's events, newest first). The Status pane on top shows the team and only what needs the human (highlighted), today's usage and allowance, and the last action's result in full; the bottom line is
  key hints; `h` lists every key (the README has the table). Slow actions (starting agents) run in
  the background. `xt tui --demo` shows sample data.
- `xt status`: roster × live state, open items, questions, queue, jobs, approvals, alerts; warns if
  the supervisor isn't running.
- `xt inbox`: the Inbox's three groups as in the TUI; in the human's terminal it clears New and
  marks the friction it printed as seen. `xt answer <id> "..."` (a number picks a decision question's
  option), `xt approve <id>…`, `xt deny <id>`, `xt clear <alert>`.
- `xt schedule <name> <interval>|off [--message …] [--between HH:MM-HH:MM] [--at HH:MM]`.
- `xt reset <name>`: a fresh context for one agent after it saved its notes (`xt checkpoint`).
- `xt version`, `xt version use <tag> [--candidate]`, `xt version rollback` (see Versions above).
- `xt log [--limit N | --full]`: the newest 20 messages by default.
- `xt restart <name>…` (stop and start with fresh instructions) and `xt restart --all` (the
  supervisor and every running agent: the upgrade path), `xt stop <name>` (close without
  retiring), `xt spawn <name>`, `xt retire <name>`,
  `xt down` (stop the supervisor, then every agent, cleanly, so neither the last tick nor the next
  `xt up` raises false alerts; `herdr session stop` bypasses xt and does leave them).

## Harnesses

| | claude | codex | pi |
|---|---|---|---|
| Startup dialog | "Is this a project you created or one you trust?" → `down`, `enter` | "Trust this folder?" → `enter` | none (started with `-a`) |
| Repo skills found via | `.claude/skills` → `skills/` | `.agents/skills` → `skills/` | `.agents/skills` → `skills/` (needs trust, hence `-a`) |
| Shell sandbox | none by default | blocks Herdr's socket (so agents never call Herdr) and the network: a fetch needs an escalation, which Codex's reviewer (or the human) approves | none |
| Other limits | a Herdr server started from inside Claude Code passes `CLAUDE_CODE_CHILD_SESSION` to its agents (transcript saving off) | shell runs in one shared machine-wide daemon; per-pane env doesn't reach it | `-a` also trusts project `.pi/` config for the run |

Verified live on 2026-09-26: a codex liaison, a claude liaison, and a pi member each started in
a fresh folder with their prompt landing; a codex liaison dispatched a goal from its sandbox and
the supervisor started the lead, which completed it. On 2026-09-27 codex agents fetched RSS feeds
and published to a web service through escalations that Codex's reviewer approved without the
human. All full team runs so far used codex for every agent.

## Coexisting with the user's setup

Agents run on a real user's machine, with global instructions, skills, plugins and memory. xt
doesn't need a clean room. The first prompt states that the xt protocol wins for team
coordination only; the protocol is self-contained; skills the team relies on live in its repo;
anything from the user's own setup is optional (a team may use a user-level skill, such as one for
publishing, when a goal says so). xt never writes to user-level skill folders. It does add a trust
entry for the team folder in codex's and claude's config, because answering their trust dialog is
what saves it.

## Known gaps

- **Soft enforcement.** An agent can still call Herdr directly outside a sandbox, or claim another
  agent's name with `--as`. The envelope and the log make it visible; nothing prevents it.
- **The `--as human` guard** is checked live for Claude Code's shell tool and Codex's normal and
  pseudo-terminal commands (0.11.0), not for every harness or mode; an agent that deliberately
  unsets `XT_AGENT` and escapes its harness's process tree would still pass.
- **Credential-holding CLIs.** Account connectors are off for agents, but a command-line tool that
  holds the operator's credentials (a mail CLI) is an ordinary program to the harness. A Claude
  agent is bounded by its settings file, a Codex agent only by its sandbox and escalation review
  (research on card #107; enforcement proposed as card #126).
- **Instructions age.** Running agents keep their first prompt's instructions until restarted.
- **Estimates, not bills.** Dollar figures come from public list prices; subscriptions, discounts
  and long-context tiers aren't reflected. No budgets or alerts on usage yet (card #92). The Claude
  plan windows come only from agents whose settings file opts into the status line.
- **Not built yet:** bypass detection, ping-pong loop detection (only the daily-volume alert),
  `xt config`.
- **Latency.** Agents' messages and jobs wait for the next supervisor tick (up to ~3 s), and
  nothing moves if the supervisor isn't running (`xt status` warns).
