# xt architecture: how it works

What the code does as of **v0.19.0** (2026-10-01), after real runs with a newsroom team and xt's
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
| **Harness adapters** (`harnesses/*.toml`) | Per harness: Herdr kind, start arguments, model flag, startup dialogs to answer, readiness before the first prompt (pi), session logs, known limits. |
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
| `src/xt/cli.py` | Every `xt` command: argument parsing, `--as` identity checks (the human's own terminal; a registered operator, card #166), delegated commands, the one answer path (`answer_question`, used by `xt answer` and the TUI), and the small commands (`send`, `log`, `status`, `inbox`, `approve`, `operator`, `delegate`, …). |
| `src/xt/context.py` | `Ctx`: one command's paths, team, ledger and Herdr client, loaded once. |
| `src/xt/paths.py` | Where everything lives in a team repo (`.xt/state`, `.xt/log`, …), finding the root (`XT_ROOT`, else the enclosing xt checkout), and `XtError`, the user-facing error. |
| `src/xt/team.py` | `team.toml`: the roster, policy, notify, log and default settings, schedules and their windows (`next_due`), and the new-team template. |
| `src/xt/ledger.py` | The message log (append-only daily JSONL, a message optionally carrying structured `question` or `answer` data) and the ledger of open goals, tasks and questions derived from it; rotation and archiving. |
| `src/xt/dispatch.py` | `xt send`: the reporting-chain policy, the envelope and reply hint, delivery now or through the queue, and what's waiting on the human. |
| `src/xt/goals.py` | Goal drafts and dispatch (`xt goal new`, `dispatch`, `list`). |
| `src/xt/goaldone.py` | One notification per goal the human dispatched, and the Inbox's done marker (`state/inbox_seen.json`). |
| `src/xt/inbox.py` | The human's Inbox in three groups (Needs you, New, Friction; the TUI calls New Notifications) for the TUI and `xt inbox`, and friction's read marker. |
| `src/xt/chat.py` | `xt chat` (from 0.21.0): the human's conversation with the liaison as a view over the ledger (the last 30 messages, new ones read every 2 s, pending questions and approvals answered in place through `cli.answer`); Textual, as the TUI; nothing stored of its own. |
| `src/xt/choices.py` | Questions with a declared answer type (closed, options, open; from 0.21.0): validation, rendering, the `question` data stored on an ask (read from the text for older asks), and checking an answer against it, a numeric answer recorded as the option's text. |
| `src/xt/brief.py` | `xt brief`: the recovery summary, included in every first prompt. |
| `src/xt/skills.py` | The team's skills index for first prompts and briefs. |
| `src/xt/spawn.py` | Starting agents (`do_spawn`: workspace, startup dialogs, readiness wait, first prompt with pi's guard line, landed check, the session-log check and the one resend of a damaged prompt, `Resends`/`run_resends`), spawn requests and their approvals (each a closed question in the ledger, answered once by `xt answer`, `approve`/`deny` or the TUI), stop and retire. |
| `src/xt/permissions.py` | Claude Code settings files: which file applies (`effective`), the preflight check, the start note. |
| `src/xt/adapters.py` | Harness adapters from `harnesses/*.toml`: start arguments (Codex options from the allowlist, settings file, connector block or opt-in, model flag), dialogs, readiness (`ready_settle`, `check_prompt_in_log`, `first_prompt_prefix`), `first_prompt_note`, limits. |
| `src/xt/herdr.py` | The thin wrapper over the `herdr` CLI, always with `--session`. |
| `src/xt/jobs.py` | Herdr work agents ask for (spawn, start, retire), queued for the supervisor. |
| `src/xt/watch.py` | `xt watch`, the supervisor: its tick (below), alerts, heartbeat, wake-ups, notifications, usage recording. |
| `src/xt/alerts.py` | Alerts for the human, raised and cleared by key. |
| `src/xt/boardwatch.py` | Card #135: the board watch. Runs the `[board_watch]` command from `team.toml` in the background (no shell, no input, a timeout, at most 64 KB of output), reads its JSON array of cards, tells the lead about each number new since the last success (the first success after a supervisor start is only the baseline), one `boardwatch` alert per outage, and the status line (`state/board_watch.json`). |
| `src/xt/up.py` | `xt up`, `xt down` and `xt restart`: bringing the team to its resting state and back. |
| `src/xt/init.py` | `xt init`: turning a fresh clone into a team repo. |
| `src/xt/launch.py` | Card #165: whether each running agent is the process xt started, by its `XT_AGENT` in `/proc` (a harness process working in the team repo); the warning and one Inbox alert per agent running without xt's launch settings. |
| `src/xt/operators.py` | Card #166: named operators acting for the human. Registration (`xt operator add NAME --pid PID`: a harness process that isn't a team agent, its start time, and a token in `.xt/operators/NAME.token`, mode 600), recognition (token in `XT_OPERATOR_TOKEN` *and* the registered process among the command's ancestors), the operator's reports to the liaison, and time-bound grants of `restart`, `reset`, `spawn` (existing agent) and `up` (at most 60 minutes, checked against the stored end time at each command). |
| `src/xt/reset.py` | `xt reset` and `xt checkpoint`: a fresh context for one agent, only after it has saved its notes. The queued reset (`--when-idle`, `state/resets.json`), the supervisor's non-blocking step that runs it, and the opt-in automatic policy that queues one above a token threshold. |
| `src/xt/usage.py` | Live context per agent, from its harness's session log. |
| `src/xt/turns.py` | Per-turn usage and cost estimates, attributed to goals; the account allowance lines and windows. |
| `src/xt/planusage.py` | Claude plan usage from the status line (standard library only). |
| `src/xt/versions.py` | Published, installed and running xt versions. |
| `src/xt/switch.py` | `xt version use` and `rollback`: state format checks, snapshots, merge and revert. |
| `src/xt/tui/app.py` | The TUI (Textual): the three bands and their heights, pane titles, the Team pane, Work and Flow sharing the middle pane, the Flow pane's filters and scrolling, keys and the per-pane key line, the toast, dialogs, and the actions it takes as the human. |
| `src/xt/tui/model.py` | What the TUI shows: the team's files and live state turned into pane rows, Flow's messages and roster, agents and the Team header, and the detail for the Team header and harness rows (versions, each window's reading or why it has none). |
| `src/xt/tui/flow.py` | The Flow lane chart: lane order, which lanes fit and the `+N` lane, arrows with type glyphs, the margin, day separators and list mode, as pure functions of the messages and the width. |
| `src/xt/tui/teampane.py` | The Team pane's layout, one column: the wrapped header, harness blocks, window bars, aligned agent lines, short model names, and the `+N more` cut to the pane's height. |
| `src/xt/tui/work.py` | The Work outline: which goal each task belongs to (the root of its `ref` chain), task states, goal order, and a Work row laid out at the pane's width. |
| `src/xt/tui/thread.py` | The detail pane's thread: which messages belong to the selected one's thread, and the view that lays it out for the pane, with the selected message kept in view. |
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
| | `state/resets.json`: queued resets and each agent's last reset, for the automatic policy's cool-down |
| | `state/board_watch.json` (+ `.out`, `.err` of the last run): the board watch's last success or current failure, for status |
| | `state/prompt_resends.json`: pi first prompts that arrived damaged, waiting to be resent once or checked after the resend |
| | `state/context_alerts.json`: which start of each agent got its `context:<name>` alert, so it's raised once per start |
| | `state/operators.json`: registered operators (pid, start time, token hash) and their delegation grants; `operators/<name>.token`: an operator's token (mode 600) |

xt's own files (`bin/`, `src/`, `tests/`, `docs/`, `protocol.md`, `harnesses/`, `roles/lead.md`,
`roles/liaison.md`, `prices.toml`, `pyproject.toml`, `uv.lock`, `mise.toml`, `CHANGELOG.md`, `LICENSE`) come from
upstream and aren't edited by the team, so upstream merges rarely conflict.

### `team.toml`

```toml
[team]      name, session (the Herdr session this team lives in)
[policy]    spawn_approval, max_agents, heartbeat_minutes, schedule_approval, min_wake_minutes,
            auto_reset (default false), auto_reset_tokens (150000), auto_reset_cooldown_hours (6)
[log]       raw_days, delete_after_days, daily_alert_mb, message_max_kb
[notify]    enabled, command (e.g. "notify-send --app-name=xt {title} {body}"), quiet (e.g. "21:00-07:00")
[defaults]  liaison / lead harness (and optional model); permissions? (settings file for every Claude agent)
[board_watch]  command (argument list), interval? ("5m"), timeout? ("30s"), column? (its name, for the message)
[[agent]]   name, role, harness, model?, reports_to, status (active | retired),
            wake_every? (e.g. "30m"), wake_message?, wake_between? (e.g. "05:00-21:00"), wake_at? (e.g. "09:30"; set with `xt schedule`),
            permissions? (e.g. "settings/carol.json"; Claude Code only), connectors? (account connectors opted in),
            auto_reset_tokens? (this agent's threshold, or "off"),
            codex_options? (e.g. ["sandbox_workspace_write.network_access=true"]; Codex only, allowlisted)
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
   - pi: started with `-a`, so no dialog (and repo skills load). pi takes input a moment after
     Herdr reports it started, so its adapter sets `ready_settle = 3`: xt waits until the pane's
     screen has stayed unchanged for three checks a second apart (at most 30) before step 3
     (card #167).
3. **First prompt.** Identity ("You are **name**, an agent in the xt team …"), a precedence
   statement (for team coordination the xt protocol wins over any other instructions the agent
   has), `protocol.md`, the role brief, the skills index, and `xt brief` for that agent.
4. **Landed check.** The prompt counts as delivered only if Herdr sees the agent start working
   *and* the prompt's text appears on the agent's screen. Otherwise xt retries once, then raises a
   `noprompt:<name>` alert. (Without this, a codex liaison twice ran with no identity and acted as
   a plain assistant.) An adapter's `first_prompt_prefix` (pi only) is typed as the prompt's first
   line (`spawn.guarded`), so characters lost at the start come out of that line (card #167, rc5).
   An adapter's `first_prompt_note` (pi only: the protocol's "never write no issues" rule, card
   #180) goes just before the prompt's last line, away from the guard and the opening.
   With `check_prompt_in_log` (pi), xt then reads the harness's session log (`usage.prompt_in_log`,
   the first 2 MB of each log written since the start): the opening `You are **name**, an agent in
   the xt team "team"` anywhere in it is whole; the first paragraph's later parts (the team repo's
   path and `Always pass --as name`) without the opening are damaged. A damaged prompt goes into
   `state/prompt_resends.json`, and the supervisor resends it (below).
5. The agent is added to the "expected" set, so the supervisor can tell a crash from a stop.

**What goes into the start command.** Before step 1, `permissions.effective` picks the agent's
settings file (its own `permissions` line, else `[defaults] permissions` when the harness takes one;
a Codex or pi agent with its own line is refused), `permissions.preflight` checks it (inside the
repo, JSON, known `defaultMode`, well-formed rules; a bad file refuses the start) and
`Adapter.start_args` builds the arguments: the adapter's own `args`, then a Codex agent's
`codex_options` as `-c key=value` (checked by `adapters.codex_option_args` against the allowlist
`CODEX_OPTIONS`, which is the sandbox network switch alone; anything else, or the line on another
harness, refuses the start; card #169), then `--settings <file>` (the
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
xt team "team""), or, when the harness lost that opening, by two later parts of the prompt's first
paragraph (the team repo's path and `Always pass --as name`; card #174), looking only at logs
written since xt last started it (the ledger's `started …` entry), so a restart moves it to the new
session; Codex's "guardian" sub-sessions (its automatic
reviewer) repeat the prompt and are skipped. The link is kept in `state/sessions.json`. From the
log's tail xt takes the latest usage record: Codex's `token_count` (latest turn's total out of
`model_context_window`, marked approximate), Claude Code's `message.usage` (input, cache and
output tokens, skipping subagent turns; window from the adapter's table), pi's message `usage`
(window from `pi --list-models`, cached a day). The same read keeps the model the log names
(Codex's newest `turn_context`, else the session's first in its head; Claude Code's and pi's
`message.model`), which the TUI's Team pane shows for an agent configured as `default`. Only
counters and the model name are read. Anything missing is reported as unknown, never guessed; a
log not found says why (`usage.not_found_reason`: no logs where the harness keeps them, none since
the start, or none with the first prompt), and `xt status` says which of context and today's usage
can be read (`usage.unreadable_line`). The
TUI's Team pane and agent detail, `xt status` and the lead's and liaison's briefs show it;
members' briefs don't.

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
supervisor at start and every few hours, after `xt version use`/`rollback` and by `xt version
check`, cached in `state/versions.json`; a cache older than the installed final is shown as
"check pending" and retried sooner), the **installed** one (the team repo's
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
   **Damaged first prompts** (card #167 rc5, `spawn.run_resends`), before any queued message: an
   agent in `state/prompt_resends.json` that is idle gets its whole first prompt again, once, behind
   the guard line and a note that it replaces the damaged one; later ticks read its session log
   until the opening shows (then the entry goes) or 2 minutes pass (then `partprompt:<name>`). A
   stopped agent's entry is dropped; a new start clears it.
4. **Drain the queue**: batch-deliver to every recipient that is idle.
5. **Check agents** and raise alerts once each, clearing them when resolved:
   - an agent blocked (usually an approval prompt in its pane);
   - an expected agent missing (crashed, or closed outside xt);
   - goals open but the lead not running (no job starting it, and not stopped by the human).
   **Queued resets** (card #134, `reset.advance`), one step each, never waiting: with live state
   read again after this tick's deliveries, an agent that is idle, owns no open goal or task and
   has no messages waiting is asked for a checkpoint; once it is confirmed and the agent is idle
   again, the session is replaced; an open item, a waiting message or one delivered since the ask
   (`asked_id`) sends the reset back to waiting; no checkpoint, or still busy, 5 minutes after
   the ask drops it. About once a minute (with usage recording), the **automatic reset policy** (card
   #114, `[policy] auto_reset`, off by default) queues a reset for each idle agent without open
   work whose fresh context reading is above its threshold in tokens and that had no reset within
   the cool-down (`state/resets.json`). Also about once a minute, the **context check** (card #174,
   `Supervisor.check_context`): a running agent whose context still can't be read 10 minutes after
   its start raises one `context:<name>` alert for that start (`state/context_alerts.json`),
   cleared when it becomes readable or the agent stops. And the **launch check** (card
   #165, `src/xt/launch.py`): harness processes in the team repo are matched to agents by their
   `XT_AGENT`; running agents left without a match are warned about (one `launch:<name>` alert,
   cleared when xt starts the agent again or it stops running) only on positive evidence, when at
   least as many processes of their harness run there without `XT_AGENT` (as after a restored
   multiplexer session). Otherwise (process not visible, fewer such processes than agents, a
   harness process that can't be read, or a sandbox: a nested PID namespace from `NSpid`, or a
   PID 1 that isn't an init) the agent is "not checked" and its alert is left as it was. Only
   programs named exactly claude, codex or pi count (not helpers like `codex-linux-sandbox`). `xt status` and `xt up` run the same check.
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
10. **Board watch** (card #135, `src/xt/boardwatch.py`), only with a `[board_watch]` section:
    every `interval` (default 5m) it starts the team's command in the background (an argument list,
    no shell, no input, the supervisor's environment, its own process group) and reads the result on
    a later tick, so a slow command never holds up the tick; past `timeout` (default 30s) or 64 KB
    of output it is killed. The output must be a JSON array of `{number, title?}`. The first
    success after the supervisor starts is the baseline; each later number not in the set is one
    `system` message to the lead. The first failure of an outage raises the `boardwatch` alert; the
    next success clears it and compares against the set kept from before the outage.
11. **Rotation**, hourly.

Every event the supervisor prints in its pane is also appended to `state/watch.log`, which the
TUI's supervisor pop-up (`v`) and `xt log --events` (once; `--watch` is its old name) show. A failed wake-up, notification or usage
recording also raises an alert (card #131, `Alerts.raise_or_count`): one per kind (`failed:wake-up`,
`failed:notification`, `failed:usage-recording`), whose count and last time go up while it is
open, so a failure every minute stays one Inbox row; a cleared one is raised anew by the next
failure. The alert about a failed notification is never itself notified.

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
- `xt tui` (also what bare `xt` opens after `xt up`), refreshed every 2 s, in three bands (card
  #162; `app.band_heights` sets their heights for the terminal's): Team and the Inbox side by side
  on top, as high as the team needs up to 60 % of the height; Work or Flow in one full-width pane in
  the middle (`2` and `3` swap them, `app.show_middle`; the hidden one keeps its state); Detail,
  full width and shorter, at the bottom with 4 to 8 rows. Each title is `[n] - Title - info`
  (`app.pane_title`, `app.retitle`, which draws Work and Flow's shared title as tabs); every list is
  newest on top, and a list whose top row is selected keeps the top row selected as rows arrive.
  The key line is the focused pane's own keys and then `S`, `/`, `v` (`app.PANE_KEYS`,
  `app.GLOBAL_KEYS`). The **Team** pane (card #128; key `0` since card #157; one column since
  card #162): a header (team, xt's version and published or restart notices, running agents,
  open goals, the Inbox's needs-you and new counts, stuck messages or jobs), wrapped between its
  parts; today's tokens and estimate; then per harness its account windows as bars
  (`turns.allowance_windows`) and its agents, one per line, in aligned columns (short model, or
  for `default` the model the agent's session log names, `usage.Reading.model`; state; context as
  tokens, bar and share). `tui/teampane.py` lays it out at the pane's width (`render`, each line
  with the row it belongs to) and cuts it to the pane's height with a last `+N more (widen the
  terminal)` line (`clip`); the pane never scrolls. `j`/`k` select an agent in view; its detail
  shows open work, schedules, recent messages and the last lines of its screen. The TUI starts in
  the Inbox. Three
  numbered panes of fixed size (focus shows by frame colour and a reversed title; `/` filters the
  focused one; list rows are cut at the pane's width in cells and end with a dim age, `model.fit`):
  **Inbox** (1: three groups: Needs you with open questions, pending approvals and alerts, and
  the questions the human answered in the last 7 days folded under it, `inbox.answered`;
  Notifications (New before card #162; unread rows bold)
  with goals done and reports to the human since they last looked, and those already seen from the
  last 7 days folded under it, `inbox.earlier`, card #157, read from the ledger and the existing
  marker; unread Friction, with seen friction folded; the counts in its title), **Work** (2, card #129: goals and their tasks as one
  two-level outline, built by `tui/work.py`: a task goes under the goal at the root of its `ref`
  chain, or under a final `no goal` row; open goals first, expanded, newest activity first; the
  liaison's drafts; done goals under a collapsed `done (N)` fold; `space` folds, `o` shows open
  work only, and the pane keeps both across refreshes; `N open · M done` in its title), and
  **Flow** (3, card #130, in place of the Log: the messages read as a swim-lane chart, laid out by
  `tui/flow.py`: one lane per agent, human first, then `xt` when it sent a shown message, the
  chain and the roster, then dim lanes for retired or unknown agents with a row in view; one row per message, an arrow
  from sender to receiver with the type's glyph and label, dotted into the human's lane, `#id` and
  the first line in the margin and a clock time on the left; lanes that don't fit collapse into a
  `+N` lane, and a narrow pane lists one line per message. `app.FlowPane` keeps the filters, `t`
  system lines, `f` the focus on one agent or one goal's thread, `/` the text filter, the selection, lists the newest
  on top and follows new messages while the newest is selected; it draws only the rows in view).
  The detail pane at the bottom (card #131, `tui/thread.py`) shows the
  selected item with its thread: for a message under a goal (the root of its `ref` chain) the whole
  goal in time order, else the message and its replies through `ref`; one row per message with
  the selected one marked, then the goal's usage and the keys that apply, then reference text such
  as a goal's brief. The thread is laid out for the pane's height at each draw: a long one shows a
  window around the selected message with counts of the hidden rows, and `j`/`k` in the focused
  detail pane move the window (in the short bottom pane they first scroll the thread into view).
  `v` opens the supervisor's events, newest first, in a pop-up. Every
  pane has a key since card #157 (`0` Team to `4` Detail; `esc` in Detail returns to the pane it
  came from); a click selects a row and focuses its pane without opening Detail (Team's cells and
  Flow's rows carry the agent or row in their style's meta), and the wheel scrolls Flow and Detail.
  The last action's result is a
  one-line toast that goes after about ten seconds; the bottom line is key hints; `h` lists every
  key (the README has the table). Slow actions (starting agents) run in the background.
  `xt tui --demo` shows sample data.
- `xt status`: roster × live state, open items, questions, queue, jobs, approvals, alerts; agents
  running without xt's launch settings (card #165); says whenever the supervisor isn't running.
- `xt inbox`: the Inbox's three groups as in the TUI; `--seen` adds the TUI's folds (answered
  questions, seen notifications, seen friction) under the TUI's labels (`inbox.fold_labels`, card
  #179); in the human's terminal it clears New and marks the friction it printed as seen. `xt answer <id> "..."` (a number picks a decision question's
  option), `xt approve <id>…`, `xt deny <id>`, `xt clear <alert>`.
