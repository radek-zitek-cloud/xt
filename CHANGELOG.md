# Changelog

All notable changes to xt. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and xt uses [semantic versioning](https://semver.org/) as described in the README's
[Versioning](README.md#versioning) section.

Every release has an **Upgrading** note: what a team that already runs xt has to do after
`git pull upstream main` (or after merging the release tag).

## [Unreleased]

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
