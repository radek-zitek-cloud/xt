# xt

Hierarchical teams of AI agents that run in any harness (Claude Code, Codex, pi) on top of
[Herdr](https://herdr.dev). You talk to one agent, the **liaison**. It turns what you want into
goals for a **lead**, which designs and runs whatever team the work needs: a newsroom, a dev team,
an accounting desk. xt owns the coordination (messages, the ledger of open work, the supervisor,
approvals, recovery), so an agent only needs a shell and a prompt.

**New here?** Start with [What xt can do](#what-xt-can-do). Then read [the story so far](docs/story.md): how xt came to be in a few days, what broke
and what we learned; and [Goals in practice](docs/examples.md): real goals given to teams, word
for word.

**Status:** 0.x, early but in daily use (current release: see [CHANGELOG.md](CHANGELOG.md)). Two teams run on it: a six-agent newsroom that hires its
own scout, finds stories in RSS feeds every hour, and researches, writes, fact-checks and publishes
articles; and a product team (a product manager and a quality analyst) that runs xt's own backlog
and accepts its releases. Most runs so far used Codex for every agent. **Using it day to day:
[docs/user-guide.md](docs/user-guide.md)** (lifecycles and every command); how it works inside:
[docs/architecture.md](docs/architecture.md).

![The newsroom pilot team in Herdr: the liaison's pane on the left, asking which story to write next; the xt TUI on the right with goals, team, tasks, inbox, log and a goal brief in the detail pane](docs/screen.png)

*The newsroom pilot in Herdr: on the left the liaison asks which of the scout's stories to write
next; on the right the xt TUI shows the goals, the team (all on Codex), tasks, inbox and log, with
the scout goal's brief in the detail pane.*

## What xt can do

Each of these has been shown in real runs, not only in tests (v0.10.0). The story behind each one
is in [the story so far](docs/story.md).

- **Run persistent, named agents with roles.** A liaison, a lead and members, each in its own
  workspace, keep working while you're away. Codex has carried every real team so far; adapters for
  Claude Code and pi exist.
- **Keep you to decisions only.** Questions wait in one Inbox (TUI or `xt inbox`) with a desktop
  notification; you never have to watch an agent's pane.
- **Deliver every message through a supervisor, with a ledger.** Nothing is lost, and every step
  can be audited later: the quality analyst accepts work partly on evidence from the ledger.
- **Work in goals, read back before dispatch.** The liaison reads a goal back to you, lets you
  revise it, and dispatches it exactly once.
- **Run on schedules.** Daily wakes at a fixed local time, hourly scouts, quiet hours that hold.
- **Act on its own within rules you set.** The newsroom picked and published stories when you
  didn't answer within an hour, let your own picks go first, and stopped at its limit of six a day.
- **Learn from corrections.** A correction from you becomes a recorded lesson and a fixed rule, and
  a regular rules review keeps the rules consistent and short.
- **Manage its own product.** A product team runs xt's backlog on a Kanban board with public specs
  and release pages; only you pass the approval points.
- **Accept work independently.** A quality analyst checks each delivered card against its spec,
  criterion by criterion; a final PASS closes the card, anything else waits for you.
- **Show context and cost.** How full each agent's context is, tokens and estimated cost per turn,
  and how much of the subscription allowance the week has used.
- **Survive restarts.** `xt down` then `xt restart --all` brings back the team that was running;
  agents recover from files and a brief, not from memory.
- **Keep agents in bounds.** No desktop or browser control and none of your account connectors
  (mail, files, calendar) unless you opt one in; public output stays free of private details.

What it can't do yet is in [Known limits](#known-limits).

## What working with a team looks like

1. You tell the liaison, in its Herdr pane, what you want. It shapes that into a goal with you and
   hands it to the lead.
2. The lead plans the work, writes the roles and skills the team needs, and asks to hire agents.
   **You approve every hire** (and every schedule an agent sets up), because each agent turn costs
   money.
3. Members work in their own Herdr workspaces and report up the chain; xt delivers every message,
   keeps the ledger of open goals and tasks, and nudges agents that go quiet.
4. When the team needs a decision from you, the liaison asks it as a **question**: it waits in
   your Inbox (TUI, `xt inbox`), with a desktop notification, until you answer.
5. The lead reports the goal done; the liaison tells you what was achieved and where the results
   are.

Everything the team builds up (roles, skills, goal briefs, notes, outputs) is plain files in the
team's own git repo, so an agent that restarts or loses its context picks up from the files, not
from memory.

## Prerequisites

- Linux with [Herdr](https://herdr.dev) (xt is developed and tested on Arch Linux)
- [mise](https://mise.jdx.dev) activated in your shell (it provides `uv` and puts `bin/` on PATH)
- At least one harness CLI: `codex` (recommended for the liaison and lead), `claude`, or `pi`
- Optional: `notify-send` for desktop notifications, `gh` for cloning

## Quick start

```sh
curl -fsSLO https://raw.githubusercontent.com/radek-zitek-cloud/xt/main/bin/xt-clone.sh
sh xt-clone.sh my-team
```

That clones xt into `./my-team`, runs `mise trust` and `xt init` (team and Herdr session both
named `my-team`; it asks which harness and model to use for the liaison and lead, and whether
hires need your approval), starts the `my-team` Herdr session in the background, runs `xt up`,
and attaches you to the session. `--no-start` stops after setup. The same by hand:

```sh
git clone https://github.com/radek-zitek-cloud/xt.git my-team && cd my-team
mise trust
herdr --session my-team        # open (or attach) the team's Herdr session
xt                             # first run asks a few questions (xt init), then starts the team
```

`xt` starts the supervisor and the liaison, then opens the TUI. Switch to the liaison's workspace
and tell it what you want. The lead starts when the first goal is dispatched.

Your clone becomes your team's own repo: `xt init` renames `origin` to `upstream`, so xt updates
come with `git pull upstream main` (see [Updating a team](#updating-a-team)).

## How a team works

- **Hierarchy, not a mesh.** human ↔ liaison ↔ lead ↔ members (sub-leads possible). Each agent
  may message only the agent it reports to and its own reports; `xt send` refuses anything else.
  The protocol every agent follows is [protocol.md](protocol.md); the shipped roles are
  [roles/liaison.md](roles/liaison.md) and [roles/lead.md](roles/lead.md). The lead writes every
  other role.
- **Agents never touch Herdr.** They write messages and requests with `xt`; the supervisor
  (`xt watch`, in its own pane) delivers messages when the recipient is idle, starts and retires
  agents, and runs the heartbeat. This also works when a harness sandboxes the agent's shell.
- **The ledger is the memory.** Every message is logged; goals, tasks and questions stay open
  until closed. `xt brief` rebuilds an agent's picture of the team from files alone.
- **The team improves itself.** Agents add a one-line `Friction:` to a report when something got
  in the way; the lead fixes its team's roles and skills and keeps `members/lead/lessons.md`, and
  problems with xt or a harness reach you as `friction` in the Inbox.
- **You stay in control of spending.** Hires and agent-set schedules wait for your approval;
  schedules have a minimum interval and can be limited to local hours (`--between 05:00-21:00`).
- **Alerts, never repairs.** A crashed, blocked or silent agent raises an alert for you; xt
  doesn't guess at fixes.
- **Any harness per agent.** Adapters in [harnesses/](harnesses/) describe how to start Claude
  Code, Codex and pi, answer their startup dialogs, and check that the first prompt landed.

## The TUI

`xt` (or `xt tui`) opens a lazygit-style view, refreshed every 2 seconds: **Goals** (with goal
drafts the liaison is still shaping), **Team** (with each agent's context, e.g. `~211k/258k`),
**Tasks**, **Inbox** and **Log** panels on the left,
the detail pane on the right with the **Supervisor** panel under it (what `xt watch` did:
deliveries, wake-ups, nudges, notifications, alerts), the Status pane on top (the team and only what
needs you, highlighted; today's usage and allowance; the last action's result) and key hints at the
bottom. Panels keep a fixed size; the focused one is shown by its frame colour.

| Key | What it does |
|---|---|
| `1`–`6`, `tab`, `j`/`k`, `enter` | Switch panels, move, read the detail |
| `/` | Filter the focused panel by text (empty clears it) |
| `a` / `d` | Approve / deny the selected hire or schedule (Inbox) |
| `s` | Answer the selected question (Inbox); anywhere else, message the liaison. The key line at the bottom says which (`s answer #288` or `s/S message liaison`). In the dialog, enter starts a new line and ctrl+s sends |
| `S` | Always message the liaison, even with a question selected |
| `c` | Clear the selected alert |
| `f` | Switch Herdr to the selected agent's workspace |
| `u` / `U` | Start the selected stopped agent / every stopped agent |
| `x` / `X` | Stop the selected agent / every agent (they stay in the roster) |
| `R` | Retire the selected member (not the liaison or lead) |
| `h` or `?`, `q` | All keys, quit |

`xt tui --demo` shows sample data.

## Commands

The [user guide](docs/user-guide.md#command-reference) describes each one, with its TUI
equivalent and when you'd use it.

| Command | What it does |
|---|---|
| `xt` | Set up if needed, `xt up`, then open the TUI |
| `xt init` | Make this clone your team's repo (asks: team name, session, liaison/lead harness and model, hire approval) |
| `xt up` | Start the supervisor and liaison (and the lead if goals are open) |
| `xt down` | Stop every agent and the supervisor cleanly (`--keep-supervisor`: agents only) |
| `xt status` | Team, live state, context and today's usage per agent, team usage and allowance, open work, questions, queue, approvals, alerts |
| `xt inbox` | What needs you: questions, alerts, approvals, recent messages |
| `xt answer <id> "..."` | Answer a question the liaison asked you |
| `xt approve [<id>…]` / `xt deny <id>…` | Decide hires and schedules (several ids at once; bare `xt approve` lists what's waiting) |
| `xt clear <alert>` | Dismiss an alert |
| `xt schedule <name> 30m\|off [--message …] [--between 05:00-21:00]` | Wake an agent periodically when idle, optionally only within local hours |
| `xt spawn`, `xt stop`, `xt retire` | Start, stop (stays in the roster) or retire an agent |
| `xt restart <name>…` / `xt restart --all` | Restart agents with fresh instructions; `--all` restarts the supervisor too and brings the team back as it was |
| `xt send <to> --type <t> "..."`, `xt done <id> "..."`, `xt note "..."` | Messages, closing work, notes (agents add `--as <name>`) |
| `xt friction "..."` | An agent's feedback about xt or its harness; lands in your Inbox |
| `xt goal new\|dispatch\|list` | Goal drafts and dispatch (normally the liaison does this) |
| `xt brief [name]`, `xt log` | Recovery summary and full message history (`xt log --watch`: the supervisor's events) |
| `xt harnesses` | Installed harnesses and their known limits |
| `xt watch` | The supervisor loop (`xt up` runs it in its own pane) |
| `xt --version` | The xt version |

## Configuration

`team.toml` holds the roster and settings; `xt init` writes it with comments. The main settings:

```toml
[policy]
spawn_approval = true       # the lead's hires wait for you
max_agents = 8              # soft cap; beyond it the lead must ask you first
heartbeat_minutes = 15      # how often the supervisor checks for silent agents
schedule_approval = true    # agent-set schedules wait for you
min_wake_minutes = 15       # shortest schedule an agent may request

[notify]                    # questions, approvals and alerts for you
enabled = true
command = "notify-send --app-name=xt {title} {body}"   # or e.g. "curl -s -d {body} ntfy.sh/<topic>"
quiet = ""                  # e.g. "21:00-07:00": no notifications then

[log]
raw_days = 30               # then gzipped; delete_after_days = 0 keeps them forever
```

Each `[[agent]]` has `name`, `role`, `harness`, optional `model`, `reports_to`, `status`, an
optional schedule (`wake_every`, `wake_message`, `wake_between`, `wake_at`) and optional
`connectors` (account connectors opted in for that agent; none by default). Runtime facts such as
pane ids never go in `team.toml`.

## Layout

| xt's own (from upstream) | Your team's (committed in your repo) | Runtime (gitignored) |
|---|---|---|
| `bin/`, `src/`, `tests/`, `pyproject.toml`, `uv.lock`, `mise.toml`, `prices.toml` | `team.toml` (roster, settings) | `.xt/log/` message log = ledger; `.xt/usage/` per-turn usage |
| `protocol.md`, `harnesses/`, `docs/` | `roles/*` written by the lead | `.xt/state/` queue, jobs, approvals, alerts, snapshots |
| `roles/lead.md`, `roles/liaison.md` | `skills/*`, `goals/`, `members/<name>/`, outputs | `.xt/cache/` |

`.agents/skills` and `.claude/skills` are symlinks to `skills/`, so codex, pi and claude also
discover team skills natively.

## Updating a team

```sh
git pull upstream main         # or merge a release tag, see Versioning
xt restart --all               # supervisor and every running agent, with the new code and instructions
```

Running agents keep the instructions they started with, so restart after every update. If you
prefer to stop the team first, `xt down`, update, then `xt restart --all` brings back exactly the
agents that were running (from 0.10.0 on; an older `xt down` records nothing, so start them with
`xt` and then `U` in the TUI). Read the
**Upgrading** note of each new release in [CHANGELOG.md](CHANGELOG.md) for anything else to do.

## Known limits

- Tested on Linux only; most runs used Codex for every agent. The Claude Code and pi adapters
  exist, but they and mixed-harness teams have seen little real use.
- The hierarchy is enforced by `xt`, not by a sandbox: an agent that ignores the protocol could
  still reach other panes through its shell.
- Codex runs agents with network access off; anything an agent fetches needs an escalation that
  Codex's reviewer (or you) approves.
- Costs are estimates from public list prices (`prices.toml`), not bills; no budgets yet.
- Account connectors are off for agents, but command-line tools that hold your credentials (a
  mail CLI, say) are just programs to the harness: xt can't switch them off.

## Versioning

xt uses [semantic versioning](https://semver.org/); `xt --version` prints the version, and
[CHANGELOG.md](CHANGELOG.md) lists every release with an **Upgrading** note for running teams.

A change is **breaking** when a team has to change its own files or its agents would behave
differently: the CLI (commands, flags), the `team.toml` format, the message protocol
(`protocol.md`, message types, the envelope), the ledger and `.xt/` state formats, the harness
adapter format, and the shipped `roles/lead.md` and `roles/liaison.md`.

While xt is `0.x`, a breaking change or a notable feature raises the minor version (0.1 → 0.2) and a
fix raises the patch version (0.1.0 → 0.1.1). `1.0.0` comes once `team.toml` and the protocol are
stable.

**Following releases instead of `main`:** to stay on a release, merge its tag instead of pulling:

```sh
git fetch upstream --tags
git merge v0.5.0
```

## Releasing

A release starts as a **candidate** and becomes final only once it's accepted, so a team that
upgrades to check a release never runs code presented as final that nobody accepted yet.

1. Move the `[Unreleased]` entries in CHANGELOG.md under a new `## [X.Y.Z-rcN] — YYYY-MM-DD`
   heading, with an **Upgrading** note.
2. Set `version = "X.Y.ZrcN"` in `pyproject.toml` (Python's spelling of `-rcN`), run `uv lock` and
   `uv run pytest`.
3. Commit (`Release vX.Y.Z-rcN`), tag it `git tag -a vX.Y.Z-rcN -m "xt vX.Y.Z-rcN"`, push both
   (`git push origin main vX.Y.Z-rcN`) and create a **pre-release** from the tag with that
   section as its notes: `gh release create vX.Y.Z-rcN --prerelease --title "xt vX.Y.Z-rcN" --notes-file <section>`.
4. If acceptance finds a problem, fix it and release `-rcN+1` the same way.
5. When every card in it is accepted, release the accepted code as final: rename the heading to
   `## [X.Y.Z]`, set `version = "X.Y.Z"`, `uv lock`, commit (`Release vX.Y.Z`), tag `vX.Y.Z`, push,
   and `gh release create vX.Y.Z` (not a pre-release). Nothing else changes between the accepted
   candidate and the final release.

## Development

```sh
uv sync && uv run pytest
```

## License

MIT, see [LICENSE](LICENSE).
