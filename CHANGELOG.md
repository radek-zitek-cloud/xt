# Changelog

All notable changes to xt. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and xt uses [semantic versioning](https://semver.org/) as described in the README's
[Versioning](README.md#versioning) section.

Every release has an **Upgrading** note: what a team that already runs xt has to do after
`git pull upstream main` (or after merging the release tag).

## [Unreleased]

### Changed

- README rewritten for new readers: what working with a team looks like, how a team works, the
  TUI keys, configuration, updating a team, and known limits.
- docs/architecture.md brought up to date with v0.4.0: questions for the human, notifications,
  quiet hours, the TUI, codex's network sandbox, state files, and known gaps.

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
