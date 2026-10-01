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
  [ending a team](#12-ending-a-team) · [an operator acting for you](#13-an-operator-acting-for-you)
- [Command reference](#command-reference)

## Who's who

- **You (the human)** talk to the **liaison**, decide what the team spends (hires, schedules), and
  answer questions. Your commands need your own terminal: xt treats a command run from a terminal
  as you, unless it runs inside an agent's session. Every agent xt starts carries `XT_AGENT` in its
  environment, and most agents' shells have no terminal at all, so agents can't act as you. This
  is enforced by xt, not a sandbox: it closes the easy paths. A process working for you outside
  the team (an **operator**) gets its own name instead, and only what you delegate to it (see 13).
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
2. The liaison drafts the goal in `goals/drafts/<slug>.md` as you talk (the TUI's Work panel
   shows it as `✎ … draft`), reads it back, and dispatches it when you say so.
3. The supervisor starts the lead, with the goal in its first prompt. From here the Work panel
   shows the goal with its tasks under it, and the Flow pane every message as a lane chart.

The answer and message dialog takes about two-thirds of the screen (up to 160 columns wide), with
the question above the text box. It's an ordinary editor: arrows, home/end, ctrl+←/→ by word,
shift+arrows to select, ctrl+z / ctrl+y to undo and redo, ctrl+c / ctrl+x / ctrl+v to copy, cut and
paste through the system clipboard (wl-copy/wl-paste on Wayland, xclip or xsel on X11, pbcopy on
macOS; if none is available the dialog says so, and your terminal's own paste still works). Enter
starts a new line, ctrl+s sends, esc cancels.

You can also message the liaison from the TUI without switching workspaces: `S` always opens a
message to the liaison. `s` does too, except when a question is selected in the Inbox: then it
answers that question. The key line at the bottom of the TUI says `s answer #288` while it will do
that (from 0.17.0, among the Inbox's keys, before `S message liaison`).

### 3. Hiring (approvals)

The lead writes a role (`roles/<role>.md`) and asks to hire someone for it. The request waits for
you: the TUI's Inbox shows `⚑ #12 spawn carol (researcher, codex/default)`, the detail pane shows
the role the lead wrote, and you get a desktop notification.

- Approve with `a` (or `xt approve 12`), deny with `d` (`xt deny 12`). Several at once:
  `xt approve 12 13 14`; `xt approve` alone lists what's waiting.
- On approval the supervisor starts the agent in its own workspace and tells the lead.
- `max_agents` in `team.toml` caps the team; beyond it the lead has to ask you first.

### 4. Day to day: questions, approvals, alerts, friction

Everything that needs you lands in the **Inbox** (TUI panel 1, or `xt inbox`), most with a desktop
notification. From 0.16.0 it has three groups, each under its heading, and a group with nothing in
it isn't shown:

| In the Inbox | What it is | What you do |
|---|---|---|
| **NEEDS YOU** | Stays until you answer, decide or clear it; newest first (from 0.17.0) | |
| `⚑ #212 liaison: Which story…  3 options` | A **question** the liaison needs you to decide (`3 options` when it offers choices) | `s` on it and type the answer (or `xt answer 212 "…"`, or answer in the liaison's pane) |
| `⚑ #12 spawn …` / `⚑ #14 wake …` | An **approval**: a hire or a schedule | `a` / `d` |
| `⚠ …` | An **alert**: an agent crashed, is blocked or went silent; or (from 0.16.0) the supervisor failed to wake an agent, to send a notification or to record usage (`⚠ ×3 wake-up failed: …`) | Look into it (see [9](#9-when-something-goes-wrong)), then `c` |
| `(2 answered, last 7 days) ▸` | (from 0.16.1) The questions you answered in the last 7 days, folded: `✓ #2098 v0.16.1 spec → 1: Approve and build`, newest first; the detail pane shows the question with its options, your answer and the thread | `enter` or `space` shows them; again folds them |
| **NOTIFICATIONS** | (called NEW before 0.17.0) Since you last looked, newest first, in bold; clears once you've looked | |
| `✓ #210 done: Write the weekly digest  #260` | A goal you dispatched (through the liaison) closed; the detail shows the lead's closing summary (#260) and the goal's whole thread | Read it |
| `✉ #47 liaison: …` | A report to you | Read it |
| `(3 earlier, seen) ▸` | (from 0.16.1) What Notifications showed that you've since seen, from the last 7 days, folded | `enter` or `space` shows it (newest first, dim); again folds it |
| **FRICTION** | Unread friction only, newest first | |
| `✱ #230 carol: …` | **Friction**: an agent's feedback about xt or its harness | Read it; it's input for improving xt. `c` marks it seen at once |
| `(12 older, seen) ▸` | The friction you've already seen, folded | `enter` or `space` (from 0.16.1) shows it (newest first); again folds it |

The Inbox's title counts what's in the groups: `[1] - Inbox - ⚑ 2 · ✉ 1 · ✱ 3` is two items that
need you, one unread notification and three unread friction; a zero count is left out. The Team
pane's header repeats the first two.

**Friction is unread until you've seen it.** In the TUI, friction counts as seen once you leave the
Inbox panel (or quit) after it was on screen there; friction further down, which you never
scrolled to, stays unread. `c` on one friction row marks it seen at once. `xt inbox` in your own
terminal marks the friction it printed as seen; an agent running `xt inbox` changes nothing. Seen
friction stays in the log (`xt log --type friction`) and under the folded row. It counts from the
supervisor's first run on 0.16.0, so friction from before the upgrade shows as seen.

**Rows** (from 0.16.0) use the whole width of their panel: a line is cut with `…` only when it
doesn't fit, and again when you resize the terminal. Each row in the Inbox and Work
panes ends with its age, dim at the right edge: `now` under 10 seconds, then `45s`, `14m`, `3h`,
`2d`, and whole weeks from 60 days (`8w`). A goal's age is that of its newest message (the goal, its
tasks and their replies), so a stuck goal looks old; a task's is that of the task itself. Agents in
the Team pane have no age, and Flow's rows and the supervisor's log (`v`) keep their clock time. The focused pane has a
green frame and a reversed title.

**Work** (panel 2, from 0.16.0; it replaces the Goals and Tasks panels) shows goals with their
tasks under them. From 0.17.0 it shares its pane with Flow: `2` shows Work, `3` Flow.

```
┌[2] - Work - 2 open · 63 done │ [3] - Flow────────────┐
│▾ #1729 Site check for #124         lead     1/2    14m│
│    ● #1733 pm    Read-only site check (curl -LfsS) 14m│
│    ✓ #1731 qa    Retry read-only curl for #124     15m│
│▾ #1702 Weekly digest               lead     0/1     2d│
│    ● #1705 carol Collect the week's links           2d│
│✎ quarterly-report  draft                              │
│▸ done (63)                                            │
│▾ no goal                                    0/1     1h│
│    ● #1740 carol A task with no goal                1h│
└───────────────────────────────────────────────────────┘
```

- **Open goals** come first, unfolded, the one with the newest activity on top. A goal row shows
  its id, first line, owner, how many of its tasks are done (`1/2`) and the age of its newest
  activity, so a goal nobody has touched for two days reads `2d`.
- A **task** shows `●` open, `✓` done or `✗` failed or blocked (closed with a `done` that starts
  with FAIL or BLOCKED, or open while its owner is blocked), then its id, owner, first line and age.
  A goal's tasks are newest first (from 0.17.0).
  A task belongs to the goal at the root of its `--ref` chain, so a task sent with `--ref` to
  another task or to a report still sits under its goal; one that reaches no goal (no `--ref`, or
  a chain that ends outside the last 30 days) sits under **no goal**, the last row.
- The liaison's **drafts** follow the open goals.
- **Done goals** are folded under `done (63)`; unfold it to see them newest first, each folded with
  its `n/n ✓`, and unfold any of them to see its tasks.
- `space` folds or unfolds the selected row (on a task: folds its goal). `o` shows open work only:
  it hides `done (N)` and the done tasks, and the panel's bottom edge says `open only`; `o` again
  shows them. Folds, `o` and the selected row stay
  as they are when the TUI refreshes. `enter` shows the selected goal or task in the detail pane
  with the goal's whole thread (below); a goal's brief follows at the end. `/` finds rows inside
  folds too.
- The title counts the goals: `2 open · 63 done`.

While a question waits for you, the work that depends on it isn't nudged. If you don't answer,
nothing breaks: the team waits, or follows a standing rule you gave it (see 5).

**When a goal is done** (from 0.15.0). A goal you dispatched (one the liaison opened) gets exactly
one desktop notification when it closes, "goal #210 done". Normally it's the liaison's report to
you about it (its first line is the text); the liaison sends it with `--ref` to the goal. If no such
report arrives within 5 minutes of the closure, the supervisor sends "goal #210 done" with the
first line of the lead's closing summary instead. That is the goal's only notification: the
liaison's progress reports about a goal that's still open, and anything it sends about the goal
afterwards, wait in the Inbox without one. Other reports the liaison sends you (not about a goal)
notify, once per `--ref`. Tasks, goals the lead opens for sub-teams, and friction never notify, and quiet
hours apply as for questions (what closes at night isn't sent later). The Inbox's Notifications group lists
closed goals, and from 0.16.0 the reports sent to you, until you've looked: in the TUI, until you
leave the Inbox panel (or quit) after it showed them; with `xt inbox`, once it has printed them in
your own terminal (an agent running `xt inbox` doesn't clear them). It counts from the supervisor's
first run on 0.15.0, so older goals don't appear. From 0.16.1 what you've seen isn't gone from the
TUI: it folds under Notifications as `(N earlier, seen)` for 7 days, also after you quit and start it again
(`xt inbox` still lists only what's new).

The **detail pane** (from 0.16.0) shows the selected item with its **thread**: for anything under
a goal (a goal, a task, a question or report about it), the whole goal in time order: the goal, its
tasks and every reply; for a message without a goal, the message and the replies to it. `enter` on
a row in any list shows it there.

```
#1733 task · lead → pm · opened 14m ago · open
Read-only site check (curl -LfsS) of the project site for #124

thread (6)
07:36  liaison → lead    goal     #1729 Site check for #124
07:36  lead    → qa      task     #1731 Retry read-only curl for #124
07:37  qa      → lead    done     #1735 BLOCKED: no network in sandbox
07:37  lead    → pm      task     #1733 Read-only site check (curl -LfsS)  ◀ you are here
07:38  pm      → lead    report   #1736 curl works from the supervisor's shell
07:38  lead    → liaison ask      #1737 How should #1729 finish?

usage (goal #1729): 212k tokens, est. $0.21
space: fold its goal · o: open work only · S: message the liaison
```

Each thread row shows the time (with the date when the thread spans days), sender → receiver, type,
id and first line; the selected message is marked `◀ you are here`. Below come the goal's usage and
the keys that work on the selected item. A thread too long for the pane shows the part around the
selected message and says how much is hidden (`↑ 24 earlier rows hidden`, `↓ 3 later rows
hidden`); after `enter`, `j`/`k` bring the hidden rows in. From 0.17.0 the detail pane is the short
band at the bottom (4 to 8 rows), so it scrolls: `j` first scrolls the thread into view, then
moves through its hidden rows. A message whose `--ref` points to one the TUI doesn't have shows
alone with its replies.

**Flow** (pane 3, from 0.16.0; it replaces the Log panel) shares its pane with Work (from 0.17.0:
`3` shows it, `2` shows Work again) and shows the messages as a swim-lane chart, the newest on top
(from 0.17.0; time runs upward):

```
┌[2] - Work │ [3] - Flow - 11 of 18 · system hidden (t)─────────────────────────────────────────────┐
│time  human       xt          liaison     lead        pm          qa          builder              │
│07:41 ◀···········report·✉                                        #1741 Site check done            │
│07:40                         ◀───────ask─⚑                       #1740 How should #1729 finish?   │
│07:39 ◀·····alert·⚠                                               #1739 qa is blocked              │
│07:38 ◀··approval·⚑                                               #1738 lead asks to spawn dora    │
│07:38                                     ◀─done──────◇           #1737 Site checked, all good     │
│07:37 ◀······································friction·✱           #1736 settings refuse plain curl │
│07:37                                     ▸─task──────▶           #1733 Read-only site check       │
│07:36                         ◆─goal──────▶                       #1729 Site check for #124        │
│07:36 ○─report────────────────▶                                   #1728 DNS fixed, ask QA to retry │
│── Sep 28 ──                                                                                       │
│18:02                                     ◀───────────report─✉    #1702 Weekly digest collected    │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- One **lane** per agent: you (`human`) first, then `xt` when it sent a message that's shown, then
  the liaison, the lead and the rest of the roster in order. An agent that has since retired (or
  one the roster doesn't know) gets a dim lane at the end, only while one of its messages is in
  view: scroll, filter or resize it out of the pane and its lane goes too.
- One **row** per message: the time on the left (local `HH:MM`; a `── Sep 28 ──` row over an
  earlier day's messages), an arrow from the sender's lane to the receiver's with the type's glyph and label at
  the sender end, and `#id` with the first line on the right, cut at the pane's edge. The glyphs:
  `◆` goal, `▸` task, `◇` done, `✉` report, `⚑` ask or approval, `✱` friction, `⚠` alert (amber),
  `○` a note or a message you typed. Messages to you are dotted (`·`), so they stand out; a note
  to itself is just its glyph and label. The glyph and label say the type, so it reads without
  colour. Flow rows show a time, not an age.
- **System lines** (xt's starts, stops and settings lines, wake-ups and nudges) are hidden; `t`
  shows or hides them (the title says which). Approval requests and alerts are always shown.
- `f` picks **one agent** (every message it sent or received) or **one goal** (the goal and every
  message whose `--ref` chain leads to it); the team's lanes stay, only rows are filtered, and the title
  names the filter. The same pick again, `esc` in the picker, or `esc` in Flow clears it. `/`
  filters by the message text.
- `j`/`k` or the arrows select a row, the page keys scroll, `g`/`G` (or `Home`/`End`) go to the
  newest (top) or oldest (bottom); a click selects a row and the wheel scrolls (from 0.16.1).
  While the newest row (the top one) is selected, Flow follows new messages; move down and it
  stays where you are. The title says
  `N of M`: rows in view of all that pass the filters. `enter` shows the message with its thread in
  the detail pane. Flow is read-only.
- A team too wide for the pane: the lanes that don't fit collapse into one `+N` lane, and a message
  to or from one of those agents starts its text with the agent's name. A narrow terminal (under
  60 columns): one line per message instead, `time sender → receiver glyph #id first line`; widen it
  and the chart comes back. Only the rows in view are drawn, so a long ledger scrolls without a
  stall. `xt log` is unchanged.

The **supervisor's log** (what xt did: deliveries, wake-ups, nudges, notifications) is a pop-up on
`v`, newest first; `j`/`k` scroll it and `esc` closes it. Its failures don't wait there: a failed
wake-up, a failed notification and a failed usage recording each raise an alert in the Inbox (Needs
you), with the first line of the error. While that alert is open, more failures of the same kind
count on it instead of adding rows (the row starts `⚠ ×3` and its age is the last failure's;
`xt inbox` says `×3, last 14:05`); once you clear it with `c`, the next failure
raises a new one. A failed notification raises only the alert, never another notification.

The **Team** pane, top left (from 0.16.0; it replaces the Status pane and the Team panel; one
column from 0.17.0):

```
┌─ [0] - Team ───────────────────────────────────┐
│my-team · xt 0.17.0 (latest) · 5 running        │
│1 goal open · ⚑ 1 needs you · ✉ 1 new           │
│today 3.6M tokens · est. $1.57                  │
│────────────────────────────────────────────────│
│CLAUDE  5h ▓░░░░░░░░░   6% resets 15:00         │
│        7d ▓░░░░░░░░░  10% resets Wed 12:00     │
│● pm      sonnet 5.5    idle      41k ▕▏  ▏   4%│
│● builder opus 5.5      idle      41k ▕▏  ▏   4%│
│● qa      default       idle        — ▕   ▏     │
│────────────────────────────────────────────────│
│CODEX  7d ▓▓▓▓▓▓░░░░  64% resets Tue 12:00      │
│● liaison default       idle        — ▕   ▏     │
│● lead    gpt-5.2-codex working ~181k ▕██▏▏  70%│
└────────────────────────────────────────────────┘
```

(100 columns: pm, builder and qa on Claude; liaison and lead on Codex, where lead's `default` is
shown as the model its session log names.)

- The **header**: the team; xt's version, with `(latest)`, a newer published release in yellow, or
  `running 0.15.0: restart to update` when something still runs an older one; how many agents run;
  open goals; `⚑ N needs you` and `✉ N new` (the Inbox's counts), or "nothing waiting for you";
  messages or jobs stuck for over a minute. It wraps between its parts rather than cut them off.
  Under it, today's tokens and estimate, then a line.
- One **block per harness**, a line between them: its account windows as bars with the share used
  and the reset time (`CLAUDE 5h …`, `CODEX 7d …`); a window without a current reading isn't shown,
  and a dim `?` after the harness's name says so (select the line to read why). Then its agents,
  one per line, in columns that line up: a dot in the
  state's colour (working yellow, idle and done green, blocked red, dim when not running: your
  terminal's own named colours, so your theme decides the shades), the name, the
  short model (`sonnet 5.5`; for an agent on `default`, the model its own session log names, else
  `default`), the state (`stopped` when not running), and the context: tokens, a bar and the share
  of the model's window, yellow from 70 % and red from 85 %.
- The pane **never scrolls**. When the team doesn't fit its height, it shows what fits and a last
  line `+3 more (widen the terminal)`, counting the agents and harness lines out of view; `j`/`k`
  reach the agents in view. A team that large is better read with `xt status`.
- The **header and harness lines can be selected** too (from 0.17.0), ahead of the agents.
  The header's detail, *xt and the team*, shows the published version with when it was checked
  (or why the check failed), the installed and running versions (the supervisor and each agent),
  the notes `xt status` prints (restart needed, upgrade available) and today's usage split by
  agent. A harness line's detail shows each account window: the share used, the reset time, how
  old the reading is and where it comes from (Claude: the statusLine snapshot; Codex: its session
  logs), or, for a window with no current reading, why and what brings one back (no Claude agent
  has the statusLine configured, the window reset with no turn since, the last reading is 3 h 10 m
  old); then the harness's agents with their model and today's tokens.

**The layout** (from 0.17.0) has three bands and the key line:

```
┌─ [0] - Team ─────────────┐┌─ [1] - Inbox - ⚑ 2 · ✉ 1 ──────────────────┐
│ header, today, harnesses ││ NEEDS YOU / NOTIFICATIONS / FRICTION       │
│ and agents, one column   ││                                            │
└──────────────────────────┘└────────────────────────────────────────────┘
┌─ [2] - Work - 1 open · 0 done │ [3] - Flow ──────────────────────────────┐
│ Work, or Flow after 3                                                    │
└──────────────────────────────────────────────────────────────────────────┘
┌─ [4] - Detail - Inbox ───────────────────────────────────────────────────┐
│ the selected row and its thread (4 to 8 rows; it scrolls)                │
└──────────────────────────────────────────────────────────────────────────┘
 a/d approve/deny · c clear · space fold · S message liaison · / filter · v supervisor
```

- **Top**: Team on the left, as wide as its agent lines need up to half the terminal, and the
  Inbox on the right, the same height. The team decides that height (up to 60 % of the
  terminal), so Work/Flow and Detail keep at least 4 rows each where the terminal allows.
- **Middle**: Work or Flow, full width, the rest of the height. Both names show in the title like
  tabs, the one on screen with its counts, the other dim. `2` and `3` switch, and each keeps its
  selection and scroll while the other is shown.
- **Bottom**: the detail pane, full width and shorter than the others.
- Every title reads `[n] - Title - info`: `n` is the pane's key, `info` its counts or filter.
- **Newest on top** in every pane (from 0.17.0): Needs you, Notifications, Friction, Work's goals
  and tasks, and Flow. With the top row selected, the selection stays on the top row as new rows
  arrive; select another row and it stays there.

The panes' number keys (from 0.16.1) are `0` Team, `1` Inbox, `2` Work, `3` Flow and `4` the
detail pane, and `v` opens the supervisor's log; the TUI starts in the Inbox, and `tab` goes round
the panes. `esc` in the detail pane goes back to the pane you came from. In the Team pane `j`/`k`
or the arrows select the header, a harness line or an agent (`Home`/`End` or `PgUp`/`PgDn`: the
first and last row in view), the detail pane shows it, and on an agent `u`, `x`, `R` and `f` act
on it (`f` in Flow is its filter).

**The key line** (from 0.17.0) shows the focused pane's own keys first, then `S`, `/` and `v`,
which work everywhere; a narrow terminal keeps the keys and drops their words. Inbox: `a/d`,
`s answer #N` (only while a question is selected: otherwise `s`, like `S`, messages the liaison),
`c`, `space`. Team: `u/U`, `x/X`, `R`, `f`. Work: `space`, `o`. Flow: `t`, `f`, `g/G`. The detail
pane: only the keys that work everywhere. Keys for moving around (`0`-`4`, `j/k`, `tab`, `enter`,
`esc`), `h` and `q` are left to the help screen (`h`), which lists every key.

**The mouse** (from 0.16.1): a click selects a row in any pane (an agent in Team, a row in the
Inbox, Work or Flow) and focuses that pane; the detail pane shows it but doesn't take focus, so the
arrows keep moving in the pane you clicked. `enter` or `4` goes to the detail pane. The wheel
scrolls Flow (the selection stays in view) and the detail pane (a long thread's hidden rows first),
wherever focus is. The result of your last action
(`alert cleared`, `starting carol…`) shows for about ten seconds in a one-line toast at the bottom,
then goes away on its own.

An agent's detail (select it in the Team pane) ends with the last lines of its screen, laid out like the
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

**The board watch** (from 0.19.0). When you move a card into a Board column that means "go" (Ready
to build, say), the team can learn it without a message from you. xt knows no board tool: you name
a command in `team.toml` that lists the cards in that column, and the supervisor runs it on a
schedule.

```toml
[board_watch]
command = ["fizzy", "card", "list", "--board", "BOARD_ID", "--column", "COLUMN_ID", "--all", "--jq", "[.data[] | {number, title}]"]
interval = "5m"             # how often; default 5m
timeout = "30s"             # a run taking longer is a failure; default 30s
column = "Ready to build"   # optional: the column's name, used in the message
```

- **The command's output (the contract).** Exit code 0 and, on standard output, one JSON array of
  the cards now in the column, each an object with a `number` (integer or string) and an optional
  `title`: `[{"number": 129, "title": "Work outline"}]`. An empty array is fine. Anything else is a
  failure, and so is output over 64 KB.
- **What the lead gets.** The supervisor keeps the set of numbers from its last successful run.
  A number that wasn't there before reaches the lead as one system message: `Card 129 (Work
  outline) is now in Ready to build (seen by the board watch)`. xt doesn't say who moved it (the
  output doesn't tell). A card that leaves the column causes nothing. The first successful run
  after the supervisor starts only records the set, so a restart replays nothing.
- **Failures.** A non-zero exit, a timeout, output that isn't the array above, or a command that
  can't be started raises one Inbox alert (`boardwatch`) naming the cause (`exit code 3`, `timed
  out after 30s`, `unreadable output`) and the first line of the command's error output, or, when
  that's empty, the first lines of its standard output (Fizzy prints its errors there). Later
  failures don't repeat it; the next success clears it. During an outage the supervisor keeps the
  old set, so a card that entered meanwhile is reported after it.
- **Where it runs.** As your user, outside every agent's sandbox, from the team repo, with no input
  and the supervisor's environment (the shell of the Herdr pane it runs in). It's run directly,
  never through a shell, so `;`, `$(…)` and quotes in the list are plain text. xt passes it nothing
  else and gives agents neither the command nor its credentials; only you edit `team.toml`. A
  Fizzy command reads its token from your keyring: run it once in a pane of the team's Herdr
  session to check that it can.
- **Check the command by hand first.** A command that runs but lists the wrong thing is a success
  to xt: Fizzy given a wrong column id prints `[]` with exit code 0, and the watch then reports
  `0 card(s)` without an alert and never tells the lead anything. Before you rely on it, run the
  exact command once in your terminal and check that it lists the cards you expect in that column,
  then compare the count in `xt status`.
- `xt status` shows `board watch: last success Wed 10:05 (3 card(s) in the column)`, or `board
  watch: FAILING since …` with the cause. One watched column per team. Without the section nothing
  runs. See [examples](examples.md#8-tell-the-lead-when-a-card-is-ready-to-build).

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
| **published** | the newest final release (candidates don't count) | the supervisor checks the upstream's tags when it starts and then every 6 hours, and `xt version use`, `xt version rollback` and `xt version check` check them too (from 0.17.0); if the check fails you see the last known one and why. It is never shown older than the installed final release: then you see `published ≥ installed, check pending` and the supervisor tries again every 15 minutes |
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
| ... as soon as it's free | `xt reset <name> --when-idle` (`--cancel` removes it) |
| Give one agent a fresh session right now | `xt restart <name>` |

Stopping keeps an agent in the roster, its notes and its open work; nothing alerts about an agent
you stopped. A schedule's rhythm survives restarts.

**Resetting a heavy agent.** An agent's context grows with every turn, and a big context costs
more per turn and carries stale detail. `xt reset <name>` gives it a fresh one without losing its
work: it is refused while the agent owns an open goal or task (it names them) or is busy; otherwise
xt asks the agent to save what it needs into `members/<name>/notes.md` and confirm with `xt
checkpoint`, waits up to 5 minutes (`--timeout`), and only then starts a fresh session, whose brief
points to the notes and the checkpoint line. No checkpoint, or new work arriving meanwhile, means
nothing is reset. `xt restart <name>` is the emergency route, without a checkpoint. When an agent's
context reaches 70% of its window, `xt status`, the agent's detail in the TUI and the lead's and
liaison's briefs show `reset suggested for …`, and only when the reading is known, has a window and
was observed within the last 2 hours (not in the future, beyond a few minutes of clock difference).

**Queueing a reset for when the agent is free.** A busy agent, or one that owns open work, refuses a
plain reset. `xt reset <name> --when-idle` queues it instead and returns at once: the supervisor
asks the agent for the same checkpoint the next time it is idle, owns no open goal or task and has
no messages waiting, then starts the fresh session. While it waits, `xt status` and the agent's
detail in the TUI show `reset queued (by human at 09:12): waits until it's idle with no open work`
(then `asked for a checkpoint at …`). After the checkpoint xt checks again and replaces the session
only once the agent is idle; an open item, a message waiting for it, or one delivered since it was
asked keeps the reset queued (a fresh checkpoint is asked for later). No checkpoint, or still busy,
5 minutes after asking drops it (the session is untouched, as with a plain reset). The queue
survives a restart of the supervisor; one reset per agent can be queued (queueing again shows the
one there is). `xt reset <name> --cancel` removes it; stopping or retiring the agent drops it too.
Each step is a line in the message log.

**Resetting automatically (off by default).** With the policy on, the supervisor queues such a reset
by itself, through the same path, for an agent whose context is above a size in tokens:

```toml
[policy]
auto_reset = true                 # off (false) by default: nothing resets on its own
auto_reset_tokens = 150000        # the threshold in tokens, whatever the agent's window
auto_reset_cooldown_hours = 6     # at most one reset per agent in this many hours

[[agent]]
name = "builder"
# ...
auto_reset_tokens = 250000        # this agent's own threshold; "off" exempts it
```

An agent is reset only when all of these hold: it is idle, owns no open goal or task, its context
reading is known, recent (observed within the last 2 hours, as for the suggestion) and above its
threshold, and no reset ran for it within the cool-down. A busy agent, one with open work, a stale
or unknown reading, or one inside the cool-down is left alone. The threshold is an absolute token
count, not a share of the window: 150,000 tokens is 15% of a 1M window and 58% of a 258k one. The
ledger says why (`context 160000 tokens, above the threshold of 150000 tokens; policy auto_reset`),
and `xt status` shows `reset queued (by xt's reset policy …)` while it waits. A cancelled or
abandoned automatic reset also waits for the cool-down. **The trade-off:** a fresh context costs one
turn re-reading the first prompt, the brief and the agent's notes, and anything not in the notes is
gone; keep the threshold well above what an agent needs for one piece of work, and exempt an agent
in the middle of long, delicate work (`auto_reset_tokens = "off"`). A complete example is in
[Examples](examples.md#6-reset-heavy-agents-automatically).

### 9. When something goes wrong

xt alerts, it never repairs. Alerts appear in the Inbox (red `⚠`) and as notifications:

| Alert | Means | Usually |
|---|---|---|
| `blocked:<name>` | The agent is stuck on something in its pane, usually its harness asking for permission | `f` to its workspace, answer it; clears by itself |
| `missing:<name>` | An agent xt started isn't running any more (crashed, or its workspace was closed outside xt) | Find out why (its pane, `xt log --member <name>`), then `u` / `xt spawn <name>` |
| `missing:lead` with goals open | The lead isn't running though there's work | `xt up` |
| `noprompt:<name>` | An agent started but its first prompt never showed up on its screen, so it doesn't know who it is | Stop and start it again (`xt restart <name>`) |
| `partprompt:<name>` | (from 0.19.0, pi) The agent's first prompt reached it without its opening, and so did xt's one resend of it. It has its identity and protocol, but xt can't link its session log, so its context and today's usage stay empty | Stop and start it again (`xt restart <name>`); clears at its next start |
| `silent:<id>` | The owner of an open item ignored two nudges | Look at its pane; ask the liaison or restart the agent |
| `volume:<date>` | Today's message log is unusually big: probably two agents in a loop | `xt log` to see who; stop them |
| `launch:<name>` | The agent runs without xt's launch settings: something other than xt started it, typically the terminal multiplexer restoring its session after a reboot or power cycle and resuming the agent's old conversation | `xt restart <name>`, or `xt restart --all` for the whole team; clears by itself |

`c` (or `xt clear <key>`) dismisses an alert once dealt with. `xt status` also says whenever the
supervisor isn't running (then nothing is delivered, no alert is raised and nobody is woken: `xt up`).

**An agent running without xt's launch settings.** xt starts every agent with its identity
(`XT_AGENT`), its model, its settings file and its connector and browser-tool blocks. A process
resumed some other way has none of them, so it may run the wrong model without the permissions and
limits the team relies on. The supervisor (about once a minute), `xt status` and `xt up` look at
the harness processes working in the team repo. An agent with one carrying `XT_AGENT=<name>` is
fine. A warning needs evidence: harness processes of the agent's kind (claude, codex or pi) without
`XT_AGENT`, at least as many as the running agents of that kind left without a match. Then they
say `<name> is running without xt's launch settings (restored by the multiplexer?) … Run xt restart
<name> (or --all)`, raise one `launch:<name>` alert under Needs you,
and mark the agent with a red `!` in place of its dot in the TUI's Team pane. The alert clears when
xt starts the agent again. When xt can't look properly, `xt status` shows `launch settings: not
checked (…)` for the agent and raises or clears nothing; it never counts as a match. That happens
when a harness process's environment can't be read (another user's), when the agent's process isn't
visible (from a sandbox, which may show only its own agent's process), when there are fewer such
processes than agents left without a match (xt can't tell which is whose), and from a sandboxed
shell (its own PID namespace, or a `/proc` whose PID 1 isn't the system's init, as in Codex's
sandbox). Only the harness programs themselves count, never helpers such as `codex-linux-sandbox`.
From such
a shell `xt status` also says `the supervisor: not checked` rather than "isn't running", unless
the supervisor saved Herdr's agent list in the last 30 seconds (then it's running). Run `xt status`
in your own terminal for the real answer.

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

**Options for a Codex agent** (from 0.19.0). Every Codex agent runs in Codex's sandbox:
workspace-write, no network. One agent can get network with a line in its `team.toml` entry:

```toml
[[agent]]
name = "qa"
harness = "codex"
codex_options = ["sandbox_workspace_write.network_access=true"]
```

xt passes each option as `-c key=value` when it starts the agent (`xt restart <name>` applies a
changed line). Rules:
- Only xt's allowlist is accepted, and in this release that's the network switch alone:
  `sandbox_workspace_write.network_access`, `true` or `false`. Any other key or value refuses the
  start with the allowed list, because Codex may silently take a key it doesn't know. The list is
  part of xt, not something a team extends.
- Codex only: the line on a Claude Code or pi agent refuses its start. `xt harnesses` says which
  harness takes it.
- Codex has no per-host limit: with network on, the agent can reach **any host**. Give it to an
  agent that works in a clean clone holding no credentials (the intended user is the quality
  analyst). That's a team rule: xt doesn't check it.
- The start note, `xt status`, the brief and the agent's detail show the options, and say
  `(running with …; xt restart <name> applies it)` when `team.toml` changed after the agent started.
- An agent without the line runs as before.

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

and the TUI's Team pane shows each window as a bar in the Claude block (from 0.16.0; a window
without a current reading isn't drawn). The plan is shared with you
and anyone else on the account, so the numbers include your own use; they are not one agent's
share.

- **Which team.** The script writes under `XT_ROOT` when that's set, otherwise under the xt checkout
  it's in (`bin/..`), and only into an existing `.xt/state` directory. Point `command` at your team
  repo's own `bin/xt-statusline`. It's one of xt's own files, which agents never edit.
- **When there's no number.** A session's first status call (before any reply) carries no limits;
  the last reading stays and status shows its age. A window whose reset time has passed shows
  `5h window reset, no reading since` rather than the old percentage. A reading older than 3 hours,
  one timestamped later than now (the script and xt run on the same machine, so there's no
  tolerance), a value out of range (a percentage outside 0–100, a time outside 2000–2100) or a
  missing or unreadable file shows `unknown`; the rest of status is unaffected. Status shows the
  Claude line when the team has a Claude agent or a reading exists.
- **Never in the way.** The file is replaced in one step (never half-written), and bad input from
  Claude Code only prints `xt` as the status line.
- Seen on Claude Code 2.1.284; another version that changes the fields shows `unknown`.

**How full is an agent's context?** The Team pane shows it per agent (`~211k ▕████▎ ▏ 82%`:
tokens in the conversation after its latest turn, a bar and the share of the model's window),
yellow from 70% and red from 85%; the agent's detail (`~211k/258k`), `xt status` and the lead's and
liaison's briefs show it too. xt reads it
from the harness's own session log (only the counters, never the conversation) and links each
agent to its log by its first prompt, so a restarted agent starts again from its new session. A
`~` means approximate (Codex reports the latest turn's usage, not a live figure); tokens with no
bar and no share mean the window isn't known for that model (`?` in the detail); `—` means nothing
is recorded yet, or the agent isn't running
(its detail then shows the last session's figure, labelled as such). When a running agent has no
session log xt can link, `xt status` says so under its row (`no session log found for <name>: its
context and today's usage can't be read`; from 0.19.0). pi has lost the first few characters of a
first prompt on some first starts, which hid its log from xt. So for pi (from 0.19.0) xt waits until
its screen has stopped changing, and types one guard line before the prompt: `(xt: this line only
guards your first prompt against lost characters; ignore it. The prompt follows.)`. A lost start
eats that line, not the prompt. xt then checks pi's session log for the prompt's opening. If it's
still missing, the start record says so, and the supervisor resends the whole prompt once the agent
is idle, behind a note that it replaces the damaged one (a second reading of the prompt: about 25k
tokens for a lead, only when this happens). If the resend arrives damaged too, `partprompt:<name>`
is raised. Claude Code and Codex agents get no guard line. Supported: Codex, Claude
Code, pi. The window comes from where it's reliable: Codex writes the usable window of the session
into its log (258,400 tokens for the current models, well below an API model's published maximum,
such as gpt-6-astra's 1.05M); Claude Code doesn't, so xt uses the table in
`harnesses/claude.toml` (1M for the current models, 200k for Haiku 4.5). A Codex log without a
window leaves it unknown rather than borrowing an API figure.

**What does the team cost?** The supervisor records every model call from the agents' session
logs (once a minute; counters only) and attributes it to the goal the agent was working on. You
see tokens and an estimate in dollars: today's team total in the Team pane's header and `xt status`,
each agent's day in its detail, each goal's total in its detail, and the team's day in the lead's
and liaison's briefs. The estimate uses public list prices from `prices.toml` (or pi's own cost)
and is always labelled "est.": on a subscription you don't pay per token, and nothing here is a
bill. Tokens of a model with no listed price are shown as unpriced, never as zero; calls made on
an agent's behalf (Codex's automatic reviewer, Claude subagents) are counted and shown as
auxiliary. Where a harness reports your account's allowance (Codex: percent of its window and
when it resets), the Team pane (as bars in that harness's block) and `xt status` show it once per
harness. `prices.toml` lists
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

### 13. An operator acting for you

(From 0.19.0.) Sometimes another process works for you outside the team: today, typically your own
coding-agent session helping with a staging check. It is not you, so `--as human` stays refused
for it, as for every process but your own terminal. Instead you register it as a named
**operator**, per team and per operator session:

1. In the operator's session, it runs `xt operator pid`. That prints its harness process, e.g.
   `48213 (claude): give the human this pid …`.
2. In **your own terminal**: `xt operator add helper --pid 48213`. xt checks that this is a harness
   process (claude, codex or pi) and not one of the team's agents, records its start time, and
   writes a secret token to `.xt/operators/helper.token`, readable by your user only.
3. The operator runs xt with that token in `XT_OPERATOR_TOKEN` and `--as helper`, from commands
   its registered process started. **Both** are needed: the token alone could be read by an agent
   under your account, and the process alone could be any command it runs. Either alone is refused,
   and so is any other process using `--as helper`.
4. When the operator's session ends, its process is gone and the registration no longer matches:
   register the next session again (`xt operator add` replaces it). `xt operator list` shows who is
   registered; `xt operator remove helper` removes one.

**What an operator may do on its own.** Send a report to the liaison: `xt send liaison --as helper
--type report <<'XT_END' … XT_END`. It's recorded under the operator's own name and in its own
Flow lane (`helper → liaison`), ends with `(sent by helper, an operator, on the human's behalf)`,
and shows in your Inbox's Notifications. It sends to the liaison only and reports only: it never
answers questions, approves anything or opens work.

**Delegation.** For a while, you can let it run some of your commands:

```sh
xt delegate helper --for 45m                 # restart, reset, spawn and up; at most 60m, 30m by default
xt delegate helper --only restart,reset      # fewer commands
xt delegate --revoke                         # end it now (or: xt delegate helper --revoke)
```

Until the grant ends, the operator may run `xt restart <name>…`, `xt reset <name>` (and
`--when-idle`, `--cancel`), `xt spawn <name>` for an agent already in `team.toml`, as it is (no
`--harness`, `--model`, `--role`, `--reports-to` or `--permissions`), and `xt up`, each with `--as
helper`. Each is recorded once it has run, as `helper, delegated by human until 14:45: xt restart
lead`; one that fails (say, `spawn` of an agent that is already running) is recorded with `(failed:
…)` and the reason. A grant over
60 minutes is refused; grant again when it ends. It expires by itself: xt compares the end time at
each command, so there's nothing to clean up. `xt status` (`delegation: delegated to helper until
14:45: …`) and the TUI's Team header show an active grant.

**Never delegated:** `xt down` and `xt restart --all` (only you stop the team), answers, approvals,
`xt version use`/`rollback`, registering operators and granting delegation. Without a grant, after
it expires or after a revoke, the operator's commands are refused as before.

Limits: the process check needs to see the operator's process tree. A command run inside Codex's
sandbox (its own PID namespace) can't be matched, so use an operator whose commands run in your
normal process tree (e.g. Claude Code without a sandbox). Operators are per team; there's one grant
per operator at a time.

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
| [`xt version`](#xt-version) | show, check: both; use/rollback: human | none |
| [`xt status`](#xt-status) | both | Team pane (on top) |
| [`xt inbox`](#xt-inbox) | human | Inbox panel (`1`) |
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
| [`xt goal`](#xt-goal) | agents (liaison) | Work panel (`2`) shows drafts and goals |
| [`xt brief`](#xt-brief) | both | Team detail (partly) |
| [`xt log`](#xt-log) | both | Flow pane (`3`), the thread in the detail pane, and the supervisor's log (`v`) |
| [`xt harnesses`](#xt-harnesses) | human | none |
| [`xt operator`](#xt-operator) | add/remove: human; pid: the operator; list: both | none |
| [`xt delegate`](#xt-delegate) | human | Team header shows an active grant |
| [`xt watch`](#xt-watch) | (xt) | `v` shows its events |
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

`xt reset <name> --when-idle` queues the same reset and returns at once; the supervisor runs it the
next time the agent is idle with no open work (see 8). `xt reset <name> --cancel` removes a queued
reset. Both human only.

### `xt restart`

`xt restart <name>…` | `xt restart --all` — stops and starts agents so they get fresh
instructions; `--all` does the whole team and the supervisor, and brings back every agent that was
running (right after an `xt down`: the agents that were running before it). **Use it** after updating xt (`git pull upstream main`), after changing a role, or to give
a confused or heavy agent a clean session.

### `xt operator`

`xt operator add NAME --pid PID` | `xt operator remove NAME` | `xt operator list` | `xt operator
pid` — registers an outside process acting for you (from 0.19.0; see 13). `add` and `remove` are
yours, in your own terminal. `add` takes the operator's harness process, which the operator's own
`xt operator pid` prints, and writes the token to `.xt/operators/NAME.token`. Run it again after
each operator session. `list` shows the registrations and any active grant.

### `xt delegate`

`xt delegate NAME [--for 30m] [--only restart,reset,spawn,up]` | `xt delegate [NAME] --revoke` —
lets a registered operator run `restart`, `reset`, `spawn` of an existing agent and `up` for at
most 60 minutes (default 30), recorded in the log; `--revoke` ends it early. Human only. `down`,
answers, approvals, version switches, registering and granting are never delegated. See 13.

### `xt version`

`xt version` | `xt version check` | `xt version use <tag> [--candidate]` | `xt version rollback` —
shows the team's versions, state format and recent switches; `check` asks the upstream for the
newest release now and prints the result (from 0.17.0; it needs network access, and any member
may run it); `use` merges an upstream release tag into the team repo
(team down, tracked files committed, state format supported, verified snapshot first); `rollback`
reverts the last switch. **Use it** to upgrade to a chosen release, or to go back one. See
[Updating xt](#7-updating-xt).

### `xt status`

`xt status` — one screen: the published, installed and running xt versions (see 7); every agent with its role, `harness/model`, live state, open work and
context (e.g. `~211k/258k`) and today's usage; today's team total and, where reported, the
account allowance (Codex from its logs; Claude's five-hour and weekly windows through the status
line, see **Claude plan usage in status**);
counts of open goals and tasks, questions for you, queued messages, jobs, approvals and alerts; the
board watch (from 0.19.0, see 5) and an active delegation to an operator (see 13); a
warning if the supervisor isn't running. **Use it** for a quick look without the TUI (e.g. over
ssh), or in scripts.

### `xt inbox`

`xt inbox [--days N] [--limit N] [--seen]` — the Inbox's three groups, as in the TUI (see 4), each
row with the command to act on it: **Needs you** (questions, approvals, alerts `⚠`), **New since you
last looked** (goals done and reports to you) and **Friction** (unread only, then `(12 older, seen;
…)`). A group with nothing in it is left out; with nothing at all it prints `Nothing for you.`
In your own terminal it clears New and marks the friction it printed as seen; run by an agent it
changes nothing. `--limit` caps each group (default 20; what it leaves out, such as older unread
friction, stays unread), `--seen` also lists the friction you've seen, `--days` is how far back it
looks (default 30, as the TUI).
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
harness; a running one is refused (`xt restart <name>` restarts it). For a new one, `--harness` and `--role` are needed and `roles/<role>.md` must exist. The
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
Work panel shows drafts and goals.

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
that refers to it directly) or an agent (`--member carol`); the TUI's Flow pane (`3`) and the
supervisor's pop-up (`v`) show the recent part.

### `xt harnesses`

`xt harnesses` — which harnesses are installed here, how their model is chosen, and their known
limits. **Use it** before choosing a harness for the liaison, lead or a new agent.

### `xt watch`

`xt watch` — the supervisor loop. `xt up` starts it in its own workspace; you don't run it by hand.
Its events show in the TUI's supervisor pop-up (`v`) and `xt log --watch`; a failed wake-up,
notification or usage recording also raises an Inbox alert.

### `xt tui`

`xt tui [--demo]` — the TUI without the `xt up` step; `--demo` shows it with sample data (no team
needed). Keys: `h` lists them all; the [README](../README.md#the-tui) has the table.
