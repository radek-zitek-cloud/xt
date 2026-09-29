# xt user guide

How to run an xt team day to day: the typical lifecycles first, then every command with its TUI
equivalent and when you'd use it. For how xt works inside, see [architecture.md](architecture.md);
for installing, the [README](../README.md).

- [Who's who](#whos-who)
- [Lifecycles](#lifecycles): [a new team](#1-starting-a-new-team) ·
  [the first goal](#2-giving-the-team-its-first-goal) · [hiring](#3-hiring-approvals) ·
  [day to day](#4-day-to-day-questions-approvals-alerts-friction) ·
  [periodic work](#5-periodic-work-schedules-quiet-hours-standing-rules) ·
  [changing course](#6-changing-or-stopping-a-goal) · [updating xt](#7-updating-xt) ·
  [pausing and resuming](#8-pausing-and-resuming-the-team) ·
  [when something goes wrong](#9-when-something-goes-wrong) ·
  [shrinking the team](#10-shrinking-the-team) · [memory and recovery](#11-memory-and-recovery) ·
  [ending a team](#12-ending-a-team)
- [Command reference](#command-reference)

## Who's who

- **You (the human)** talk to the **liaison**, decide what the team spends (hires, schedules), and
  answer questions. Your commands need your own terminal: xt treats a command run from a terminal
  as you, unless it runs inside an agent's session. Every agent xt starts carries `XT_AGENT` in its
  environment, and most agents' shells have no terminal at all, so agents can't act as you. This
  is enforced by xt, not a sandbox: it closes the easy paths.
- **The liaison** turns what you want into goals and relays questions and results. It never does
  the work and never hires.
- **The lead** plans each goal, writes roles and skills, asks to hire members, hands out tasks and
  reports back.
- **Members** do the work and report to the lead (or to a sub-lead).
- **The supervisor** (`xt watch`) delivers messages, starts and stops agents, wakes scheduled
  agents, nudges quiet ones and alerts and notifies you. It runs in its own Herdr workspace.

Agents run the same `xt` commands with `--as <their name>`; the commands marked *agents* below are
mostly theirs, but you can use them too.

## Lifecycles

### 1. Starting a new team

```sh
curl -fsSLO https://raw.githubusercontent.com/radek-zitek-cloud/xt/main/bin/xt-clone.sh
sh xt-clone.sh my-team
```

`xt-clone.sh` clones xt into `./my-team`, runs `xt init` (it asks for the liaison's and lead's
harness and model, codex recommended, and whether hires need your approval; say yes), starts the
team's Herdr session and `xt up`, and attaches you. What you get: the supervisor and the liaison
running, the TUI open, the lead not started yet (it starts with the first goal).

Worth doing once: add your own `origin` remote if you want to push the team's repo somewhere, and
set `[notify] quiet = "21:00-07:00"` in `team.toml` if you don't want notifications at night.

### 2. Giving the team its first goal

1. Switch to the liaison's workspace (in the TUI: select it in Team, press `f`) and say what you
   want: the outcome, constraints, what "done" looks like.
2. The liaison drafts the goal in `goals/drafts/<slug>.md` as you talk (the TUI's Goals panel
   shows it as `✎ … draft`), reads it back, and dispatches it when you say so.
3. The supervisor starts the lead, with the goal in its first prompt. From here the Goals panel
   shows the goal and its tasks, and the Log panel every message.

The answer and message dialog takes about two-thirds of the screen (up to 160 columns wide), with
the question above the text box. It's an ordinary editor: arrows, home/end, ctrl+←/→ by word,
shift+arrows to select, ctrl+z / ctrl+y to undo and redo, ctrl+c / ctrl+x / ctrl+v to copy, cut and
paste through the system clipboard (wl-copy/wl-paste on Wayland, xclip or xsel on X11, pbcopy on
macOS; if none is available the dialog says so, and your terminal's own paste still works). Enter
starts a new line, ctrl+s sends, esc cancels.

You can also message the liaison from the TUI without switching workspaces: `S` always opens a
message to the liaison. `s` does too, except when a question is selected in the Inbox: then it
answers that question. The key line at the bottom of the TUI starts with what `s` will do right
now (`s answer #288 · S message liaison`, or `s/S message liaison`).

### 3. Hiring (approvals)

The lead writes a role (`roles/<role>.md`) and asks to hire someone for it. The request waits for
you: the TUI's Inbox shows `? #12 spawn carol (researcher, codex/default)`, the detail pane shows
the role the lead wrote, and you get a desktop notification.

- Approve with `a` (or `xt approve 12`), deny with `d` (`xt deny 12`). Several at once:
  `xt approve 12 13 14`; `xt approve` alone lists what's waiting.
- On approval the supervisor starts the agent in its own workspace and tells the lead.
- `max_agents` in `team.toml` caps the team; beyond it the lead has to ask you first.

### 4. Day to day: questions, approvals, alerts, friction

Everything that needs you lands in the **Inbox** (TUI panel 4, or `xt inbox`), most with a desktop
notification:

| In the Inbox | What it is | What you do |
|---|---|---|
| `? #212 liaison: Which story…` | A **question** the liaison needs you to decide | `s` on it and type the answer (or `xt answer 212 "…"`, or answer in the liaison's pane) |
| `? #12 spawn …` / `? #14 wake …` | An **approval**: a hire or a schedule | `a` / `d` |
| `⚠ …` | An **alert**: an agent crashed, is blocked or went silent | Look into it (see [9](#9-when-something-goes-wrong)), then `c` |
| `✓ #210 done: Write the weekly digest  #260` | **Done since you last looked**: a goal you dispatched (through the liaison) closed; the detail shows the lead's closing summary (#260) | Read it; `xt log --id 210` for the thread. It clears once you've looked |
| `✱ #230 carol: …` | **Friction**: an agent's feedback about xt or its harness | Read it; it's input for improving xt |
| `✉ #47 liaison: …` | A message to you | Read it |

While a question waits for you, the work that depends on it isn't nudged. If you don't answer,
nothing breaks: the team waits, or follows a standing rule you gave it (see 5).

**When a goal is done** (from 0.15.0). A goal you dispatched (one the liaison opened) gets exactly
one desktop notification when it closes, "goal #210 done". Normally it's the liaison's report to
you about it (its first line is the text); the liaison sends it with `--ref` to the goal. If no such
report arrives within 5 minutes of the closure, the supervisor sends "goal #210 done" with the
first line of the lead's closing summary instead. Other reports the liaison sends you notify too,
once per `--ref`. Tasks, goals the lead opens for sub-teams, and friction never notify, and quiet
hours apply as for questions (what closes at night isn't sent later). "Done since you last looked"
lists closed goals until you've looked: in the TUI, until you leave the Inbox panel (or quit) after
it showed them; with `xt inbox`, once it has printed them in your own terminal (an agent running `xt
inbox` doesn't clear them). It counts from the supervisor's first run on 0.15.0, so older goals
don't appear.

The **Supervisor** panel (6) shows what xt did (deliveries, wake-ups, nudges, notifications). The
Status pane on top has three lines: the team with only what needs you (questions and approvals in
yellow, alerts in red, or "nothing waiting for you"); today's usage and account allowance; and the
result of your last action, in full. The key line at the bottom starts with what `s` will do.

An agent's detail (Team panel, 2) ends with the last lines of its screen, laid out like the
terminal: each line starts on its own line, a line too long for the pane continues on indented
lines marked `↳`, blank lines are dropped, and a line repeated in a row is shown once with `(×3)`.

### 5. Periodic work: schedules, quiet hours, standing rules

Agents only act when prompted, so a periodic duty (a monitor, a scout reading feeds every hour)
needs a **schedule**: the supervisor sends the agent a `wake` message whenever the interval has
passed and it's idle.

- The lead sets schedules for its reports (`xt schedule scout 60m --message "…" --as lead`); each
  one waits for your approval, since every wake-up is a billed turn. You can set one directly:
  `xt schedule scout 60m --between 05:00-21:00`.
- `--between` limits wake-ups to local hours; the first wake after the window opens catches up once.
- A **standing rule** lets the team act without you, e.g. "if I don't pick a story within the
  hour, pick the top one yourself". Put it in the goal; the lead records it in its notes. Work
  started under it still gets its own goal: the lead asks the liaison, which dispatches it without
  asking you (naming the rule) and tells you afterwards.
- A decision like "pass" (none of these) is a decision: a standing auto-pick won't override it.

### 6. Changing or stopping a goal

- **Change it:** tell the liaison; it sends the lead the change with a reference to the goal.
- **Stop it:** tell the liaison the goal is off; the lead closes it with `done` (open tasks under
  it close with it). If you must, close it yourself: `xt done <goal id> "Cancelled by the human"`.
- **Pause everything:** see 8.

### 7. Updating xt

```sh
git pull upstream main
xt restart --all
```

or, if you like to stop the team first (to commit its files, say): `xt down`, pull, `xt restart
--all`. Either way `xt restart --all` restarts the supervisor (new code) and every agent that was
running (new protocol and roles in their first prompt), and brings the team back as it was: after
an `xt down` it restores the agents that were running just before it (agents you had stopped on
purpose stay stopped) and ends with one summary:

```text
restored: liaison, lead, carol (running before xt down)
left stopped: dora (not running before; `xt spawn <name>` starts one)
supervisor: running
```

If nothing was running and nothing was recorded, it says `restored: nobody` and why. Read the release's **Upgrading**
note in [CHANGELOG.md](../CHANGELOG.md) first.

**Which version is the team on?** Three different things, shown in the TUI's Status title, `xt
status` and every agent's brief:

| Label | What it is | Where it comes from |
|---|---|---|
| **published** | the newest final release (candidates don't count) | the supervisor checks the upstream's tags every 6 hours; if the check fails you see the last known one and why |
| **installed** | the xt in the team's repo: what the next command or start runs | the repo's `pyproject.toml`, read every time |
| **running** | the supervisor's version and, per agent, the xt that started it (its first prompt, protocol and reply hints) | recorded when each starts; `mixed` when they differ |

After `git pull` the team is *installed* on the new version but still *running* the old one until
`xt restart --all`; the status line says which processes haven't picked it up yet. A newer
*published* release only produces a notice: nothing upgrades on its own. Processes started by xt
older than 0.12.0 show as `unknown` until their next restart. To verify an upgrade finished: all
three read the same version and no note follows the line. (Teams on xt
0.6.0 or older don't have `restart` yet: `xt down`, pull, `xt`, then `U` in the TUI.)

**Choosing a version, and going back.** `git pull upstream main` takes whatever is newest. To pick
a release on purpose, and to be able to undo it (from 0.14.0 on):

```sh
xt down
git commit -am "team changes"          # xt refuses while tracked files have uncommitted changes
xt version use v0.14.0                 # a candidate: xt version use v0.15.0-rc1 --candidate
xt restart --all
# if it misbehaves:
xt down && xt version rollback && xt restart --all
```

- The team must be fully down (no supervisor, no agent) and no other xt command writing; xt checks.
- `use` fetches the upstream tags and merges the tag into your repo with a merge commit, so your own
  commits and files stay. A conflict (say you edited `roles/lead.md` and the release changed it too)
  stops the switch: xt aborts the merge, names the files and leaves the previous version in place.
  To resolve by hand: `git merge --no-ff <tag>`, fix the files, `git commit`, then run `xt version use
  <tag>` again to finish the checks.
- The team's state (`.xt/state/`) has a **format** number (`.xt/state/format.json`, written by `xt
  up`). xt switches only to a version that says it reads that format, and never converts state; a
  release that needs a new format will say so in its Upgrading note. Every version from 0.12.0 reads
  format 1.
- Before merging, xt takes a verified snapshot of `.xt/state/` (under `.xt/snapshots/`) and records
  a fingerprint of the ledger. The ledger (`.xt/log/`) is never copied back or rewritten: it only
  grows.
- `rollback` reverts the last switch's merge commit (your later commits stay), checks the version
  and that the ledger still starts with the recorded messages, and keeps the current state when
  the format is the same (it matches the ledger). It refuses, and changes nothing, when the snapshot
  is missing, the ledger was altered, the old version can't read the state, or files changed since
  the switch conflict (then: `git revert -m 1 <merge commit>` by hand).
- Neither command starts the team: `xt restart --all` (or `xt up`) does. `xt version` alone shows the
  three versions, the state format and the last switches.

### 8. Pausing and resuming the team

| You want to | Do |
|---|---|
| Stop everything (end of day, reboot, before editing `team.toml` by hand) | `xt down` |
| Start again | `xt` (supervisor, liaison, and the lead if goals are open), then `U` in the TUI for the members |
| Stop the agents but keep the supervisor | `X` in the TUI, or `xt down --keep-supervisor` |
| Restart everything with fresh instructions | `xt restart --all` |
| Stop / start one agent | `x` / `u` on it in the TUI (`xt stop <name>` / `xt spawn <name>`) |
| Give one agent a fresh context, safely | `xt reset <name>` (see below) |
| Give one agent a fresh session right now | `xt restart <name>` |

Stopping keeps an agent in the roster, its notes and its open work; nothing alerts about an agent
you stopped. A schedule's rhythm survives restarts.

**Resetting a heavy agent.** An agent's context grows with every turn, and a big context costs
more per turn and carries stale detail. `xt reset <name>` gives it a fresh one without losing its
work: it is refused while the agent owns an open goal or task (it names them) or is busy; otherwise
xt asks the agent to save what it needs into `members/<name>/notes.md` and confirm with `xt
checkpoint`, waits up to 5 minutes (`--timeout`), and only then starts a fresh session, whose brief
points to the notes and the checkpoint line. No checkpoint, or new work arriving meanwhile, means
nothing is reset. `xt restart <name>` is the emergency route, without a checkpoint. xt never resets
anyone on its own: when an agent's context reaches 70% of its window, `xt status`, the agent's
detail in the TUI and the lead's and liaison's briefs show `reset suggested for …`, and only when the
reading is known, has a window and was observed within the last 2 hours (not in the future, beyond a few minutes of clock difference).

### 9. When something goes wrong

xt alerts, it never repairs. Alerts appear in the Inbox (red `⚠`) and as notifications:

| Alert | Means | Usually |
|---|---|---|
| `blocked:<name>` | The agent is stuck on something in its pane, usually its harness asking for permission | `f` to its workspace, answer it; clears by itself |
| `missing:<name>` | An agent xt started isn't running any more (crashed, or its workspace was closed outside xt) | Find out why (its pane, `xt log --member <name>`), then `u` / `xt spawn <name>` |
| `missing:lead` with goals open | The lead isn't running though there's work | `xt up` |
| `noprompt:<name>` | An agent started but its first prompt never showed up on its screen, so it doesn't know who it is | Stop and start it again (`xt restart <name>`) |
| `silent:<id>` | The owner of an open item ignored two nudges | Look at its pane; ask the liaison or restart the agent |
| `volume:<date>` | Today's message log is unusually big: probably two agents in a loop | `xt log` to see who; stop them |

`c` (or `xt clear <key>`) dismisses an alert once dealt with. `xt status` also warns when the
supervisor isn't running (then nothing is delivered: `xt up`).

### 10. Shrinking the team

- **Stop** an agent you'll want again (`x`, `xt stop`): it stays in the roster.
- **Retire** one that's no longer needed (`R` in the TUI, `xt retire <name>`): its workspace closes
  and it's marked retired in `team.toml`. Its files stay. The lead can also retire its own reports,
  and asks you if it wants to hire again.

### 11. Memory and recovery

Agents lose their memory on restart and when their harness compacts the conversation. xt is built
for that: the ledger, the goal briefs, the roles, skills and each agent's
`members/<name>/notes.md` hold everything that matters, and `xt brief` rebuilds an agent's picture
from them (every first prompt includes it). If an agent seems confused or its context is heavy,
`xt restart <name>` gives it a clean session that starts from its brief.

**No desktop or browser control.** xt starts Codex agents with its computer-use and browser tools
switched off and Claude Code agents with Claude in Chrome refused (their own settings for your
sessions stay as they are); `xt harnesses` shows what each harness blocks, and a start note says
when a harness can't block everything. Agents are told to ask you for anything only a UI can do.

**No account connectors.** Harnesses can reach your accounts through connectors: Claude Code's
claude.ai connectors (Gmail, Drive, Calendar…) and MCP servers, Codex's apps. xt starts agents
without them: Claude Code with `--strict-mcp-config` (no MCP server loads), Codex with its apps
switched off. Your own sessions keep them. When an agent needs one, opt it in by name in
`team.toml` and restart the agent:

```toml
[[agent]]
name = "researcher"
connectors = ["claude.ai Context7"]   # Claude Code: MCP server names as the harness lists them
```

A Claude Code agent then gets exactly those servers (xt lists the others at start and refuses
their tools). A Codex agent takes no opt-in: Codex can switch its apps back on only all at once,
so xt refuses to start a Codex agent that has `connectors` (use Claude Code for that agent).
The start note, the agent's detail and `xt harnesses` show what's opted in and what each harness
covers. Removing the line restores the default at the next start. **Not covered:** command-line
tools that hold your credentials (a mail CLI, for example) are ordinary programs to the harness;
keep such skills out of an agent's reach if it shouldn't use them.

**Permission settings for Claude Code agents.** A Claude Code agent starts in Claude's default
permission mode: its first command outside Claude's built-in safe set waits at a permission
prompt, and an unattended agent then sits blocked (`blocked:<name>`) until you answer it. Give it
a settings file instead, per agent or once for all Claude agents:

```toml
[defaults]
permissions = "settings/claude-agents.json"   # every Claude agent without its own line

[[agent]]
name = "liaison"
permissions = "settings/liaison.json"         # this agent's own file wins
```

xt passes the file with `--settings`. For an agent nobody watches, use `"defaultMode":
"dontAsk"`: anything not on its `allow` list is refused at once instead of waiting:

```json
{"permissions": {"defaultMode": "dontAsk",
  "allow": ["Bash(/path/to/team/bin/xt *)", "Bash(cat *)", "Bash(rg *)", "Edit(goals/drafts/**)"],
  "deny": ["Bash(git push *)", "Bash(curl *)", "WebFetch"]}}
```

Rules:
- The path is relative to the team repo and must stay inside it (no absolute path, no `..`, no
  symlink out). Settings files are yours, like `team.toml`: an agent that could edit its own file
  could widen its own permissions, so the protocol tells agents never to touch them.
- xt checks the file before every start and refuses to start the agent (it never starts it without
  the file) when it's missing, not a JSON object, has an unknown `permissions.defaultMode`, or has a
  malformed `allow`, `deny` or `ask` rule. That check matters: Claude Code (2.1.284) silently ignores
  a broken file, an unknown mode or a bad rule and starts anyway. Other settings keys pass through
  unchecked; Claude Code owns its schema.
- The `[defaults]` file applies only to agents whose harness takes one (Claude Code); Codex and pi
  agents skip it, and the start note says so. A `permissions` line on a Codex or pi agent's own
  entry is refused.
- The start note shows the file, a short hash of its content (a changed file shows a new hash at
  the next start) and the mode, with a warning for `bypassPermissions` or `acceptEdits`, which let
  the agent act without asking. `xt status` and the agent's detail show the path; `xt harnesses`
  shows which harnesses take a file.
- A new agent can get its line at spawn: `xt spawn carol ... --permissions settings/carol.json`
  (from 0.15.0; see [`xt spawn`](#xt-spawn)). The spawn approval names the file, or warns when a
  Claude agent would start without one.
- Pass the file this way rather than as a project `.claude/settings.json`: in a folder Claude Code
  hasn't trusted yet, a project settings file applies its `deny` rules but ignores its `allow` rules
  (seen 2026-09-29).
- Your own `~/.claude/settings.json` still applies to every Claude agent on top of the file: its
  hooks, and its `allow` and `deny` rules. A user-level `allow` rule widens every agent.

**Claude plan usage in status** (from 0.15.0). Claude Code doesn't write its plan's rate limits to
its session logs; it hands them only to a status-line command. xt ships one, `bin/xt-statusline`.
To use it, add a `statusLine` entry to a Claude agent's settings file (one agent is enough; the
reading is account-wide):

```json
{"statusLine": {"type": "command", "command": "/path/to/team/bin/xt-statusline"},
 "permissions": {"defaultMode": "dontAsk", "allow": ["..."]}}
```

After each of that agent's replies, Claude Code passes its status to the script, which keeps the
five-hour and seven-day windows (percent used and reset time, nothing else from the status: no
session ids, paths or costs) in `.xt/state/claude_plan.json` and prints the model and both
percentages as the agent's status line (`Sonnet 5.5 · 5h 5% · 7d 7%`). `xt status` then shows

```text
allowance: claude 5% of 5h, resets Tue 21:30; 7% of 7d, resets Mon 08:00; read 2m ago (account-wide)
```

and the TUI's Status pane shows the same next to the Codex allowance. The plan is shared with you
and anyone else on the account, so the numbers include your own use; they are not one agent's
share.

- **Which team.** The script writes under `XT_ROOT` when that's set, otherwise under the xt checkout
  it's in (`bin/..`), and only into an existing `.xt/state` directory. Point `command` at your team
  repo's own `bin/xt-statusline`. It's one of xt's own files, which agents never edit.
- **When there's no number.** A session's first status call (before any reply) carries no limits;
  the last reading stays and status shows its age. A window whose reset time has passed shows
  `5h window reset, no reading since` rather than the old percentage. A reading older than 3 hours,
  a missing or unreadable file shows `unknown`; the rest of status is unaffected. Status shows the
  Claude line when the team has a Claude agent or a reading exists.
- **Never in the way.** The file is replaced in one step (never half-written), and bad input from
  Claude Code only prints `xt` as the status line.
- Seen on Claude Code 2.1.284; another version that changes the fields shows `unknown`.

**How full is an agent's context?** The Team panel shows it per agent (`~211k/258k`: tokens in
the conversation after its latest turn, out of the model's window), yellow from 70% and red from
85%; the agent's detail, `xt status` and the lead's and liaison's briefs show it too. xt reads it
from the harness's own session log (only the counters, never the conversation) and links each
agent to its log by its first prompt, so a restarted agent starts again from its new session. A
`~` means approximate (Codex reports the latest turn's usage, not a live figure); `?` means the
window isn't known for that model; `—` means nothing is recorded yet, or the agent isn't running
(its detail then shows the last session's figure, labelled as such). Supported: Codex, Claude
Code, pi. The window comes from where it's reliable: Codex writes the usable window of the session
into its log (258,400 tokens for the current models, well below an API model's published maximum,
such as gpt-6-astra's 1.05M); Claude Code doesn't, so xt uses the table in
`harnesses/claude.toml` (1M for the current models, 200k for Haiku 4.5). A Codex log without a
window leaves it unknown rather than borrowing an API figure.

**What does the team cost?** The supervisor records every model call from the agents' session
logs (once a minute; counters only) and attributes it to the goal the agent was working on. You
see tokens and an estimate in dollars: today's team total in the Status pane and `xt status`,
each agent's day in its detail, each goal's total in its detail, and the team's day in the lead's
and liaison's briefs. The estimate uses public list prices from `prices.toml` (or pi's own cost)
and is always labelled "est.": on a subscription you don't pay per token, and nothing here is a
bill. Tokens of a model with no listed price are shown as unpriced, never as zero; calls made on
an agent's behalf (Codex's automatic reviewer, Claude subagents) are counted and shown as
auxiliary. Where a harness reports your account's allowance (Codex: percent of its window and
when it resets), the Status pane and `xt status` show it once per harness. `prices.toml` lists
the current Codex and Claude models at the providers' **Standard** API rates, each row with its
source page and the date it was checked
(2026-09-29 for the table shipped with 0.13.0); xt can't see which tier or plan you're actually
billed on, which is one more reason the figure is an estimate. For Codex models xt uses OpenAI's
short-context rates: right while a session stays below OpenAI's long-context threshold (272K for
gpt-5.5; the Codex sessions checked on 2026-09-29 logged a usable window of 258,400), an
underestimate beyond it. To price another model, add it to
`prices.toml` with its source, tier and checked date.

### 12. Ending a team

`xt down`, then remove the team's Herdr session (`herdr session stop <team>`; only after `xt down`)
and, if you're done with it, the folder. The repo holds the whole history (`.xt/log/`), so keep it
if you might want to look back.

## Command reference

Who: **human** = your terminal only; **both** = you or agents (agents pass `--as <name>`);
**agents** = mostly used by agents. Every command accepts `--as NAME` and `-h`.

| Command | Who | TUI equivalent |
|---|---|---|
| [`xt`](#xt) | human | opens the TUI |
| [`xt init`](#xt-init) | human | none |
| [`xt up`](#xt-up) | human | none (bare `xt` runs it) |
| [`xt down`](#xt-down) | human | `X` stops agents only |
| [`xt restart`](#xt-restart) | human | `x` then `u` for one agent |
| [`xt version`](#xt-version) | show: both; use/rollback: human | none |
| [`xt status`](#xt-status) | both | Status pane + Team panel |
| [`xt inbox`](#xt-inbox) | human | Inbox panel (`4`) |
| [`xt answer`](#xt-answer) | human | `s` on a question |
| [`xt approve`, `xt deny`](#xt-approve-xt-deny) | human | `a` / `d` on an approval |
| [`xt clear`](#xt-clear) | human | `c` on an alert |
| [`xt schedule`](#xt-schedule) | both | none (Team detail shows schedules) |
| [`xt spawn`](#xt-spawn) | both | `u` / `U` for agents in the roster |
| [`xt stop`](#xt-stop) | human | `x` |
| [`xt retire`](#xt-retire) | both | `R` |
| [`xt send`](#xt-send) | both | `S` (to the liaison; `s` too when no question is selected) |
| [`xt done`](#xt-done) | agents | none |
| [`xt note`](#xt-note) | agents | none |
| [`xt friction`](#xt-friction) | agents | shown in Inbox (`✱`) |
| [`xt goal`](#xt-goal) | agents (liaison) | Goals panel shows drafts and goals |
| [`xt brief`](#xt-brief) | both | Team detail (partly) |
| [`xt log`](#xt-log) | both | Log (`5`) and Supervisor (`6`) panels |
| [`xt harnesses`](#xt-harnesses) | human | none |
| [`xt watch`](#xt-watch) | (xt) | Supervisor panel shows its events |
| [`xt tui`](#xt-tui) | human | is the TUI |

### `xt`

`xt` — sets the team up if this clone has no `team.toml` yet (`xt init`), then `xt up`, then opens
the TUI. **Use it** as the one command to start working with a team, any time.

### `xt init`

`xt init [--name NAME] [--session SESSION] [--liaison HARNESS[:MODEL]] [--lead HARNESS[:MODEL]]
[--approval on|off] [--yes] [--no-commit]` — turns a fresh clone of xt into a team's repo: checks
prerequisites, asks for the team name, the Herdr session, the liaison's and lead's harness and model
and whether hires need approval, renames `origin` to `upstream`, writes `team.toml` and the team
folders, and commits. **Use it** once per team; `xt-clone.sh` and bare `xt` run it for you.
`--yes` takes the recommended defaults without questions (e.g. for scripts).

### `xt up`

`xt up` — brings the team to its resting state: starts the supervisor if it isn't running, the
liaison, and the lead if goals are open; lists members that aren't running. **Use it** after
`xt down`, a reboot, or when `xt status` says the supervisor isn't running.

### `xt down`

`xt down [--keep-supervisor]` — stops the supervisor, then every running agent, cleanly (no false
alerts afterwards). **Use it** at the end of a day, before a reboot, or before editing `team.toml`
by hand. `--keep-supervisor` stops only the agents (same as `X` in the TUI).

### `xt reset`

`xt reset <name> [--timeout S]` — a fresh context for one agent, after it saved a checkpoint to its
notes; refused while it owns open work or is busy (see 8). Human only. Agents answer the request with
`xt checkpoint --as <name>` (text on stdin: what the next session should read first).

### `xt restart`

`xt restart <name>…` | `xt restart --all` — stops and starts agents so they get fresh
instructions; `--all` does the whole team and the supervisor, and brings back every agent that was
running (right after an `xt down`: the agents that were running before it). **Use it** after updating xt (`git pull upstream main`), after changing a role, or to give
a confused or heavy agent a clean session.

### `xt version`

`xt version` | `xt version use <tag> [--candidate]` | `xt version rollback` — shows the team's
versions, state format and recent switches; `use` merges an upstream release tag into the team repo
(team down, tracked files committed, state format supported, verified snapshot first); `rollback`
reverts the last switch. **Use it** to upgrade to a chosen release, or to go back one. See
[Updating xt](#7-updating-xt).

### `xt status`

`xt status` — one screen: the published, installed and running xt versions (see 7); every agent with its role, `harness/model`, live state, open work and
context (e.g. `~211k/258k`) and today's usage; today's team total and, where reported, the
account allowance (Codex from its logs; Claude's five-hour and weekly windows through the status
line, see **Claude plan usage in status**);
counts of open goals and tasks, questions for you, queued messages, jobs, approvals and alerts; a
warning if the supervisor isn't running. **Use it** for a quick look without the TUI (e.g. over
ssh), or in scripts.

### `xt inbox`

`xt inbox [--days N] [--limit N]` — what needs you: questions, alerts, pending approvals, goals
done since you last looked (cleared once shown; see 4), friction reported about xt or a harness,
and recent messages to you, each with the command to act on it.
**Use it** when you're not in the TUI; the Inbox panel shows the same.

### `xt answer`

`xt answer <id> "your answer"` — answers a question the liaison asked you; the liaison gets it as
a report and the question closes. **Use it** from a terminal; in the TUI press `s` on the question.
Answering in the liaison's pane works too (it closes the question itself). A longer answer can come
from a heredoc (see `xt send`).

**Questions with options** (from 0.14.0). A decision question shows numbered options, each with
what it leads to, and the asker's recommendation:

```text
When do we ship 0.14.0?

Options:
1. Ship on Friday — the release waits two days
2. Ship today — no staging check
Recommended: 1
Or answer in your own words.
```

Answer with the number (`xt answer 1261 2`), and xt records the option's full text ("Option 2: Ship
today — no staging check"), so the log says what you chose, not just "2"; a number that isn't an
option is refused. In the TUI answer dialog, pressing 1, 2 or 3 while the answer is empty fills in
that option's text, which you can still edit before ctrl+s; once there's text, digits are just
digits. Your own words always work. Agents ask this way with `xt send … --type ask --option
"<option> :: <consequence>" --option … --recommend <n> "the question"`; xt refuses a question with
fewer than two or more than three options, an option without a consequence or no single
recommendation, and sends nothing.

### `xt approve`, `xt deny`

`xt approve [<id>…]`, `xt deny <id>…` — decide hires and schedules the lead asked for. Without ids,
`xt approve` lists what's waiting and the command to approve them all. **Use it** when a
notification says something waits for you; in the TUI, `a` / `d` on the Inbox row (the detail
shows the role or schedule first).

### `xt clear`

`xt clear <key>` — dismisses an alert (`blocked:carol`, `missing:lead`, `silent:212`, …; `xt inbox`
shows the keys). **Use it** once you've dealt with the cause; in the TUI, `c`.

### `xt schedule`

`xt schedule <name> <interval>|off [--message "…"] [--between HH:MM-HH:MM|always] [--at HH:MM|off]`
— wakes an agent every interval (`90s`, `30m`, `2h`, `1d`) when it's idle. `--message` says what to
do each time; `--between` limits wake-ups to local hours (may wrap midnight; `always` removes it).
A daily (or longer) schedule with a window wakes at the window's start, every day, whenever it was
approved; `--at` picks another local time inside the window. The next wake-up is shown by `xt
schedule`, `xt status` and the agent's detail. Options left out keep their current value; `off`
removes the schedule. The lead's requests wait for your
approval and can't go below `min_wake_minutes`; yours apply directly. **Use it** for periodic roles,
to change a schedule's hours, or to switch one off.

### `xt spawn`

`xt spawn <name> [--harness H --role R [--model M] [--reports-to NAME]] [--permissions FILE]` —
starts an agent. For an agent already in the roster (stopped), it starts it again with its role and
harness. For a new one, `--harness` and `--role` are needed and `roles/<role>.md` must exist. The
lead's spawns become approval requests; yours start immediately. **Use it** to bring back a stopped
agent (`u` in the TUI), or to add an agent yourself.

**Permissions file** (from 0.15.0). `--permissions settings/carol.json` gives a Claude Code agent
its settings file: the line is written to its `team.toml` entry, as if you had added `permissions`
there by hand. xt checks the file as it does at every start (see **Permission settings for Claude
Code agents** above) before anything else happens, so a bad file refuses the
spawn request before any approval reaches you. Without the flag, an existing entry keeps its own
line and a team-wide `[defaults]` file applies as usual. The approval names the file and its
`permissions.defaultMode`; when no file applies to a Claude agent it says instead, in red in the
TUI: "WARNING: carol would start without a permissions file, so the operator's own claude defaults
apply". A harness that takes no settings file (codex, pi) refuses `--permissions`, and a team
default is skipped for it with a note.

### `xt stop`

`xt stop <name>` — closes the agent's workspace and keeps it in the roster; nothing alerts about it.
**Use it** to pause one agent; `x` in the TUI. `xt spawn <name>` or `u` brings it back.

### `xt retire`

`xt retire <name>` — closes the agent's workspace and marks it retired in `team.toml`. You retire
anyone; the lead retires its own reports (the supervisor carries it out). **Use it** when an agent
is no longer needed; `R` in the TUI (not for the liaison or lead).

### `xt send`

`xt send <to> --type goal|task|ask|report|done|note|friction [--ref ID] "text"` — the one way agents
talk. xt checks the hierarchy (an agent messages only the one it reports to and its own reports),
logs the message and delivers it when the recipient is idle. **Use it** yourself rarely: to message
an agent directly (`xt send lead --type ask "…"`); `S` in the TUI messages the liaison.

For text with quotes, apostrophes, backticks or several lines, pass it on standard input in a
heredoc whose end word is **quoted** (the quotes stop the shell from touching the text), from your
own terminal or an agent's shell. xt's reply hints use `XT_END` as the end word, because `EOF` can
turn up inside the text itself:

```sh
xt send liaison --type report <<'XT_END'
Standing rule from the human: don't publish anything before 07:00.
It's fine to prepare drafts overnight.
XT_END
```

Agents are told to send every message this way (protocol section 2): text in a quoted argument
goes through the shell first, so backticks and `$(…)` in it would run as commands.

### `xt done`

`xt done <id> "summary, where the result is"` — closes an open goal, task or question and reports
to whoever opened it. **Agents** use it to finish work; **you** can use it to cancel a goal or task
(`xt done 234 "Cancelled"`).

### `xt note`

`xt note [--ref ID] "text"` — logs a note for the sender only, never delivered. **Agents** use it
to keep decisions in the ledger (the liaison records what you asked for this way).

### `xt friction`

`xt friction [--ref ID] "what happened; cost; suggested fix"` — an agent's feedback about xt or its
harness (a command refused something reasonable, a sandbox blocked it). It reaches your Inbox as
`✱`, outside the reporting chain. Friction with the team's own work goes in a `Friction:` line of
the agent's report instead, for the lead.

### `xt goal`

`xt goal new <slug> [title]` creates a draft in `goals/drafts/`; `xt goal dispatch <slug>` freezes
it as `goals/<slug>.md` and sends it to the lead (starting the lead if needed); `xt goal list`
shows drafts and open goals. **The liaison** uses these while shaping goals with you; the TUI's
Goals panel shows drafts and goals.

### `xt brief`

`xt brief [name]` — a ~2k-token summary for an agent: the team, open work, drafts, what waits on
you, recent messages. **Agents** run it after any restart; **you** can read an agent's brief to see
what it knows (`xt brief lead`).

### `xt log`

`xt log [--member NAME] [--id ID] [--type TYPE] [--since DAYS] [--limit N | --full]` — the
message history, filtered. By default it prints the newest 20 messages that match the filters, oldest
of them first, and a first line saying how many older ones were left out; `--limit N` prints the
newest N, `--full` all of them. `--id` alone still prints the whole thread (from 0.15.0; before, `xt
log` always printed everything). `xt log --watch [--limit N]` shows the supervisor's newest events
instead (50 by default). **Use it** to trace a goal (`--id 234` shows the goal and every message
that refers to it directly) or an agent (`--member carol`); the TUI's Log (`5`) and Supervisor
(`6`) panels show the recent part.

### `xt harnesses`

`xt harnesses` — which harnesses are installed here, how their model is chosen, and their known
limits. **Use it** before choosing a harness for the liaison, lead or a new agent.

### `xt watch`

`xt watch` — the supervisor loop. `xt up` starts it in its own workspace; you don't run it by hand.
Its events show in the Supervisor panel and `xt log --watch`.

### `xt tui`

`xt tui [--demo]` — the TUI without the `xt up` step; `--demo` shows it with sample data (no team
needed). Keys: `h` lists them all; the [README](../README.md#the-tui) has the table.
