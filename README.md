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

![The xt-team in Herdr: the lead's pane on the left, just handed the v0.18.0 proposal to the product manager; the xt 0.17.0 TUI on the right in three bands: Team and Inbox on top, the Flow lane chart in the middle, the answered publish question in Detail at the bottom](docs/screen-v0170.png)

*The xt-team building xt, on 0.17.0. On the left the lead has just passed the v0.18.0 proposal goal
to the product manager. On the right the TUI in three bands: on top the team grouped by harness
(Claude and Codex, with each account's usage windows) next to the Inbox of answered questions; in
the middle the Flow lane chart of messages between the human, xt and the agents, newest on top; at
the bottom the publish question for v0.17.0 that the human answered.*

## What xt can do

Each of these has been shown in real runs, not only in tests (as of v0.10.0). The story behind
each one is in [the story so far](docs/story.md).

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
- **Keep agents in bounds.** No desktop or browser control for agents; public output stays free
  of private details.

Added since (0.11.0 to 0.16.0), each checked against its spec by the product team's quality
analyst before its final release, some on staging teams rather than in daily use yet:

- **No account connectors by default.** Agents start without your mail, files or calendar
  connectors unless you opt one in, and can't act as you: `--as human` works only from your own
  terminal ([Memory and recovery](docs/user-guide.md#11-memory-and-recovery)).

- **Know which xt is running.** The published, installed and running versions are shown apart,
  so a half-finished upgrade is visible ([Updating xt](docs/user-guide.md#7-updating-xt)).
- **Choose a version and roll back.** `xt version use <tag>` merges a release into your team repo
  after checking the state format and taking a verified snapshot; `xt version rollback` undoes it
  ([`xt version`](docs/user-guide.md#xt-version)).
- **Give one agent a fresh context safely.** `xt reset <name>` waits until the agent has saved its
  notes and has no open work ([`xt reset`](docs/user-guide.md#xt-reset)). `--when-idle` queues it
  until the agent is free, and an opt-in policy resets idle agents above a context size in tokens
  ([Resetting automatically](docs/user-guide.md#8-pausing-and-resuming-the-team)).
- **Know when an agent runs without xt's settings.** An agent resumed outside xt (a multiplexer
  restoring its session after a power cycle) is flagged in `xt status`, `xt up`, the Inbox and the
  Team pane, with `xt restart` as the fix ([When something goes wrong](docs/user-guide.md#9-when-something-goes-wrong)).
- **Decide with options.** A decision question shows numbered options, each with its consequence,
  and a recommendation; you answer with a number or your own words
  ([`xt answer`](docs/user-guide.md#xt-answer)).
- **Per-agent permissions for Claude Code agents.** A settings file per agent (or one for all),
  checked before every start; `xt spawn --permissions` sets it for a new agent, and the approval
  warns when a Claude agent would start without one
  ([Memory and recovery](docs/user-guide.md#11-memory-and-recovery), [`xt spawn`](docs/user-guide.md#xt-spawn)).
- **See the Claude plan's usage.** The five-hour and weekly windows in `xt status` and the TUI,
  through a shipped status-line script ([Memory and recovery](docs/user-guide.md#11-memory-and-recovery)).
- **Hear when a goal is done.** Exactly one notification per goal you dispatched, when it's done
  (progress on an open goal doesn't notify), and a "Done since you last looked" list in the Inbox ([Day to day](docs/user-guide.md#4-day-to-day-questions-approvals-alerts-friction)).
- **Short logs by default.** `xt log` prints the newest 20 messages; `--full` prints all
  ([`xt log`](docs/user-guide.md#xt-log)).
- **An Inbox that shows what's new.** Three groups, Needs you, Notifications and Friction, with
  their counts in the panel title; friction you've seen folds away, in the TUI and in `xt inbox`
  ([Day to day](docs/user-guide.md#4-day-to-day-questions-approvals-alerts-friction)).
- **A TUI that reads the same everywhere.** Three bands (Team and Inbox, Work or Flow, the detail
  pane), numbered titles `[n] - Title - info`, the newest on top in every pane, and a key line with
  the focused pane's own keys ([Day to day](docs/user-guide.md#4-day-to-day-questions-approvals-alerts-friction)).
- **Rows that use the whole panel, with ages.** List rows are cut only at the panel's edge and show
  how old they are (`now`, `45s`, `14m`, `3h`, `2d`, `8w`); the focused panel's title is reversed
  ([Day to day](docs/user-guide.md#4-day-to-day-questions-approvals-alerts-friction)).
- **Goals and their tasks in one outline.** The TUI's Work panel lists open goals first with their
  tasks under them, so a stuck goal shows its age; done goals fold away under `done (N)`, and `o`
  shows open work only ([Day to day](docs/user-guide.md#4-day-to-day-questions-approvals-alerts-friction)).
- **The whole thread in the detail pane.** Select a task, a question or a report and the detail
  pane shows its goal's whole conversation in time order, with the selected message marked; the
  supervisor's log is a pop-up on `v`, and its failed wake-ups, notifications and usage recordings
  raise Inbox alerts ([Day to day](docs/user-guide.md#4-day-to-day-questions-approvals-alerts-friction)).
- **Who talked to whom, at a glance.** The TUI's Flow pane draws the ledger as a lane chart: one
  lane per agent, one arrow per message with its type's glyph, messages to you dotted, system
  lines hidden until `t`, and `f` for one agent or one goal's thread
  ([Day to day](docs/user-guide.md#4-day-to-day-questions-approvals-alerts-friction)).
- **Hear when a card is ready to build.** A command you name in `team.toml` lists a Board column;
  the supervisor runs it every few minutes and tells the lead about each card that enters, with one
  alert if the command fails. xt stays independent of the board tool
  ([Periodic work](docs/user-guide.md#5-periodic-work-schedules-quiet-hours-standing-rules)).
- **An operator that acts for you, within limits.** Register an outside process (your own coding
  agent, say) under its own name: it sends reports to the liaison as itself, and for up to an hour
  at a time you can delegate `restart`, `reset`, `spawn` and `up` to it, each one logged. Taking
  the team down, answers and approvals stay yours, and `--as human` stays your terminal's
  ([An operator acting for you](docs/user-guide.md#13-an-operator-acting-for-you)).
- **Network for one Codex agent.** `codex_options` gives a single Codex agent the sandbox's network
  switch (an allowlist of one), shown in its start note, `xt status` and the brief
  ([Memory and recovery](docs/user-guide.md#11-memory-and-recovery)).

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

**Already running a team on an older xt?** Your first upgrade to this version: `xt down`, commit
your team's changes, `git pull upstream main`, then `xt restart --all`, and read each newer
release's **Upgrading** note in [CHANGELOG.md](CHANGELOG.md). From 0.14.0 on, `xt version use
<tag>` picks a release and `xt version rollback` undoes it (see [Updating a team](#updating-a-team)).

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
  A hire's approval names the Claude agent's permissions file, or warns that it has none.
- **Alerts, never repairs.** A crashed, blocked or silent agent raises an alert for you; xt
  doesn't guess at fixes.
- **Any harness per agent.** Adapters in [harnesses/](harnesses/) describe how to start Claude
  Code, Codex and pi, answer their startup dialogs, and check that the first prompt landed.

## The TUI

`xt` (or `xt tui`) opens a lazygit-style view, refreshed every 2 seconds, in three bands. On top,
the **Team** pane (0) on the left, one column: a header with the team, xt's version, what's running
and what needs you; today's tokens and cost; then per harness its account windows as bars and its
agents, one per line (short model such as `sonnet 5.5`, state, and context as tokens, a bar and a
percentage); a team too big for the pane ends with `+N more (widen the terminal)`. Selecting the
header shows xt's versions and today's usage per agent; selecting a harness line shows its
windows, how old each reading is, and why one is unknown (a dim `?` marks it). Beside it, as
high, the **Inbox** (1: Needs you, Notifications and unread Friction, with their counts in its
title; where the TUI starts). In the middle, full width, **Work** (2: goals with their tasks under
them, open goals first, done goals folded under `done (N)`, and goal drafts the liaison is still
shaping) or **Flow** (3), which share the pane like tabs. At the bottom, the detail pane (4: the
selected item with its whole thread in time order), and key hints on the last line: the focused
pane's own keys, then `S`, `/` and `v`. Every title reads `[n] - Title - info`, and every pane has
the newest on top. Flow is the ledger as a swim-lane chart: one
lane per agent (you first, then the liaison, the lead and the rest of the roster), one row per
message with an arrow from sender to receiver, the type's glyph (`◆` goal, `▸` task, `◇` done,
`✉` report, `⚑` ask or approval, `✱` friction, `⚠` alert, `○` note or your own message) and its
label, a dotted line into your lane, `#id` and the first line on the right and the time on the
left. `v` opens the supervisor's log (what `xt watch` did: deliveries, wake-ups, nudges,
notifications, alerts) in a pop-up. The result of your last
action shows for about ten seconds in a one-line toast. The panes keep a fixed size, and the
focused one is shown by its frame colour and a reversed title. List rows use the pane's whole
width and end with their age.

| Key | What it does |
|---|---|
| `0`–`4`, `tab`, `j`/`k`, `enter`, `esc` | Switch panes: 0 Team, 1 Inbox, 2 Work, 3 Flow (2 and 3 swap the middle pane), 4 the detail pane (`tab` goes round them); move (the arrows too); read the detail (`j`/`k` there bring a long thread's hidden rows in); `esc` from the detail pane back to the pane you came from |
| Mouse | A click selects a row in any pane and focuses that pane (the detail pane follows without taking focus); the wheel scrolls Flow and the detail pane |
| `Home` / `End`, page keys (Team) | The first / last agent in view |
| `v` | The supervisor's log, newest first, in a pop-up (`esc` closes it) |
| `/` | Filter the focused pane by text (empty clears it) |
| `t` | Show or hide system lines (starts, stops, settings, wake-ups, nudges) in Flow |
| `f` (Flow) | Show one agent's messages or one goal's thread; the same pick again, or `esc`, clears it |
| `g` / `G`, page keys (Flow) | The newest (top) / oldest message, a page up or down; with the newest selected, Flow follows new messages |
| `space` / `o` | Fold or unfold the selected goal, `done (N)` or `no goal` row / show open work only (Work) |
| `a` / `d` | Approve / deny the selected hire or schedule (Inbox) |
| `s` | Answer the selected question (Inbox); anywhere else, message the liaison. The key line at the bottom says `s answer #288` while it answers. In the dialog (about two-thirds of the screen), enter starts a new line, ctrl+s sends, esc cancels; ctrl+c / ctrl+v copy and paste through the system clipboard |
| `S` | Always message the liaison, even with a question selected |
| `c` | Clear the selected alert, or mark the selected friction seen (Inbox) |
| `enter` or `space` on `(N older, seen) ▸` | Show or hide the friction you've already seen (Inbox) |
| `enter` or `space` on `(N earlier, seen) ▸` | Show or hide what Notifications showed you in the last 7 days (Inbox) |
| `enter` or `space` on `(N answered, last 7 days) ▸` | Show or hide the questions you answered in the last 7 days, each with your answer (Inbox, under Needs you) |
| `f` (Team) | Switch Herdr to the selected agent's workspace |
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
| `xt status` | Team, live state, context and today's usage per agent, team usage and allowance (Codex, and Claude's five-hour and weekly windows through `bin/xt-statusline`), open work, questions, queue, approvals, alerts |
| `xt inbox` | The Inbox as in the TUI: what needs you (questions, approvals, alerts), what's new since you last looked (goals done, reports), unread friction (`--seen`: also the friction you've seen) |
| `xt answer <id> "..."` | Answer a question the liaison asked you (a number picks one of its options) |
| `xt approve [<id>…]` / `xt deny <id>…` | Decide hires and schedules (several ids at once; bare `xt approve` lists what's waiting) |
| `xt clear <alert>` | Dismiss an alert |
| `xt schedule <name> 30m\|off [--message …] [--between 05:00-21:00] [--at 09:30]` | Wake an agent periodically when idle, optionally only within local hours or at a set time |
| `xt spawn`, `xt stop`, `xt retire` | Start, stop (stays in the roster) or retire an agent (`xt spawn … --permissions FILE`: a Claude agent's settings file) |
| `xt restart <name>…` / `xt restart --all` | Restart agents with fresh instructions; `--all` restarts the supervisor too and brings the team back as it was |
| `xt reset <name>` / `xt checkpoint` | A fresh context for one agent, only after it saved its notes (the agent confirms with `xt checkpoint`); `--when-idle` queues it until the agent is free, `--cancel` removes the queued one |
| `xt version` / `xt version check` / `xt version use <tag>` / `xt version rollback` | The team's versions; ask the upstream for the published one now; switch to a release (a candidate with `--candidate`) or undo the last switch |
| `xt send <to> --type <t> "..."`, `xt done <id> "..."`, `xt note "..."` | Messages, closing work, notes (agents add `--as <name>`) |
| `xt friction "..."` | An agent's feedback about xt or its harness; lands in your Inbox |
| `xt goal new\|dispatch\|list` | Goal drafts and dispatch (normally the liaison does this) |
| `xt brief [name]`, `xt log` | Recovery summary and the newest 20 messages (`--limit N`, `--full` for the whole history; `xt log --watch`: the supervisor's events) |
| `xt harnesses` | Installed harnesses and their known limits |
| `xt operator add NAME --pid PID` / `remove` / `list` / `pid` | Register an outside process acting for you under its own name (`pid`: the operator prints what to register) |
| `xt delegate NAME [--for 30m] [--only …]` / `xt delegate --revoke` | Let an operator run `restart`, `reset`, `spawn` and `up` for at most an hour, each one logged |
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
auto_reset = false          # true: reset idle agents without open work above auto_reset_tokens
auto_reset_tokens = 150000  # (an agent's own auto_reset_tokens, or "off", wins); at most once
auto_reset_cooldown_hours = 6   # per agent in this many hours

[notify]                    # questions, approvals, alerts, done goals and the liaison's reports for you
enabled = true
command = "notify-send --app-name=xt {title} {body}"   # or e.g. "curl -s -d {body} ntfy.sh/<topic>"
quiet = ""                  # e.g. "21:00-07:00": no notifications then

[log]
raw_days = 30               # then gzipped; delete_after_days = 0 keeps them forever
```

Each `[[agent]]` has `name`, `role`, `harness`, optional `model`, `reports_to`, `status`, an
optional schedule (`wake_every`, `wake_message`, `wake_between`, `wake_at`), optional
`connectors` (account connectors opted in for that agent; none by default) and, for a Claude Code
agent, optional `permissions` (its settings file, e.g. `"settings/carol.json"`; `[defaults]
permissions` sets one for every Claude agent), and for a Codex agent optional `codex_options`
(only `["sandbox_workspace_write.network_access=true"]`: network for that agent). An optional
`[board_watch]` names a command that lists a Board column's cards, so the lead hears when one
enters it. Runtime facts such as pane ids never go in `team.toml`. Copyable examples of each are in
[docs/examples.md](docs/examples.md).

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

To pick a release on purpose and be able to go back (from 0.14.0 on):

```sh
xt down
git commit -am "team changes"  # xt refuses while tracked files have uncommitted changes
xt version use v0.15.0         # a candidate needs --candidate
xt restart --all
# if it misbehaves: xt down && xt version rollback && xt restart --all
```

`xt version` shows the published, installed and running versions; see
[Updating xt](docs/user-guide.md#7-updating-xt) for the checks and the snapshot it takes.

## Known limits

- Tested on Linux only; most runs used Codex for every agent. The Claude Code and pi adapters
  exist, but they and mixed-harness teams have seen little real use.
- The hierarchy is enforced by `xt`, not by a sandbox: an agent that ignores the protocol could
  still reach other panes through its shell.
- Codex runs agents with network access off; anything an agent fetches needs an escalation that
  Codex's reviewer (or you) approves.
- Costs are estimates from public list prices (`prices.toml`), not bills; no budgets yet.
- Account connectors are off for agents, but command-line tools that hold your credentials (a
  mail CLI, say) are just programs to the harness: xt can't switch them off. A Claude agent's
  settings file can refuse them; a Codex agent is bounded only by its sandbox's escalation review.

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

**Following releases instead of `main`:** to stay on a release, switch to its tag instead of
pulling: `xt version use v0.15.0` (from 0.14.0 on; it merges the tag after its checks, see
[Updating a team](#updating-a-team)). On an older xt, merge the tag by hand:

```sh
git fetch upstream --tags
git merge v0.14.1
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
5. When every card in it is accepted, release the accepted code as final: add a `## [X.Y.Z]`
   heading above the candidates' entries saying which candidate it is, set `version = "X.Y.Z"`,
   `uv lock`, commit (`Release vX.Y.Z`), tag `vX.Y.Z`, push, and `gh release create vX.Y.Z` (not a
   pre-release). Nothing else changes between the accepted candidate and the final release, which
   `git diff vX.Y.Z-rcN vX.Y.Z` shows.

## Development

```sh
uv sync && uv run pytest
```

## License

MIT, see [LICENSE](LICENSE).