- `xt schedule <name> <interval>|off [--message …] [--between HH:MM-HH:MM] [--at HH:MM]`.
- `xt reset <name>`: a fresh context for one agent after it saved its notes (`xt checkpoint`);
  `--when-idle` queues it for the supervisor, `--cancel` removes the queued one.
- `xt version`, `xt version check`, `xt version use <tag> [--candidate]`, `xt version rollback` (see Versions above).
- `xt log [--limit N | --full]`: the newest 20 messages by default.
- `xt restart <name>…` (stop and start with fresh instructions) and `xt restart --all` (the
  supervisor and every running agent: the upgrade path), `xt stop <name>` (close without
  retiring), `xt spawn <name>`, `xt retire <name>`,
  `xt down` (stop the supervisor, then every agent, cleanly, so neither the last tick nor the next
  `xt up` raises false alerts; `herdr session stop` bypasses xt and does leave them).
- **Operators and delegation** (card #166, `src/xt/operators.py`). `xt operator add NAME --pid PID`
  registers an outside process acting for the human (its harness: claude, codex or pi, not a team
  agent's) with its start time, and writes a token readable by the human's user only. `cli._who`
  accepts `--as NAME` for a registered operator only when `XT_OPERATOR_TOKEN` holds that token and
  the registered pid with the same start time is the command's own process or an ancestor; either
  alone is refused, and so is the name on any command but `send` (a `report` to the liaison, marked
  as sent on the human's behalf, shown in the human's Inbox and in its own Flow lane; no reply hint)
  and the delegable ones. `xt delegate NAME [--for ≤60m, default 30m] [--only …]` grants
  `restart`, `reset`, `spawn` of an existing agent as it is, and `up`; `cli._delegated` checks the
  stored end time at each command and records `NAME, delegated by human until HH:MM: xt …`.
  `down`, `restart --all` (it takes the team down), answers, approvals, version switches,
  registering and granting stay the human's. `xt status` and the Team header show an active grant.
  The process check needs the operator's process tree to be visible: a command run in Codex's
  sandbox (its own PID namespace) can't be recognised.

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
