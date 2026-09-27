# xt architecture: how it works

State of xt as built and tested on 2026-09-26 (after three real runs and the fixes they led to).
The design history and the reasons behind each decision live in the lab repo (`cross-talk/design.md`
and its worklog); this document describes what the code does now.

## In one paragraph

xt runs a hierarchical team of coding agents, each in its own [Herdr](https://herdr.dev) workspace,
in any harness Herdr supports (claude, codex, pi, ...). The human talks to one agent, the
**liaison**. The liaison turns requests into **goals** for the **lead**. The lead designs the team,
writes its roles, and gets members spawned and tasked. Agents never talk to each other directly
and never call Herdr themselves. They run `xt` commands that only write files in the team's repo.
A **supervisor** process (`xt watch`) does everything that touches Herdr: delivering messages,
starting and stopping agents, watching liveness, and alerting the human. The team's whole state
(roster, roles, skills, goals, the message log) is in the repo, so any agent can lose its memory
and recover.

## The pieces

```
 human ──(types in its pane)──▶ liaison ──goal──▶ lead ──task──▶ members
   │                               ▲                ▲               │
   │ xt status / inbox / approve   └───── report / done ─────────────┘
   ▼
 ┌─────────────── team repo (a clone of xt, owned by the user) ───────────────┐
 │ team.toml  roles/  skills/  goals/  members/        .xt/ (runtime, ignored) │
 │   log/*.jsonl (message log = ledger)   state/ queue, jobs, alerts, live …   │
 └──────────────────────────────▲───────────────────────────────▲──────────────┘
          agents' `xt …` commands│ write files only               │ reads/writes
                                 │                    ┌───────────┴───────────┐
                                 │                    │ xt watch (supervisor) │── Herdr CLI ──▶ Herdr
                                 │                    └───────────────────────┘   (--session <team>)
```

| Piece | What it is |
|---|---|
| **Herdr** | The only real prerequisite. Runs the terminal panes, starts harnesses (`agent start --kind`), tells xt each agent's state (idle, working, blocked, done), and injects prompts. Every xt call is `herdr --session <team session> …`, so xt never depends on inherited `HERDR_*` environment variables. |
| **`bin/xt`** | Launcher. Runs the repo's own `.venv` (re-synced from `uv.lock` when that changes), and keeps uv's cache inside the repo, since some sandboxes can't write `~/.cache`. |
| **`xt` CLI** (`src/xt/`) | Python, run through uv. Commands for the human and for agents. |
| **Supervisor** (`xt watch`) | A long-running loop in its own Herdr workspace. The only part of xt that calls Herdr on agents' behalf. |
| **Harness adapters** (`harnesses/*.toml`) | Per harness: Herdr kind, start arguments, model flag, startup dialogs to answer, known limits. |
| **Team repo** | A clone of xt that `xt init` turns into the user's own repo (`origin` renamed `upstream`, so `git pull upstream main` brings xt updates). |
| **mise** | Puts `bin/` on PATH inside the repo and provides uv. |

## Files in a team repo

| Committed (the team's durable state) | Runtime, gitignored (`.xt/`) |
|---|---|
| `team.toml`: roster and settings | `log/YYYY-MM-DD.jsonl`: the message log (append-only); `log/archive/` gzipped old days |
| `roles/<role>.md`: role briefs (`lead` and `liaison` ship; the lead writes the rest) | `state/ledger.json`: id counter + open goals/tasks (rebuildable from the log) |
| `skills/<name>/SKILL.md`: team skills (`.agents/skills` and `.claude/skills` link here) | `state/queue.json`: messages waiting for delivery |
| `goals/drafts/*.md`, `goals/<slug>.md`: goal briefs | `state/jobs.json`: Herdr work requested by agents |
| `members/<name>/notes.md`: durable per-agent notes | `state/live.json`: the supervisor's latest `agent list` |
| `protocol.md`: the protocol every agent follows | `state/alerts.json`, `approvals.json`, `expected.json`, `nudges.json`, `watch.pid` |

xt's own files (`bin/`, `src/`, `protocol.md`, `harnesses/`, `roles/lead.md`, `roles/liaison.md`)
come from upstream and aren't edited by the team, so upstream merges rarely conflict.

### `team.toml`

```toml
[team]      name, session (the Herdr session this team lives in)
[policy]    spawn_approval, max_agents, heartbeat_minutes
[log]       raw_days, delete_after_days, daily_alert_mb, message_max_kb
[defaults]  liaison / lead harness (and optional model)
[[agent]]   name, role, harness, model?, reports_to, status (active | retired),
            wake_every? (e.g. "30m"), wake_message? (set with `xt schedule`)
```

`reports_to` is the communication chain: human ↔ liaison ↔ lead ↔ members (sub-leads possible).
Runtime facts such as pane ids never go in `team.toml`.

## Starting a team

`bin/xt-clone.sh <team>`:
1. Clones xt from GitHub (via `gh` for the private repo), runs `mise trust`.
2. `xt init`: checks prerequisites; asks for liaison and lead harness/model (codex recommended),
   and whether spawns need approval; renames `origin` to `upstream`; writes `team.toml` and the team
   folders; commits.
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

## Messages

Agents talk only through `xt send <to> --as <me> --type … [--ref id]` (or `xt done <id>`).

| Type | Meaning |
|---|---|
| `goal` | What the human wants; liaison → lead only. Opens a ledger item. |
| `task` | A unit of work, sent down the chain; `--ref <goal>`. Opens a ledger item. |
| `ask`, `report` | Questions and progress, up or down. |
| `done` | Closes an open item; the owner's final report. Goes to whoever opened it, or up the sender's chain if it can't reach them (e.g. a goal the human dispatched directly). |
| `note` | Logged for the sender only, never delivered (the liaison records what the human said this way). |
| `system`, `alert`, `approval`, `nudge` | From xt itself. |

- **Policy:** a sender may message its `reports_to` and its own reports; the human may message
  anyone. Only the liaison (or human) opens goals; tasks go downward only; the liaison can't spawn
  or retire. Messages over 4 KB are refused (put payloads in files and send the path).
- **Identity:** agents pass `--as <name>` (told in the first prompt). `--as human` works only from
  a real terminal; agents' shell tools don't have one.
- **Envelope:** delivered text is stamped `[xt #42 task from:lead to:carol ref:#3]`, with a reply
  hint. Unstamped text in a pane comes from the human typing there.
- **Delivery:** an agent's `xt send` only appends to the log and the queue. The supervisor delivers
  when the recipient is idle: **everything queued for it in one prompt**, oldest first, with
  messages about since-closed items marked *stale*. Messages from the human (and the supervisor's
  own) are delivered directly if the recipient is idle. Messages to the human appear in
  `xt inbox`.

## The ledger and recovery

The message log is the ledger. Every message gets a sequential id; `goal`/`task` open an item with
an owner; `done` closes it. `state/ledger.json` keeps the open items and can be rebuilt from the
log, so rotation never loses them. Logs are gzipped after 30 days and never deleted by default.

`xt brief [--as name]` summarises the team, live state, open work, drafts, and recent messages in
about 2k tokens. Every first prompt includes it, and any agent runs it after a restart or context
loss; nothing depends on an agent's own memory. Agents may read their own brief and their reports'
briefs. `xt log` gives the full history.

## The supervisor, one tick every 3 seconds

1. Reload `team.toml`.
2. **Run jobs**: spawns, lazy lead starts, and retires that agents asked for. Then message the
   requester "Done: …" or "Failed: …".
3. Read `herdr agent list`; save it to `state/live.json` (agents in sandboxes read it there).
4. **Drain the queue**: batch-deliver to every recipient that is idle.
5. **Check agents** and raise alerts once each, clearing them when resolved:
   - an agent blocked (usually an approval prompt in its pane);
   - an expected agent missing (crashed, or closed outside xt);
   - goals open but the lead not running (and no job starting it).
6. **Volume**: alert if today's log passes the limit (a likely message loop).
7. **Scheduled wake-ups**: an agent with `wake_every` gets a `wake` message (its `wake_message`)
   when the interval has passed and it's idle with nothing queued, so it never interrupts work. The
   clock starts when the supervisor first sees the schedule. Set with `xt schedule` by the human or
   the agent's lead; this is how a periodic role like a monitor works, since agents only act when
   prompted.
8. **Heartbeat** (every `heartbeat_minutes`): an idle owner of an open item with no recent report
   gets a `nudge`; after two unanswered nudges the human gets an alert instead.
9. **Rotation**, hourly.

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
3. The lead plans, writes role briefs into `roles/`, and requests spawns. With `spawn_approval` on
   (default), the human approves each with `xt approve <id>`. The supervisor starts the agents.
4. The lead sends `task`s; members report and `done` them; the lead integrates and sends `done` for
   the goal to the liaison, who tells the human.

## The human's controls

- Talk to the liaison in its Herdr pane (or type into any agent's pane: that's unstamped and
  legitimate).
- `xt status`: roster × live state, open items, queue, jobs, approvals, alerts; warns if the
  supervisor isn't running.
- `xt inbox`: alerts, pending approvals, messages to the human. `xt approve|deny <id>`,
  `xt clear <alert>`.
- `xt stop <name>` (close without retiring), `xt spawn <name>` (restart), `xt retire <name>`,
  `xt down` (stop every agent and the supervisor cleanly, so the next `xt up` raises no false
  "crashed" alerts; `herdr session stop` bypasses xt and does leave them).
- `xt tui` (also what bare `xt` opens after `xt up`): the lazygit-style overview, refreshed every
  2 s. Five panels: **Goals** (open first, with task progress; detail shows the tasks and the goal
  brief), **Team** (live state; detail shows open work, recent messages and the last lines of the
  agent's screen), **Tasks** (open, then recently closed; detail shows the thread), **Inbox**
  (pending spawn approvals, alerts, messages to the human), **Log** (newest first). Keys: `a`/`d`
  approve or deny the selected spawn (the detail pane shows the role brief the lead wrote; the spawn
  runs in the background), `c` clears an alert, `s` messages the liaison, `f` switches Herdr to the
  selected agent's workspace, `u` starts the selected stopped agent, `U` starts every stopped
  agent, `x` stops the selected agent (it stays in the roster), `X` stops every running agent, `enter` reads the detail pane,
  `h`/`?` help. The team summary and the last action's result are on the top line; the bottom
  line is key hints. `xt tui --demo` shows sample
  data.

## Harnesses

| | claude | codex | pi |
|---|---|---|---|
| Startup dialog | "Is this a project you created or one you trust?" → `down`, `enter` | "Trust this folder?" → `enter` | none (started with `-a`) |
| Repo skills found via | `.claude/skills` → `skills/` | `.agents/skills` → `skills/` | `.agents/skills` → `skills/` (needs trust, hence `-a`) |
| Shell sandbox | none by default | blocks Herdr's socket (so agents never call Herdr) | none |
| Other limits | a Herdr server started from inside Claude Code passes `CLAUDE_CODE_CHILD_SESSION` to its agents (transcript saving off) | shell runs in one shared machine-wide daemon; per-pane env doesn't reach it | `-a` also trusts project `.pi/` config for the run |

Verified live on 2026-09-26: a codex liaison, a claude liaison, and a pi member each started in
a fresh folder with their prompt landing; a codex liaison dispatched a goal from its sandbox and
the supervisor started the lead, which completed it.

## Coexisting with the user's setup

Agents run on a real user's machine, with global instructions, skills, plugins and memory. xt
doesn't need a clean room. The first prompt states that the xt protocol wins for team
coordination only; the protocol is self-contained; skills the team relies on live in its repo;
anything from the user's own setup is optional. xt never writes to user-level skill folders. It
does add a trust entry for the team folder in codex's and claude's config, because answering
their trust dialog is what saves it.

## Known gaps

- **Soft enforcement.** An agent can still call Herdr directly outside a sandbox, or claim another
  agent's name with `--as`. The envelope and the log make it visible; nothing prevents it.
- **The `--as human` terminal guard** is verified for non-interactive codex and claude shells, not
  for every harness.
- **Not built yet:** bypass detection, ping-pong loop detection
  (only the daily-volume alert), `xt config`.
- **Latency.** Agents' messages and jobs wait for the next supervisor tick (up to ~3 s), and
  nothing moves if the supervisor isn't running (`xt status` warns).
