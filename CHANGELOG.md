# Changelog

All notable changes to xt. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and xt uses [semantic versioning](https://semver.org/) as described in the README's
[Versioning](README.md#versioning) section.

Every release has an **Upgrading** note: what a team that already runs xt has to do after
`git pull upstream main` (or after merging the release tag).

## [Unreleased]

## [0.11.0] — 2026-09-28

The second batch from the xt product team, and the first release planned before it was built (five
cards, 8 points). Card numbers from here on are xt Board cards.

### Added

- **Agents start without your account connectors (card #101).** Claude Code agents start with
  `--strict-mcp-config`, so no claude.ai connector (mail, drive, calendar…) and no plugin or user
  MCP server loads; Codex agents start with their apps (ChatGPT connectors) switched off. Your own
  sessions keep them. An agent that needs one gets it by name: `connectors = [...]` on its
  `[[agent]]` in `team.toml`, then restart it (Claude Code: exactly those servers; Codex: its apps
  as a whole). Adapters declare their coverage; `xt harnesses`, the start note and the agent's
  detail show it. Command-line tools that hold your credentials aren't covered (Known limits).
- **`S` in the TUI always messages the liaison (card #102),** even with a question selected, and
  the key line now starts with what `s` will do (`s answer #288 · S message liaison`, or
  `s/S message liaison`).

### Changed

- **Messages go on standard input, exactly as written (card #106).** The reply hint under each
  delivered message, the protocol and the lead's role show `xt send … <<'XT_END'` … `XT_END`: text
  in a quoted argument went through the agent's shell first, so backticks and `$(…)` in it were
  run and their output replaced the words (it happened twice in one team). `xt done`, `xt note`
  and `xt friction` now also take their text on stdin. Checked live with Claude Code, Codex and pi.
- **You can pipe or heredoc a message body into xt (card #103).** xt now decides who is the human
  by whether a command runs inside an agent's session (every agent xt starts has `XT_AGENT` set,
  and a harness among a process's ancestors counts too) and whether it has a controlling terminal,
  not by whether stdin is a terminal. This also closes a gap: a Codex agent running a command in a
  pseudo-terminal passed the old check. New agent names must be lowercase letters, digits, `-`
  and `_`.
- **The agent detail's screen reads like the terminal (card #98):** each captured line starts on
  its own line, a long one continues on indented `↳` lines instead of being re-wrapped mid-word,
  blank lines are dropped and a line repeated in a row is shown once with `(×N)`.

### Upgrading

- `xt down`, `git pull upstream main`, `xt restart --all` (or pull, then `xt restart --all`).
  **Restart every agent:** only agents started by 0.11.0 carry `XT_AGENT`, get the new reply
  hints and protocol, and start without account connectors. If an agent needs a connector, add
  `connectors = [...]` to it in `team.toml` before restarting.

## [0.10.0] — 2026-09-28

The first batch specified by the xt product team (eight cards, 11 points).

### Added

- **Agents without desktop control (#37).** Codex agents start with the computer-use plugin's
  server and Codex's browser and computer-use features switched off for their session only; Claude
  Code agents with Claude in Chrome refused. Adapters declare `desktop_tools` (blocked / none /
  partial); a start note says when a harness can't block everything; `xt harnesses` shows it; the
  protocol tells agents not to drive a GUI and to ask the human.
- **Daily schedules at a set time (#41).** A daily or longer schedule with a window wakes at the
  window's start every day, however late it was approved; `xt schedule … --at HH:MM` picks another
  time inside the window. The next wake-up is shown by `xt schedule`, `xt status` and the agent's
  detail. Wall-clock time holds across daylight-saving changes.
- **A multi-line answer dialog (#38):** `s` opens a text box with the question above it; enter
  starts a new line, ctrl+s sends.
- **A readable Status pane (#44):** line 1 shows the team and only what needs you (questions and
  approvals in yellow, alerts in red, or "nothing waiting for you"; queue and jobs only when stuck
  for over a minute); line 2 today's usage and account allowance in words; line 3 the last action's
  result in full.

### Changed

- **Goal read-backs are questions (#39):** the liaison asks "ready to dispatch?" through xt (Inbox,
  notification) as well as in its pane, and dispatches once; a second dispatch of the same goal now
  says it was already dispatched.
- **Corrections become lessons (#40):** the liaison relays a correction as `Correction from the
  human:`; the lead records it in `members/lead/lessons.md` and fixes the rule behind it.
- **`xt restart --all` after `xt down` (#42)** restores the agents that were running before the
  down (not ones stopped on purpose) and lists them.
- **A stopped agent's context (#43)** isn't shown as current: `—` in Team rows and `xt status`,
  "last session" in its detail and none in briefs.

### Upgrading

- `git pull upstream main`, then `xt restart --all` (or `xt down`, pull, `xt restart --all`). The
  new roles and protocol reach agents on restart. Existing daily schedules with a window move to
  the window's start from their next wake.

## [0.9.1] — 2026-09-28

### Fixed

- **Usage from before a restart was never recorded.** The usage recorder only read session logs
  written since each agent's last start, so the `xt restart --all` of an upgrade dropped everything
  the agents had used before it. It now reads each agent's logs from the last two days (still
  identified by the agent's own first prompt; read positions prevent double counting). Context per
  agent still follows the current session only. The 0.9.0 upgrade note wrongly said earlier usage
  would be included.

### Upgrading

- `git pull upstream main`, then `xt restart --all`. The first pass records the last two days.

## [0.9.0] — 2026-09-28

### Added

- **Usage and estimated cost** (product board card #17, second step of the xt product team's
  spec): the supervisor records every model call from the agents' session logs once a minute
  (counters only) into `.xt/usage/YYYY-MM-DD.jsonl`, attributed to the goal the agent was working
  on and counted on the local day it completed. Shown as tokens and "est." USD: today's team
  total in the Status pane and `xt status`, each agent's day in its detail and `xt status`, each
  goal's total in its detail, the team's day in the lead's and liaison's briefs (not members').
- **Estimates from public list prices** in the new `prices.toml` (gpt-6-sol and Claude Opus 5.5,
  with source and date), or pi's own cost. A model without a price stays "unpriced", never zero.
- **Auxiliary calls counted separately:** Codex's automatic-reviewer sessions and Claude subagent
  turns.
- **Account allowance:** where a harness reports it (Codex), the Status pane and `xt status` show
  it once per harness, e.g. "codex 20% of 7d, resets Sat 19:24 (account-wide)".

### Upgrading

- `git pull upstream main`, then `xt restart --all`. (Use 0.9.1: in 0.9.0 the restart dropped earlier usage.)

## [0.8.0] — 2026-09-28

### Added

- **Context per agent** (product board card #25, specified by the xt product team): how full each
  agent's conversation is, e.g. `~211k/258k`, in the TUI's Team rows (yellow from 70%, red from
  85%) and agent detail, in `xt status`, and in the lead's and liaison's briefs (not members').
  Read from each harness's own session log (counters only, never the conversation) for Codex,
  Claude Code and pi. Each agent is linked to its session by its first prompt, among logs written
  since xt last started it; the link is kept in `.xt/state/sessions.json`. `~` marks approximate
  figures (Codex's latest turn), `?` an unknown window, `—` nothing recorded yet.
- Harness adapters gain `sessions`, `session_format` and `[context_windows]`.
- [docs/story.md](docs/story.md), how xt came to be (linked from the top of the README), and
  [docs/examples.md](docs/examples.md), three real goals word for word with what the teams did.

### Upgrading

- `git pull upstream main`, then `xt restart --all`. Context appears as soon as an agent has taken
  a turn; agents started before the upgrade are found too.

## [0.7.1] — 2026-09-27

### Added

- **User guide** ([docs/user-guide.md](docs/user-guide.md)): the typical lifecycles (a new team,
  the first goal, hiring, day to day, periodic work, changing course, updating, pausing and
  resuming, when something goes wrong, shrinking the team, memory and recovery, ending a team) and
  a reference for every command with who uses it, its TUI equivalent and when it's useful. Linked
  from the README and the architecture doc.

### Upgrading

- Nothing to do: documentation only.

## [0.7.0] — 2026-09-27

### Added

- **Reflection loop.** The protocol asks every agent to add one `Friction: …; cost: …; fix: …`
  line to a `done` or report when something got in the way (and never "no issues"). The lead's
  role: make small, clear fixes to the team's roles and skills and record them in
  `members/lead/lessons.md` (flagging friction that comes back), send bigger changes to the human
  as proposals, summarise a goal's friction in its `done`, and prune now and then.
- **`xt friction "..."`:** a new message type for problems with xt or a harness. It goes to the
  human's Inbox (✱ in the TUI, its own section in `xt inbox`), outside the reporting chain, and is
  never typed into a pane.
- **`xt restart <name>…` / `xt restart --all`:** restart agents with fresh instructions; `--all`
  restarts the supervisor and every running agent and brings the team back as it was. It's now
  the upgrade path after `git pull upstream main`.
- **Bare `xt approve`** lists what's waiting, with the commands (and one to approve them all).
- **Harness and model everywhere:** Team rows and detail, approvals (TUI, `xt approve`,
  `xt inbox`, the brief) and `xt status` show `harness/model` (`codex/default` when no model is set).

### Changed

- **Standing rules:** the liaison may dispatch a goal the lead asks for under a standing rule the
  human set (e.g. an auto-pick) without a read-back, naming the rule and telling the human
  afterwards; the lead's role says work under such a rule still needs a goal.

### Upgrading

- `git pull upstream main`, then `xt restart --all` (on 0.6.0 and earlier, `xt down` then `xt`,
  since `restart` doesn't exist yet). The new roles and protocol reach agents only after a restart.

## [0.6.0] — 2026-09-27

### Added

- **Supervisor events in the TUI.** Everything `xt watch` does (deliveries, jobs, wake-ups,
  nudges, notifications and their failures, alerts, errors) is also kept in
  `.xt/state/watch.log` (rotated at 512 KB) and shown newest first in a new **Supervisor** panel
  (`6`) under the detail pane; failures and alerts are red. `xt log --watch [--limit N]` prints them.
- **Filter a panel with `/`:** type text to show only matching rows (the panel's subtitle shows the
  filter); an empty filter clears it.
- **Goal drafts in the Goals panel:** drafts the liaison is still shaping (`goals/drafts/`) are
  listed first, marked `✎ … draft`; the detail shows the draft.

### Changed

- **Panels keep a fixed size.** The focused panel no longer grows (it made the layout shift on
  every move); focus shows by frame colour only. Panel heights follow how much each usually holds.
- The key hints start with `h help · q quit`, so they stay visible on narrow screens.

### Upgrading

- Restart the team (`xt down`, then `xt`) so the supervisor starts writing its event log; reopen
  the TUI.

## [0.5.0] — 2026-09-27

### Fixed

- **The heartbeat nudged a lead that was working.** A goal whose owner hadn't reported on it yet
  was nudged at the first heartbeat however new it was, and sending tasks under a goal didn't
  count as working on it; in the newsroom run the lead was nudged 7–9 minutes into goals whose
  tasks were running, and spent a turn each time saying so. Now a new item counts from when it
  opened, a task sent under a goal counts as the owner's activity, and an item with open subtasks
  isn't nudged at all (the subtasks' owners are, if they go quiet).
- **`xt down` raised a false "lead is not running but goals are open" alert.** It stopped the
  agents first and the supervisor last, so a tick in between saw the lead gone. It now stops the
  supervisor first. An agent the human stopped (`xt stop`, `x`/`X` in the TUI, `xt down
  --keep-supervisor`) no longer triggers that alert until it's started again.

### Changed

- README rewritten for new readers: what working with a team looks like, how a team works, the
  TUI keys, configuration, updating a team, and known limits.
- docs/architecture.md brought up to date with v0.4.0: questions for the human, notifications,
  quiet hours, the TUI, codex's network sandbox, state files, and known gaps.

### Upgrading

- Restart the team (`xt down`, then `xt`) so the supervisor runs the new code. Nothing else changes.

## [0.4.0] — 2026-09-27

### Added

- **Retire from the TUI:** `R` on a member in the Team panel retires it after a y/n confirmation
  (workspace closed, marked retired in `team.toml`). The liaison and lead can't be retired this
  way; `xt retire` still can.
- **Lead rule: ongoing duties outlive their goal.** Before closing a goal that leaves something
  running (a schedule, a recurring check, a standing rule), the lead makes sure the agent's role or
  a skill fully describes it and points the wake message there, never at the goal brief; its own
  standing duties go in `members/lead/notes.md`.

### Upgrading

- Restart the team (`xt down`, then `xt`) so the lead gets its updated role. Existing wake messages
  that point at a goal brief keep working; ask the lead to move them if you like.

## [0.3.0] — 2026-09-27

### Added

- **Questions for the human.** The liaison sends every decision it needs as
  `xt send human --type ask --ref <what it's about>`. It becomes an open item owned by the human:
  first in the TUI's Inbox (with how long it has waited), in `xt inbox`, in `xt status`, and in the
  "Waiting on the human" section of the liaison's **and the lead's** brief. The human answers with
  `xt answer <id> "..."` or `s` on it in the TUI; the answer reaches the liaison as a report with
  `--ref` to the question, which closes it. The liaison closes a question itself (`xt done`) when
  the human answered in its pane or the question is superseded.
- **No nudges while waiting on the human.** The heartbeat leaves alone any open item that an open
  question refers to (directly, or through the messages it is about).
- **Notifications.** The supervisor runs a command for each new question, approval request and
  alert for the human: `[notify]` in `team.toml` with `enabled`, `command` (default
  `notify-send --app-name=xt {title} {body}`; any command with `{title}`/`{body}`, e.g.
  `curl -s -d {body} ntfy.sh/<topic>` for a phone) and an optional `quiet` window such as
  `"21:00-07:00"`.
- Liaison and lead roles and the protocol describe questions.

### Changed

- The lead's brief now includes "Waiting on the human", so it knows what's pending and since when.

### Upgrading

- Restart the team (`xt down`, then `xt`) so the supervisor runs the new code and the liaison and
  lead get their updated roles.
- Notifications are on by default with `notify-send`. To change or silence them, add a `[notify]`
  section to `team.toml` (new teams get one from `xt init`), e.g. `quiet = "21:00-07:00"` or
  `enabled = false`.

## [0.2.0] — 2026-09-27

### Added

- **Quiet hours for schedules.** `wake_between = "05:00-21:00"` on an agent in `team.toml`, set with
  `xt schedule <name> <interval> --between 05:00-21:00` (local time; a window may wrap midnight,
  e.g. `22:00-06:00`; `--between always` removes it). The supervisor wakes the agent only inside the
  window; an agent that became due outside it gets one wake-up when the window opens, not one per
  missed interval. Agent-set windows go through the same approval as the schedule. The window shows
  in the brief, the TUI's Team detail, wake messages and approval requests.
- The lead's role says to use a window when a goal asks for quiet hours, rather than having the agent
  skip runs itself (each skipped run is still a billed turn).

### Changed

- `xt schedule` keeps an agent's current wake message and window when `--message` or `--between`
  is left out (before, a schedule set without `--message` dropped the message). `off` still clears
  everything.

### Upgrading

- Restart the team (`xt down`, then `xt`) so the supervisor runs the new code and the lead gets the
  updated role.
- A schedule an agent answers with "quiet hours" can move into xt: from your terminal,
  `xt schedule <name> <interval> --between HH:MM-HH:MM` (it keeps the wake message).

## [0.1.0] — 2026-09-27

The first public release, under the MIT licence. Tested with a six-agent newsroom team (all codex)
that hired its own scout, researched, wrote, fact-checked and published articles.

### Added

- **Teams in a git repo.** `xt init` turns a clone of xt into a team's own repo (`origin` becomes
  `upstream`), asks for the liaison's and lead's harness and model (codex recommended) and writes
  `team.toml`. `bin/xt-clone.sh <team>` goes from nothing to a running team in one command.
- **Hierarchy.** The human talks to the liaison; the liaison hands goals to the lead; the lead plans,
  writes roles and skills, and hires members (`reports_to` is the communication chain). Shipped roles:
  `roles/liaison.md`, `roles/lead.md`; the protocol is `protocol.md`.
- **Messages and the ledger.** Typed messages (`goal`, `task`, `ask`, `report`, `done`, `note`),
  queued and delivered by the supervisor when the recipient is free, in an append-only ledger that
  also serves as the team's memory (`xt brief`, `xt inbox`, `xt log`). Leftover tasks close with
  their goal.
- **The supervisor (`xt watch`).** Delivers messages, runs spawn/start/retire jobs for agents (agents
  never call Herdr themselves), a heartbeat that nudges idle owners of open work, alerts on crashed,
  blocked or silent agents and on log volume, and log rotation.
- **Approvals.** Spawns and agent-set schedules wait for the human (`xt approve`, `xt deny`, several
  ids at once); the liaison's brief lists what waits on the human.
- **Scheduled wake-ups.** `xt schedule` and `wake_every`/`wake_message` in `team.toml`, with a
  minimum interval for agent-set schedules.
- **Harness adapters** for Claude Code, Codex and pi (`harnesses/*.toml`), including answering
  startup dialogs and verifying that the first prompt landed.
- **Lifecycle.** `xt up`, `xt spawn`, `xt stop`, `xt retire`, `xt down` (stop a whole team cleanly).
- **The TUI** (`xt`, lazygit style): Goals, Team, Tasks, Inbox and Log panels with a detail pane;
  approve/deny, clear alerts, send to the liaison, jump to an agent's workspace, start and stop
  agents one by one or all at once, key help on `h`.
- `xt --version`; the version also shows in `xt status` and the TUI's Status pane.

### Upgrading

- Nothing to migrate: this is the first release. Teams created before it are already on this code
  once they have pulled `a244d15` or later.
