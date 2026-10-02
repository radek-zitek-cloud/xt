# Changelog

All notable changes to xt. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and xt uses [semantic versioning](https://semver.org/) as described in the README's
[Versioning](README.md#versioning) section.

Every release has an **Upgrading** note: what a team that already runs xt has to do after
`git pull upstream main` (or after merging the release tag).

## [Unreleased]

## [0.21.0] — not released yet

First release of Direction B (a power user without an AI operator). **0.21.0-rc1** has #182 and
#183. The ledger gains optional fields (`question` on an ask, `answer` on a reply); older ledgers
read unchanged and older xt versions ignore the fields.

### Added

- **One structured message format (#182).** A message to the human is a narrative that may end in
  one question with a declared answer type: **closed** (`xt send … --type ask --closed`: yes or
  no), **options** (two to four `--option "<option> :: <consequence>"`, one `--recommend <n>`, and
  `--other` when the human may also answer in their own words) or **open** (an ask with neither).
  The type, the options, the recommendation and the human's answer are stored as data in the ledger
  entry, and `xt log` shows them in a line under the text (`[question: options 1-4, recommended 2,
  Other allowed]`, `[answer: option 2]`). `xt answer`, and `s` in the TUI, check the answer against
  the type: `yes`/`no` for closed (stored as `yes` or `no`); an option's number for options (stored
  as the option's full text, as since 0.14.0), and own words only with Other; any text for open.
  xt refuses a malformed question (fewer than two or more than four options, an empty option or one
  without a consequence, no or several recommendations, `--other` or options on a closed question),
  sends nothing and prints the message text back. In the TUI, `s` on a closed question takes `y` or
  `n`; on an options question the answer dialog shows every option in full, wrapped, also at 80
  columns, and `1` to `4` fill one in; the Inbox row and `xt inbox` say `yes/no`, `3 options` or
  `4 options, Other`. Asks written before 0.21.0 still read and answer as they did: 0.14.0's options
  take a number or own words, any other ask is an open question.

### Changed

- **Decision questions take up to four options, and own words need `--other` (#182).** 0.14.0 took
  two or three and always allowed own words (`Or answer in your own words.`); a new question ends
  with `Other: answer in your own words.` or `Answer with the option's number.`. The protocol's
  `ask`, the liaison's and the lead's guidance, `docs/examples.md` §5 and the user guide describe
  the format.

### Upgrading

- Pull the release and `xt restart --all` (or restart the liaison and lead), so they read the new
  guidance. Nothing to migrate.

## [0.20.0] — 2026-10-02

The release: the same code and docs as 0.20.0-rc3 (only the version, this changelog and the site's
badge and Flow line changed). Polish from a fresh-eyes usability review of 0.19.0: seven small
cards to their approved spec, no new feature. **0.20.0-rc1** has #174, #177 and #178; **0.20.0-rc2** adds #176, #179 and #180; **0.20.0-rc3** adds #175. No protocol or ledger format change; new state
file `.xt/state/context_alerts.json`, and `.xt/state/versions.json` may carry `starting`.

### Fixed

- **A pi agent's context is readable, or xt says why not (#174).** A hired pi member's context
  stayed `—` for its whole life with only "no session log found", while its usage was recorded
  later. A session log whose first prompt lost its opening now still counts as the agent's, by two
  later parts of the prompt (the team repo's path and `Always pass --as <name>`), for both the
  context and the usage. When the context still can't be read, `xt status` says under the agent's
  row which of context and today's usage xt can read (`<name>: today's usage recorded; context
  can't be read (…)` or `<name>: nothing can be read: no context and no usage recorded today
  (…)`), and the reason, also in the TUI's agent detail, names what xt found: no session logs where
  the harness keeps them (or none it may read), none written since the agent started, or some
  written since but none with its first prompt. In an agent's first 10 minutes a found log without
  usage yet is expected and says nothing. After them, the supervisor raises one `context:<name>`
  alert per start, cleared when the context becomes readable or the agent stops. The `partprompt`
  alert no longer says xt can't find the log. The user guide says when an unreadable context is
  expected. The cause seen in the review was not reproduced on staging; status now names the cause
  class.

### Changed

- **Plainer wording (#177).** The demo TUI's Inbox shows the real TUI's group labels (`NEEDS YOU`,
  `NOTIFICATIONS`, `FRICTION`; it said `NEW`), from one shared list. An agent whose start is under
  way, as in its own first brief, shows `not recorded yet (first turn running)` instead of `unknown
  (started before xt recorded versions)`, which stays for processes that really predate version
  recording (xt marks the start in `.xt/state/versions.json` before the first prompt). `xt log --id`
  of a message that doesn't exist says `no such message: #ID` and exits with an error; an existing
  message filtered away still prints `(no messages)`. `xt tui --help` describes `--demo` as made-up
  example data rather than a "look-and-feel spike". `xt approve` of a missing id says `no pending
  approval #ID` with the id once.
- **`xt log --events`, and `xt init` without a terminal (#178).** `xt log --events` prints the
  supervisor's newest events once, as `--watch` did; `--watch` stays as its alias, and the help and
  user guide say it doesn't follow. `xt init` without a terminal (a script or a pipe) still uses the
  defaults for every question not given as an option, and now says so in one line naming `--yes`
  and `xt init --help`; the written `team.toml` and the exit code are unchanged.
- **TUI help, detail cue and Flow key names (#176).** The Keys pop-up (`h`) is never wider than the
  terminal: at 80 columns and less it takes the whole width, every entry wraps under itself, and
  its `j/k scroll · esc close` hint stays visible; it scrolls with `j`/`k` and the page keys (it is
  taller than the screen at every size checked, 120x40 included, and its last lines were cut off
  before). When the detail pane's text is longer than the pane, its bottom edge says `▾ N more
  (j/k)` (at the end, `▴ N above (k)`), and the key line in the detail pane starts with `j/k
  scroll`. Flow's `f` is called focus (key line `f focus`, the picker `Focus Flow on`, `Flow: focus
  cleared`) and `/` filter, in the key lines, the help and the user guide. Checked with Textual's
  headless Pilot at 120x40, 100x30, 80x24 and 60x20.
- **`xt inbox --seen` shows what the TUI folds (#179).** It lists, under the TUI's own labels and
  in its order, the questions you answered in the last 7 days (`(N answered, last 7 days)` under
  Needs you, each `✓ #id question → your answer`), the notifications you've seen in the last 7
  days (`(N earlier, seen)` under New) and the friction you've seen (`(N older, seen)`, as before);
  the labels come from one place for both. Plain `xt inbox` is unchanged. The user guide says when
  a notification counts as seen (when you leave the Inbox or quit the TUI, or when `xt inbox`
  prints it in your terminal) and that two open TUIs differ only while one still has its Inbox
  focused.
- **pi agents are reminded of "no friction, no line" (#180).** A pi agent's first prompt (and a
  resent one) carries one line just before its last, reminding it never to write "no issues"
  (`first_prompt_note` in `harnesses/pi.toml`, a new adapter key); the guard line and the opening
  that xt checks stay where they were. Claude Code and Codex prompts are unchanged. The user guide
  says which harnesses were seen to comply. A "no issues" line isn't flagged in the ledger: the
  evidence is one run.

### Documentation

- **README highlights and a quick start on the site (#175).** The README's 23 "Added since"
  entries (0.11.0 to 0.19.0), which sat between the pitch and the Quick start, are replaced by five
  highlights and a link to this changelog, where every one of them is; a "Want to try it?" link at
  the top goes to the Quick start. The site shows the README's Quick start command (`curl -fsSLO
  …/xt-clone.sh`, then `sh xt-clone.sh my-team`) under its first screen, with what it does and
  what it needs, and both "Get started" buttons go there instead of to GitHub.

### Upgrading

- From 0.19.0: `git pull upstream main` (or `xt version use v0.20.0`), then `xt restart --all` so
  the supervisor runs the context check. Scripts using `xt log --watch` keep working. From
  0.20.0-rc3: nothing but the version changes.

## [0.19.0] — 2026-10-01

The release: the same code and docs as 0.19.0-rc6 (only the version and this changelog changed).
Working with the team from outside it: five cards to their approved specs. #135 tells the lead when
a card enters a Board column; #166 adds a named operator sender and time-bound delegation; #169
gives one Codex agent network; #167 makes pi's first prompt arrive whole; #156 brings the README,
architecture, examples and site up to date. **0.19.0-rc1** has #167, #169 and #135;
**0.19.0-rc2** adds #166; **0.19.0-rc3** adds #156 and three findings from the rc1 live run and
QA's rc2 check; **0.19.0-rc4** fixes two #166 findings from the rc3 live run; **0.19.0-rc5**
prevents #167's lost characters instead of only reporting them (reopened by Radek); **0.19.0-rc6**
gives the README and the site's `og:image` a new screenshot of the live team. No protocol or ledger
format change; new state files `.xt/state/board_watch.json` (+ `.out`, `.err`),
`.xt/state/operators.json` (+ `.xt/operators/`) and `.xt/state/prompt_resends.json`, and the
agents' start records in `.xt/state/versions.json` may carry `codex_options`.

### Added

- **Network for one Codex agent (#169).** `codex_options = ["sandbox_workspace_write.network_access=true"]`
  on an agent's `team.toml` entry passes `-c sandbox_workspace_write.network_access=true` when xt
  starts it. Only xt's allowlist is accepted, which in this release is that network switch alone
  (`true` or `false`): any other key or value, or the line on a non-Codex agent, refuses the start
  and names what's allowed. The start note, `xt status`, the brief and the agent's detail show the
  options (with "network on: it can reach any host"), and say when the running start has other
  options than `team.toml`; `xt harnesses` says the key is for Codex only. The options are kept
  with the agent's start record (`.xt/state/versions.json`). Without the line nothing changes.
- **Tell the lead when a card enters a Board column (#135).** An optional `[board_watch]` section in
  `team.toml` names a command (an argument list, run without a shell, with no input and the
  supervisor's environment), an `interval` (default 5m), a `timeout` (default 30s) and optionally
  the `column`'s name. The supervisor runs it in the background and reads, on exit code 0, one JSON
  array of the cards in the column (`[{"number": 129, "title": "…"}]`, at most 64 KB). Its first
  success after a supervisor start records the set; each later card number not in it reaches the
  lead as one system message ("Card 129 (…) is now in Ready to build (seen by the board watch)").
  A card leaving causes nothing. A non-zero exit, a timeout, unreadable output or a command that
  can't start raises one `boardwatch` alert per outage with the cause and the first line of the
  command's error output; the next success clears it and reports the cards that entered meanwhile.
  `xt status` shows the last success or the failure. xt contains no board code: Fizzy is an
  example (`docs/examples.md` §8). New state: `.xt/state/board_watch.json` and the last run's
  `.out`/`.err`.
- **An operator sender and time-bound delegation (#166).** The human registers an outside process
  acting for them (typically their own coding-agent session) from their own terminal: `xt operator
  add NAME --pid PID`, where PID is the operator's harness process (claude, codex or pi, not a team
  agent's) as its own `xt operator pid` prints it. xt records the process's start time and writes a
  token to `.xt/operators/NAME.token` (mode 600). `--as NAME` is then accepted only when both match:
  `XT_OPERATOR_TOKEN` holds the token, and the registered process is the command's own or an
  ancestor; either alone is refused, and the operator re-registers after each of its sessions. An
  operator sends reports to the liaison only, under its own name and Flow lane, marked `(sent by
  NAME, an operator, on the human's behalf)` and shown in the human's Inbox; any other command is
  refused. `xt delegate NAME [--for 30m] [--only …]` (human only; at most 60 minutes, 30 by default;
  `xt delegate --revoke` ends it) lets it run `restart`, `reset`, `spawn` of an existing agent as it
  is, and `up`, each recorded as `NAME, delegated by human until HH:MM: xt …`; expiry is checked at
  each command. `down`, `restart --all`, answers, approvals, version switches, registering operators
  and granting delegation are never delegated. `xt status` and the TUI's Team header show an active
  grant. The `--as human` guard is unchanged. New state: `.xt/state/operators.json`,
  `.xt/operators/`.

### Fixed

- **pi gets its first prompt whole (#167).** On a first start pi takes input a moment after Herdr
  reports it started, and the first prompt lost its first five characters; xt then couldn't link
  the agent's session log, so `xt status` showed its context and today's usage empty, with no
  reason. For pi, xt now waits until the screen has stayed unchanged for three checks a second
  apart (at most 30) before it types the prompt, then checks pi's session log for the prompt's
  opening. A prompt that still arrives without it raises a `partprompt:<name>` alert (cleared at the
  agent's next start) and the start record says so; when no log shows the prompt yet, the start
  record says it wasn't checked. Two new adapter keys carry this, `ready_settle` and
  `check_prompt_in_log`, set in `harnesses/pi.toml` only: Claude Code and Codex starts are
  unchanged. `xt status` now says `no session log found for <name>: its context and today's usage
  can't be read` under a running agent whose log xt can't find, for any harness.
- **pi's first prompt arrives whole after all (#167, rc5).** The readiness wait didn't prevent the
  loss: rc3 lost the same five characters after a 3-second still screen, and a cold start captured
  later lost none, with pi's screen up at 0.9 s. xt now types one guard line before pi's first
  prompt: `(xt: this line only guards your first prompt against lost characters; ignore it. The
  prompt follows.)`. Lost characters come out of that line, and a damaged guard line doesn't count
  as damage. A prompt whose opening is still missing in pi's session log is resent whole once,
  by the supervisor, when the agent is idle and before any queued message reaches it. The resend
  has the guard line and a note that it replaces the damaged one: a second reading of the prompt,
  about 25k tokens for a lead, only when it triggers. The `partprompt:<name>` alert is now the last
  resort: it is raised if the resent prompt is damaged too (checked for 2 minutes) or Herdr refuses
  the resend. xt searches the first 2 MB of a pi session log for the prompt, since a resent one
  comes after the agent's first turn. New adapter key `first_prompt_prefix` (pi only; Claude Code
  and Codex prompts are unchanged); new state file `.xt/state/prompt_resends.json`.
- **The board watch's alert shows Fizzy's error (#135, rc3, from the rc1 live run).** A failing
  command with empty error output now puts the first lines of its standard output in the alert
  (Fizzy prints its error JSON there); before, the alert gave only the exit code.
- **A delegated command is logged after it ran, or as failed (#166, rc4, from the rc3 live run).**
  An operator's `xt spawn lead` on a running lead failed, yet the log said `helper, delegated by
  human until …: xt spawn lead` as if it had run. The line is now written once the command has run;
  one that fails gets `(failed: <reason>)`, and a refused one (no grant, not delegable) none. An
  operator's `xt restart` of a name that isn't an active agent now fails instead of being logged as
  a restart.
- **`xt spawn`'s help says what it does (rc4).** It said "existing: restarts it", but spawn has
  always refused an agent that is running. The help and the refusal now say: spawn starts an agent
  that isn't running; `xt restart <name>` restarts a running one.

### Documentation

- **README, architecture and site caught up (#156, rc3).** The README's "Added since" list covers
  0.11.0 to 0.19.0 with an entry for each release, and its version examples name v0.19.0.
  `docs/architecture.md` describes 0.19.0. The site's first screenshot and its TUI section use new
  0.19.0 images (`xt tui --demo` at 160×40, with Flow and with Work), with new alt text; the old
  `screen.jpg` and `tui-v0170.svg` are gone. From rc6 the README's picture is a new screenshot of
  the live xt-team on 0.18.0 (`docs/screen-v0180.png`: the liaison's pane beside the TUI's Team,
  Inbox, Flow and Detail), with new alt text and caption, and the site's `og:image` is the same
  picture (`site/assets/screen-v0180.png`).
- **Examples (rc3).** `docs/examples.md` §7 shows QA's suite in a clean clone under Codex with
  network on (`UV_CACHE_DIR` inside the clone: the default cache is read-only in Codex's sandbox);
  §8 says to run the board command once by hand, since a wrong column id prints `[]` and exits 0;
  the new §9 is an operator with a delegation (QA's rc2 check). The user guide says the same about
  the board command.

### Upgrading

- From 0.18.0: `git pull upstream main` (or `xt version use v0.19.0`), then `xt restart --all` so
  the supervisor runs the board watch and pi's prompt resend, and pi agents start with the guard
  line. Nothing changes until you use the new keys: `codex_options` on a Codex agent (then `xt
  restart <name>`), or a `[board_watch]` section (the supervisor picks it up on its next tick).
  Operators need `xt operator add` from your own terminal. From 0.19.0-rc6: nothing but the
  version changes.

## [0.18.0] — 2026-10-01

The release: the same code and docs as 0.18.0-rc6 (only the version and this changelog changed).
Agent lifecycle: fewer manual resets, and a warning when agents run without xt's launch settings.
Five cards: #134, #114 and #165 to their approved specs, and two verification cards with recorded
checks and no code change: #62 (the human-identity guard holds in an interactive Codex session,
through the agent and through Codex's own shell) and #55 (the pi adapter's smoke test; a
first-prompt and session-log defect found there is left for a separate card). **0.18.0-rc1** has
#134 and #114; **0.18.0-rc2** adds #165; **0.18.0-rc3** fixes rc1's queued reset (QA) and adds
the policy example; **0.18.0-rc4** makes #165 say "not checked" from a sandbox; **0.18.0-rc5**
makes its warning need positive evidence; **0.18.0-rc6** ignores harness helpers and recognises
Codex's sandbox by its PID 1. No protocol or ledger format change; one new state file,
`.xt/state/resets.json`.

### Added

- **Queue a reset until the agent is free (#134).** `xt reset <name> --when-idle` records the reset
  and returns at once; the supervisor runs it, through the same checkpoint as a plain reset, the
  next time the agent is idle, owns no open goal or task and has no messages waiting. After the
  checkpoint it checks again: the session is replaced only once the agent is idle again, and an
  open item, a message waiting for it or one delivered since it was asked sends the reset back to
  waiting (it stays queued; a fresh checkpoint is asked for later). No checkpoint, or still busy,
  5 minutes after asking drops it, leaving the session as it was. The queue survives a supervisor
  restart, holds one reset per agent (queueing again shows the existing one), and shows as `reset queued (by human at HH:MM): …` in `xt status` and the agent's
  detail in the TUI. `xt reset <name> --cancel` removes it; stopping or retiring the agent drops it.
  Each step is a line in the message log. Human only, like `xt reset`. A plain `xt reset` is
  unchanged (it replaces a queued one).
- **Reset idle agents automatically above a context size (#114).** Off by default. With `[policy]
  auto_reset = true` the supervisor queues a reset (#134's path) for an agent that is idle, owns no
  open work, and has a known context reading from the last 2 hours above `auto_reset_tokens`
  (default 150,000 tokens, whatever the window), unless a reset ran for it within
  `auto_reset_cooldown_hours` (default 6). An agent's own `auto_reset_tokens` overrides the team's;
  `"off"` exempts it. The ledger says why (context and threshold in tokens, the policy). A cancelled
  or abandoned automatic reset also waits for the cool-down. A bad setting is said once in the
  supervisor's log and resets nobody. A copyable configuration is in
  [docs/examples.md](docs/examples.md#6-reset-heavy-agents-automatically).
- **A warning when an agent runs without xt's launch settings (#165).** After a power cycle the
  terminal multiplexer can resume every agent in its old conversation without the identity,
  model, settings file and connector and tool blocks xt starts it with. The supervisor (about once
  a minute), `xt status` and `xt up` now look for each running agent's harness process in the team
  repo with its `XT_AGENT` in the environment (read from `/proc`). A warning needs evidence: visible
  harness processes of the agent's kind without `XT_AGENT`, at least as many as the agents of that
  kind left without a match (rc5); then they say `<name> is running without xt's launch settings
  (restored by the multiplexer?) … Run xt restart <name> (or --all)`, raise one `launch:<name>` Inbox alert per agent, and the Team pane shows a red `!` in
  place of the agent's dot. The alert clears when xt starts the agent again. When xt can't look
  properly, the agent is `not checked` in `xt status`, never a match or a warning, and no alert is
  raised or cleared for it: a harness process of its kind it can't inspect, its process not
  visible (a sandbox, which may show only another agent's process), fewer unlaunched processes
  than unmatched agents, or a sandboxed shell (a nested PID namespace in `NSpid`, or a PID 1 that
  isn't a system's init, as in Codex's sandbox). Only the harness programs themselves count, so a
  helper such as `codex-linux-sandbox` is never taken for an agent. (rc4 to rc6, from the rc2 and
  rc4 staging: a Codex sandbox reported every agent as restored.)

### Changed

- **`xt status` says whenever the supervisor isn't running (#165),** not only when messages or jobs
  are waiting for it. A supervisor that saved Herdr's agent list in the last 30 seconds counts as
  running even when its pid isn't visible, and from a sandboxed shell otherwise the line reads `the
  supervisor: not checked` (rc4).

### Upgrading

- From 0.17.0: `git pull upstream main` (or `xt version use v0.18.0`), then `xt restart --all` so
  the supervisor runs queued resets. The automatic policy stays off until you add `auto_reset =
  true` to `[policy]` in `team.toml`.

## [0.17.0] — 2026-09-30

The release: the same code and docs as 0.17.0-rc1 (only the version and this changelog changed).
TUI layout and consistency: three cards, #162, #151 and #133, to their approved specs. No protocol,
ledger or state-file change; one new command, `xt version check`. **0.17.0-rc1** (2026-09-30) has
all three.

### Added

- **The Team header and harness lines open Detail (#151).** In the Team pane the header and each
  harness line can be selected ahead of the agents (`j`/`k`, the arrows, a click). The header's
  detail, *xt and the team*, shows the published version with when it was checked or why the
  check failed, the installed and running versions per agent, the notes `xt status` prints and
  today's usage split by agent. A harness line's detail shows each account window with the share
  used, the reset time, the reading's age and its source, or why there is no current reading and
  what brings one back, then the harness's agents with model and today's tokens. A harness with a
  stale or missing window shows a dim `?` after its name.
- **`xt version check` (#133).** Asks the upstream for the newest release now and prints the result
  and the versions line `xt status` shows. Any member may run it; it needs network access.

### Fixed

- **The published version no longer goes stale after a release (#133).** The supervisor checks it
  once when it starts (in its loop, so an offline start isn't held up), and `xt version use` and
  `xt version rollback` check it after a successful switch; the 6-hour interval applies otherwise,
  and a failed check still keeps the last known version. A cached version older than the installed
  final release is never shown: `xt status`, briefs and the TUI say `published ≥ installed, check
  pending`, and the supervisor tries again every 15 minutes until a check succeeds.

### Changed

- **Three bands (#162).** The TUI is laid out in three bands: the Team pane and the Inbox side by
  side on top, with the same height, which the team decides (up to 60 % of the terminal); Work or
  Flow in one full-width pane in the middle; the detail pane full width at the bottom, shorter
  than the others (4 to 8 rows), scrolling inside; the key line last. This replaces the 0.16.0
  layout (Team on top, Inbox over Work on the left, Detail on the right, Flow at the bottom) and its
  rule that the Inbox is the tallest list.
- **Work and Flow share a pane (#162).** `2` shows Work and `3` shows Flow in the middle band; the
  title shows both names like tabs, the one on screen with its counts, the other dim. Each keeps its
  selection and scroll position while the other is shown. `tab` and `esc` work as before.
- **Numbered titles (#162).** Every pane's title reads `[n] - Title - info`: `[0] - Team`,
  `[1] - Inbox - ⚑ 2 · ✉ 1`, `[2] - Work - 1 open · 3 done`, `[3] - Flow - 12 of 40 · system hidden (t)`,
  `[4] - Detail - Inbox`, where `n` is the pane's key.
- **A one-column Team pane (#162).** The header (wrapped between its parts, so nothing that needs
  you is cut off), today's tokens and cost, a line, then each harness's usage and its agents, one
  per line, with a line between harnesses. It never scrolls: a team too big for it shows what fits
  and a last line `+N more (widen the terminal)`, N being the agents and harness lines out of view;
  `j`/`k` and the page keys reach the agents in view. This replaces 0.16.0's up-to-three columns and
  its cap for a big team on a small terminal.
- **NOTIFICATIONS (#162).** The Inbox's New section is called NOTIFICATIONS; its unread rows are
  bold, and the title keeps the unread count. What it holds and when it clears don't change.
  `xt inbox` still says New.
- **A key line per pane (#162).** The bottom line shows the focused pane's own keys first (Inbox:
  `a/d`, `s answer #N` while a question is selected, `c`, `space`; Team: `u/U`, `x/X`, `R`, `f`;
  Work: `space`, `o`; Flow: `t`, `f`, `g/G`), then `S`, `/` and `v`, which work everywhere. Keys
  for moving around (`0`-`4`, `j/k`, `tab`, `enter`, `esc`), `h` and `q` are left to the help
  screen, which lists every key.
- **Newest on top everywhere (#162).** Flow lists the newest message first (time runs upward, a
  `── Sep 28 ──` row over an earlier day's messages); `g` goes to the newest (top) and `G` to the
  oldest. The Inbox's Needs you and Work's tasks under a goal are newest first too. In every list,
  with the top row selected the selection stays on the top row as new rows arrive; select another
  row and it stays there. This replaces 0.16.0's newest-at-the-bottom Flow.
- **The detail pane scrolls to a thread (#162).** In the short bottom pane a message's thread gets
  the pane's height; `j` (or the wheel) first scrolls the thread into view, then moves through its
  hidden rows as before.

### Upgrading

Nothing to do beyond `xt restart --all` (or restarting `xt tui`).

## [0.16.1] — 2026-09-30

The release: the same code and docs as 0.16.1-rc2 (only the version and this changelog changed).
A patch release for the TUI of 0.16.0: six fixes from its first live use, one card (#157), to the
approved spec. No command, protocol, ledger or state-file change. **0.16.1-rc1** (2026-09-30) has
all six. **0.16.1-rc2** (2026-09-30) adds change 5b, the answered-questions fold, which Radek added
to the card while rc1 was being built; the rest is unchanged from rc1.

### Fixed

- **Every pane has a key (#157).** `0` focuses the Team pane and `4` the detail pane, next to `1`
  Inbox, `2` Work and `3` Flow; `esc` in the detail pane goes back to the pane you came from (Team
  too). The key line says `0-4 panes` and the help lists them. `tab` still goes round the panes
  (its word in the key line is now `next pane`).
- **Arrows work in every pane (#157).** Up and down move in the Team pane and in Flow as `j`/`k`
  do. In the Team pane `Home` and `End` select the first and last agent, and `PgUp`/`PgDn` move by
  the agent lines in view (the whole team when it all fits).
- **The state dot (#157).** The dot before each agent in the Team pane is drawn from the state word's
  colour in one place: working yellow, idle and done green, blocked red, not running dim, in the
  terminal's own named colours (your theme decides the shades; a theme whose yellow is a green shows
  working as green). v0.16.0 already coloured it this way through a second table in the model; the
  dot and the word can no longer differ. No other colour changes.
- **`space` folds in the Inbox too (#157).** On `(N older, seen)` or on a row under it, and on the
  new `(N earlier, seen)`, `space` opens or folds it (the selection goes back to the fold row),
  like `enter`. Anywhere else in the Inbox it says where it works.
- **New items you have seen stay reachable (#157).** Reports to you and your closed goals that New
  showed and you have since seen fold under New as `(N earlier, seen) ▸`, newest first, dim, for 7
  days, also after quitting and restarting the TUI. `enter` or `space` opens them; the detail pane
  shows each as before. Nothing is stored for it: it reads the ledger and the existing seen marker.
  `xt inbox` is unchanged.
- **Your answers stay visible (#157, rc2).** A question you answered left the Inbox with no trace
  there. Now the questions you answered in the last 7 days fold under Needs you as
  `(N answered, last 7 days) ▸`, newest first, one row each with the question and your answer
  (`✓ #2098 v0.16.1 spec → 1: Approve and build`). The detail pane shows the question with its
  options, your answer and the thread; `enter` or `space` opens and folds it. It reads the
  ledger only (your reply with `--ref` to the question, which `xt answer` and the TUI's `s`
  record).
- **The mouse (#157).** A click selects the row in any pane (a Team agent, a Flow row, an Inbox or
  Work row) and focuses that pane; the detail pane follows, but focus stays where you clicked
  (in v0.16.0 a click in the Inbox or Work threw focus into the detail pane, and Team and Flow
  ignored clicks). `enter` or `4` moves focus to the detail pane. The wheel scrolls Flow (three rows a
  notch; the selection stays in view, and scrolling up stops Flow following new messages) and the
  detail pane (a long thread's hidden rows first, as `j`/`k`), without moving focus.

### Upgrading

- From 0.16.0: `git pull upstream main` (or `xt version use v0.16.1`), then quit and start `xt tui`
  again. Agents need no restart: nothing they see changes.

## [0.16.0] — 2026-09-30

The release: the same code and docs as 0.16.0-rc6 (only the version and this changelog changed).
A TUI-focused release, built card by card to the approved specs of the TUI redesign: six cards,
#127, #132, #128, #129, #131 and #130. How the candidates got here: **0.16.0-rc1** (2026-09-30) has the first two cards: #127 (Inbox groups and friction read state)
and #132 (rows cut at pane width, with ages). **0.16.0-rc2** (2026-09-30) adds #128 (the Team pane
replaces the Status pane and the Team panel); #127 and #132 are unchanged from rc1 except that the
Inbox is now panel 3. **0.16.0-rc3** (2026-09-30) adds #129 (the Work outline replaces the Goals
and Tasks panels); the earlier cards are unchanged from rc2 except the panel numbers (Inbox is now
1) and the panel heights. **0.16.0-rc4** (2026-09-30) adds #131 (the detail pane shows the thread;
the Supervisor panel becomes a pop-up on `v`, and three supervisor failures raise Inbox alerts);
the earlier cards are unchanged from rc3 except that the Supervisor panel and its key `4` are
gone. **0.16.0-rc5** (2026-09-30) adds the last card, #130 (the Flow lane chart replaces the Log),
and the final layout; the earlier cards are unchanged from rc4 except the pane heights, the start
pane (the Inbox), a cap on the Team pane for small terminals, the key line's order and a thread
window fix in the detail pane. **0.16.0-rc6** (2026-09-30) is rc5 plus the fix for QA's rc5 FAIL on
#130 criterion 1 (see Fixed).

### Added

- **Inbox in three groups (#127, rc1).** The TUI's Inbox and `xt inbox` show **Needs you** (open
  questions with `N options` when they have choices, approvals, alerts with `⚠`; they stay until
  answered, decided or cleared), **New** (goals you dispatched that closed and reports to you, since
  you last looked, newest first) and **Friction** (unread only). An empty group isn't shown. The
  Inbox's title carries the counts, e.g. `[1]─Inbox─⚑ 1 · ✉ 2 · ✱ 1` (`[4]` in rc1, `[3]` in rc2),
  leaving out a zero.
- **Friction read state (#127, rc1).** Friction is unread until you've seen it: in the TUI, once
  you leave the Inbox (or quit) after it was on screen there; `c` on a friction row marks it seen
  at once; `xt inbox` in your own terminal marks the friction it printed as seen. An agent's `xt
  inbox` changes nothing (the same human-terminal rule as the done marker of #125). Seen friction
  folds into one row, `(12 older, seen) ▸`, that `enter` expands (newest first) and folds again;
  `xt inbox` prints `(12 older, seen; …)` and `--seen` lists them. On the first run after the
  upgrade all existing friction counts as seen. Friction stays in the log.
- **Ages on rows (#132, rc1).** Each row in the Goals, Tasks (Work from rc3), Inbox and Log (until rc4) panels ends with a dim
  age at its right edge, by one rule in whole units rounded down: `now` under 10 s, then `45s`,
  `14m`, `3h`, `2d` up to 59 days, and whole weeks from 60 days (`8w`). A goal's age is its newest
  activity (the goal, its tasks and their replies). Team rows have none; Supervisor rows (the `v`
  pop-up from rc4) and Flow rows (rc5) keep their clock time.
- **The Team pane (#128, rc2)** at the top of the TUI replaces the Status pane and the Team panel.
  Its header line has the team, xt's version with `(latest)`, a newer published release or
  `running …: restart to update`, the agents running, open goals, `⚑ N needs you` and `✉ N new`
  (the Inbox's counts) or "nothing waiting for you", messages or jobs stuck over a minute, and
  today's tokens and estimate on the right. Then one block per harness, in a fixed order: its
  account windows as bars with the share used and the reset time (`CLAUDE 5h …`, `CODEX 7d …`; a
  window with no current reading isn't drawn), and its agents in columns that line up: a state
  dot, the name, a short model (`sonnet 5.5`, `opus 5.5`; for `default`, the model the agent's own
  session log names, else `default`), the state, and the context as tokens, a bar and a
  percentage of the window. Agents fill up to three columns as the width allows (five agents take
  two lines at 160 columns); blocks sit side by side or one under the other, whichever is shorter.
  The pane is as high as its content. It has no number key: `tab` reaches it, `j`/`k` select an
  agent for its detail and for `u`, `x`, `R` and `f`.
- **Action results in a toast (#128, rc2).** The result of your last action (`alert cleared`,
  `starting carol…`) is a one-line toast at the bottom that dims and goes after about ten seconds
  without a key press. It's never part of the Team pane.
- **The Work outline (#129, rc3)** replaces the Goals and Tasks panels: goals with their tasks
  under them. A task belongs to the goal at the root of its `ref` chain (through other tasks or
  messages); a task that reaches no goal sits under a final `no goal` row. Open goals come first,
  unfolded, newest activity first; a goal row shows its fold mark, id, first line, owner,
  `done/total` of its tasks and the age of its newest activity. A task row shows `●` open, `✓` done
  or `✗` failed or blocked (closed with a `done` starting FAIL or BLOCKED, or open while its owner
  is blocked), id, owner, first line and age. The liaison's drafts follow the open goals. Done goals
  sit under one `done (N)` fold, folded, newest first, each folded with `n/n ✓`. `space` folds or
  unfolds the selected row (on a task, its goal); `o` shows open work only (hides `done (N)` and
  done tasks; the pane's bottom edge says `open only`); both, and the selected row, stay across
  refreshes. `enter` shows the selected row in
  the detail pane. The title counts the goals, `[2]─Work─1 open · 63 done`. An open goal older than
  the 30 days the TUI reads still shows.
- **The detail pane shows the thread (#131, rc4).** The selected item comes with its thread in time
  order: for anything under a goal (the root of its `ref` chain: a goal, a task, a question or
  report about it, a done goal in New), the goal, its tasks and every reply; for a message without
  a goal, the message and the messages that reply to it. Each thread row shows the time, sender →
  receiver, type, id and first line; the selected message is marked `◀ you are here`. Below the
  thread come the goal's usage and the keys that apply to the selected item (the `xt log --id`
  hint is gone); a goal's brief follows at the end. A thread longer than the pane shows the part
  around the selected message and says how many rows are hidden above and below; after `enter`,
  `j`/`k` bring them in, and the place survives a refresh. A message whose ref points to one the TUI
  doesn't have shows alone with its replies.
- **The supervisor's log on `v` (#131, rc4).** `v` opens what the supervisor did, newest first, in
  a pop-up over the TUI; `j`/`k` scroll it, `esc` closes it, and it follows the refresh while open.
- **Supervisor failures raise Inbox alerts (#131, rc4).** A failed wake-up, a failed notification
  and a failed usage recording, which until now appeared only in the supervisor's log, each raise
  an alert under Needs you (`⚠ wake-up failed: scout: …`) with the first line of the error; it
  counts in the Inbox's title and the Team header. While the alert is open, more failures of the
  same kind update it instead of adding rows: the newest error's first line, the count (the TUI's
  row starts `⚠ ×3` and its age is the last failure's; `xt inbox` and briefs say `×3, last 14:05`); after `c` (or `xt clear`), the next failure raises a new one. The
  alert about a failed notification is never notified itself. Other alerts are unchanged.
- **The Flow lane chart (#130, rc5)** replaces the Log panel. Pane 3, across the bottom of the TUI,
  draws the messages as a swim-lane chart: one lane per agent (`human`; `xt` when it sent a shown
  message; the liaison, the lead and the rest of the roster in order; a dim lane at the end for a
  retired or unknown agent while one of its messages is in view (rc6)), time down the left (local `HH:MM`, a
  `── Sep 29 ──` row where the day changes, the newest at the bottom), and one row per message: an
  arrow from the sender's lane to the receiver's with the type's glyph and label at the sender end
  (`◆` goal, `▸` task, `◇` done, `✉` report, `⚑` ask or approval, `✱` friction, `⚠` alert in amber,
  `○` a note or a message the human typed), dotted into the human's lane, the label dropped when
  the lanes are too close; `#id` and the first line on the right, cut at the pane's edge. Flow rows
  show a clock time, not an age. System lines (xt's `system` lines, `wake`, `nudge`) are hidden;
  `t` shows or hides them, and approval requests and alerts show either way. `f` filters to one
  agent's messages or one goal and its `ref` chain (the team's lanes stay); the same pick again, `esc` in
  the picker or `esc` in Flow clears it; `/` filters by the message text. `j`/`k`, the page keys and
  `g`/`G` move; with the newest row selected Flow follows new messages. `enter` shows the message
  and its thread in the detail pane. The title says `N of M` (rows in view of all that pass the
  filters), whether system lines are shown, and the filter. Lanes that don't fit collapse into one
  `+N` lane, and a message to or from a collapsed agent starts its text with the agent's name; a
  pane under 60 cells lists one line per message (`time sender → receiver glyph #id first line`).
  Only the rows in view are drawn: a 5,000-message ledger opens in about 0.3 s and each key takes
  under 0.1 s in the Pilot test. `xt log` is unchanged.

### Changed

- **The final layout (#130, rc5).** Team on top; Inbox over Work on the left, the detail pane on
  the right; Flow across the bottom, full width; the key line last. The TUI sets the heights for the
  terminal: Flow about a third (6 to 14 rows), the Team pane what it needs, and the Inbox the larger
  part of the rest, so it is the tallest list pane (at least 8 rows at 160x40, 5 at 100x30; were 3
  and 2 in rc1). On a small terminal a big team's Team pane is capped so the Inbox keeps 5 rows: it
  shows the header and the lines around the selected agent, and its bottom edge says how many lines
  are out of view. The TUI starts in the Inbox (was Work).
- **Keys (#130, rc5).** `1` Inbox, `2` Work, `3` Flow (was Log); Team and the detail pane have no
  number. New: `t` system lines, `f` in Flow its filter (`f` on an agent in Team still switches
  Herdr), `g`/`G` and the page keys in Flow. The key line lists what `s` does, then `h`, `q`, `1-3`,
  `j/k`, `space`, `enter`, `a/d`, `/`, `t`, `f`, `v`, and the other keys while they fit; on a narrow
  terminal the keys keep their place and drop their words, from the end. `o open only` shows while
  Work has focus and `g/G top/end` while Flow has. `h` has a Flow section.
- **Detail's thread window (#131 fix, rc5).** In a detail pane only three or four rows high (the
  100x30 layout), the window around the selected message could leave the message itself out of
  view; it now keeps it in view.

- **Panels and keys (#131, rc4).** The Supervisor panel is gone (its contents are the `v` pop-up);
  the keys are `1` Inbox, `2` Work, `3` Log (`4` did the Supervisor in rc3), and the key line and
  `h` add `v supervisor`. The detail pane has the whole right-hand side. `enter` on a row in the
  Inbox and Log now shows it in the detail pane too, as it did in Work (enter on the Inbox's
  `(N older, seen)` row still folds).

- **Panel keys (#129, rc3).** With Goals and Tasks merged into Work, the keys are `1` Inbox, `2`
  Work, `3` Log, `4` Supervisor (were `1` Goals, `2` Tasks, `3` Inbox, `4` Log, `5` Supervisor in
  rc2); the key line and `h` say so, and the key line adds `space fold · o open only` while Work
  has focus. The TUI starts in Work, as it started in Goals. The left column is now Inbox, Work
  and Log, with Inbox and Work the same height and Log half of that.
- **Panel keys (#128, rc2).** With Team out of the numbered panels, the keys are `1` Goals, `2`
  Tasks, `3` Inbox, `4` Log, `5` Supervisor (were 1–6 with Team at 2); the key line and `h` say so.
- **Agent states (#128, rc2).** An agent that isn't running shows `stopped` in the Team pane (its
  detail still says `not running`).
- **Long action results (#128, rc2)** are cut to one line in the toast instead of wrapping in the
  Status pane.

- **Rows use the whole panel (#132, rc1).** List rows are cut at the panel's current width in
  terminal cells, not at fixed widths (60, 50, 40 characters), with `…` only when text was cut, and
  cut again when the terminal is resized. Wide characters never spill out of the panel.
- **The focused panel's title is reversed (#132, rc1)**, as well as the frame colour.
- **`xt inbox` output (#127, rc1).** The sections are now `Needs you:`, `New since you last
  looked:` and `Friction reported about xt or a harness:`, left out when empty (`Nothing for you.`
  when all are). Reports to you appear once, under New, instead of in a "Recent messages to you"
  list that repeated them. `--days` defaults to 30 (was 7), as the TUI; `--limit` caps each group.
- The TUI's Inbox rows for questions and approvals start with `⚑` (was `?`); open task rows say
  `open` where they showed the age in yellow (rc1 and rc2; from rc3 a task row starts with `●`).

### Fixed

- **Flow's retired lanes (#130, rc6; QA's rc5 FAIL on criterion 1).** A retired or unknown agent's
  dim lane appeared whenever any of its messages passed the system toggle, even with none of them
  on screen. The lane is now there only while one of its rows is in view, after `f`, `/`, `t`,
  scrolling and resizing. The team's own lanes, the chart width and the `+N` collapse are
  unchanged; `f` still offers every agent, retired ones included.

### Upgrading

- From 0.15.0: `git pull upstream main` (or `xt version use v0.16.0`), then `xt restart --all`
  so the supervisor starts the friction marker and raises the new failure alerts. Friction from
  before that shows as seen. New keys in `.xt/state/inbox_seen.json` (`friction_upto`,
  `friction_seen`) and in `.xt/state/alerts.json` (`count`, `last`, on the failure alerts); no
  state format change. Scripts that parse `xt inbox` need the new section names.
  From 0.16.0-rc6: nothing but the version changes. From an earlier 0.16.0 candidate: the same
  restart.

## [0.15.0] — 2026-09-30

The release: the same code and docs as 0.15.0-rc7 (only the version and this changelog changed).
Seven cards: #122, #113, #120, #105, #125, #107 (research only) and #124 (docs and site). How
the candidates got here: **0.15.0-rc1** (2026-09-29) has the first batch: #122
and #113. **0.15.0-rc2** (2026-09-29) adds #120 and #105; #122 and #113 are unchanged from rc1.
**0.15.0-rc3** (2026-09-29) adds #125 and #107 (research only, no code); the earlier cards are
unchanged from rc2. **0.15.0-rc4** (2026-09-29) is rc3 plus the fix for QA's rc2 FAIL on #120
(see Fixed). **0.15.0-rc5** (2026-09-29) adds the last card, #124 (docs and site); it has all
seven cards of the approved composition, and the code is unchanged from rc4. **0.15.0-rc6**
(2026-09-29) is rc5 plus the fixes for QA's rc3 FAIL on #125 (a goal notifies only once, when
it's done) and QA's rc4 FAIL on #120 (no tolerance for a reading timestamped later than now).
**0.15.0-rc7** (2026-09-29) is rc6 plus the README fix for QA's rc5 FAIL on #124 (see
Documentation); code unchanged from rc6.

### Added

- **One notification when a goal you dispatched is done (#125, rc3).** A goal the liaison opened
  now notifies you exactly once, when it's done. The notification is the liaison's report to you
  about it after the closure (with `--ref` to the goal or to the lead's `done`); if none arrives
  within 5 minutes of the closure, the supervisor sends "goal #N done" with the first line of the
  closing summary. Progress reports about a goal that's still open don't notify (rc6, QA's rc3
  FAIL: rc3 to rc5 notified them too). Other liaison reports to you, not about a goal, notify once
  per `--ref`. Tasks, sub-team goals and friction
  never notify, and quiet hours apply as for questions. The Inbox (TUI and `xt inbox`) has "Done
  since you last looked": each closed goal, with the lead's closing summary and its message id,
  until you've looked (in the TUI, when you leave the Inbox panel or quit; with `xt inbox`, in your
  own terminal). The liaison role now says to send the goal-done summary as an xt report. New state:
  `.xt/state/goal_notices.json`, `.xt/state/inbox_seen.json`.

- **Claude plan usage in `xt status` and the TUI (#120, rc2).** Claude Code logs no rate limits;
  it passes them only to a status-line command. The new `bin/xt-statusline` is one: point a Claude
  agent's settings file at it (`"statusLine": {"type": "command", "command":
  "/path/to/team/bin/xt-statusline"}`) and it keeps the five-hour and seven-day windows (percent
  used, reset time, when read; nothing else from the status) in `.xt/state/claude_plan.json`,
  written atomically, under `XT_ROOT` or else its own checkout. `xt status` and the Status pane show
  `claude 5% of 5h, resets …; 7% of 7d, resets …; read 2m ago (account-wide)` next to the Codex
  allowance. A session's first call (no limits yet) keeps the last reading; a window whose reset
  has passed shows "window reset, no reading since"; a reading over 3 hours old or a missing or
  broken file shows `unknown`. Bad input never breaks the agent's status line. Tested against a
  redacted real Claude Code 2.1.284 payload. The reading is account-wide: it includes your own use.

- **`xt spawn --permissions FILE` (#122).** A spawn can give a new Claude Code agent its settings
  file: the line is written to its `team.toml` entry, as if added by hand (0.13.0, #117). The file
  gets the same check as at every start *before* anything else happens, so a bad file (missing, not
  JSON, unknown `defaultMode`, malformed rule, outside the team repo) refuses the lead's request
  before an approval reaches you. The approval (ledger message, TUI detail, `xt approve` and `xt
  inbox` lists) names the file and its `permissions.defaultMode`; when no file applies to a Claude
  agent it says "WARNING: carol would start without a permissions file, so the operator's own
  claude defaults apply", in red in the TUI. Without the flag, a team `[defaults]` file applies as
  before and an existing entry keeps its own line. A harness that takes no settings file (codex, pi)
  refuses `--permissions`; a team default is skipped for it, and the approval says so. The shipped
  lead role mentions the flag.

### Changed

- **`xt log` prints the newest messages by default (#113).** Plain `xt log` printed the whole
  history (about 300 KB on a two-day-old team), and `--limit` only worked with `--watch`, so
  agents' `xt log --limit 80` still filled their context. Now it prints the newest 20 messages that
  match the filters (`--member`, `--type`, `--since`, `--id`), oldest of them first, under one line
  saying how many older ones were left out. `--limit N` gives the newest N, `--full` everything.
  `xt log --id N` still prints the whole thread (a message and its direct replies) unless you pass
  `--limit`. `--watch` keeps its default of 50 events; `--limit` below 1 is refused. `protocol.md`
  describes the default.
- **The protocol states the liaison's goal writes (#105, rc2).** Section 6 listed only notes and
  the lead's files, while the liaison role requires writing goal drafts. It now says the liaison
  creates drafts with `xt goal new`, edits `goals/drafts/<slug>.md` and dispatches them into
  `goals/<slug>.md` with `xt goal dispatch`, and writes nothing else besides its notes; the liaison
  role says the same. Wording only, no behavior change.

### Fixed

- **#120, QA's rc2 FAIL (rc4).** A plan-usage snapshot with a huge `resets_at` (10**20) raised
  `OverflowError` while formatting the reset time and broke `xt status` and the TUI's Status pane.
  Every number read from Claude Code's status line or the snapshot is now checked: `used_percentage`
  0–100, `resets_at` and the read time Unix seconds between 2000 and 2100, finite, and a real
  number (not a boolean, text, list or null). Anything else shows `unknown` (and is never stored
  from a payload); a reading timestamped later than now shows `unknown`, with no tolerance, since
  the script and xt run on the same machine (rc6, QA on rc4: rc4 and rc5 allowed 60 seconds); and
  the rest of status stays
  usable whatever the snapshot holds.

### Documentation

- **README, architecture, examples and the site caught up (#124, rc5; rc7).** The README lists
  what 0.11.0 to 0.15.0 added, with links into the user guide, apart from its list of what was
  shown in real runs as of v0.10.0 (rc7, QA's rc5 FAIL: that list had gained the v0.15.0 goal
  notification and the v0.11.0 connector block, neither live-checked as of v0.10.0; both now sit in
  the "Added since" list). It also has a first-upgrade path and `xt version
  use` in Quick start and Updating a team; its command table and configuration cover `xt reset`,
  `xt version`, `--at`, numbered answers and `permissions`. `docs/architecture.md` describes v0.15.0:
  every source file with its job, the `team.toml` keys, how a settings file, connectors and the
  model reach a harness's start command (and that the model tables only feed the context and cost
  views), and versions, the state format and snapshots. `docs/examples.md` has a second part with a
  Claude Code agent's permissions file (and `xt spawn --permissions`) and a decision question with
  options. `site/index.html` shows v0.15.0 and the same new features as the README (deploying it is
  a separate step). Tests check that every source file is named in the architecture, that the
  relative links and anchors in the repo docs resolve, and that the examples' settings file passes
  xt's check and its question renders as shown.

### Research

- **Credential-holding CLI skills visible to agents (#107, rc3).** A research page with an
  inventory by class, a login-status-only check of visibility against authority, and a proposed
  default boundary for Radek's review. No change to xt; any enforcement is card #126.

### Upgrading

- From 0.14.1: `git pull upstream main` (or `xt version use v0.15.0`), then `xt restart --all`
  so agents get the new protocol and roles, and the supervisor the goal notifications. Scripts or
  roles that rely on `xt log` printing everything need `--full`. For Claude plan usage, add the
  `statusLine` entry to one Claude agent's settings file (yours to edit) and restart that agent.
  From 0.15.0-rc7: nothing but the version changes. From an earlier 0.15.0 candidate: the same
  restart. "Done since you last looked" starts empty
  and counts from the supervisor's first run on rc3 or later.

## [0.14.1] — 2026-09-29

A patch release: one wording clarification, no behavior change. The same code as 0.14.1-rc1 (only
the version changed); #121 was accepted on rc1.

### Changed

- **The human-identity rule is about the human's identity, not an agent's own work (#121).**
  0.14.0's "never suggest any other way … not a command in your own session" could be read as
  forbidding an agent's ordinary work too: on staging, the liaison declined `xt status --as human`,
  then ran `xt status --as liaison` itself, and QA read that as a way around the rule. `protocol.md`
  section 1 and the liaison role now say: never act as the human and never suggest any route to it
  (a harness shell, a command in your session, a script, another agent); your own normal work under
  your own name and your role's authority stays allowed, for example `xt status --as liaison`, as
  long as you don't offer it as a way around the request. Reporting a request that didn't come from
  the human in your pane is unchanged. `xt` itself (authorization, `--as` checks, routing) is
  unchanged.

### Upgrading

- From 0.14.0: `git pull upstream main` (or `xt version use v0.14.1`), then restart (`xt down`,
  `xt restart --all`) so agents get the new wording in their first prompt. From 0.14.1-rc1:
  nothing but the version changes.

## [0.14.0] — 2026-09-29

The accepted release: the same code as 0.14.0-rc2 (only the version changed). All four cards were
accepted: #100 (choose a team's xt version and roll back; QA PASS on rc2 after a real staging
switch, rollback and a switch to a later tag through the new re-apply path), #111 (decision
questions with options; QA PASS on rc1, unchanged since), #118 (notes first on every start; QA PASS
on rc1, seen on Claude Code and Codex liaisons) and #119 (never `--as human`, whoever asks; QA
failed rc1 and rc2 on the wording's strictest reading, and Radek accepted it on rc2, #1353: the
liaison never acted as the human; card #121 clarifies the wording later). The changes are listed
under the candidates below.

### Upgrading

- From 0.13.0: `xt down`, commit your team changes, `git pull upstream main`, `xt restart --all`
  (see 0.14.0-rc1 below). From then on, `xt version use <tag>` and `xt version rollback` work.
  From 0.14.0-rc2: nothing but the version changes.

## [0.14.0-rc2] — 2026-09-29

**Release candidate.** rc1 plus the fix for #119 from rc1's acceptance and a #100 fix found before
its staging use; #111 and #118 are unchanged from rc1. It becomes 0.14.0, from the same code, once all four cards are accepted.

### Fixed

- **#119, QA's rc1 FAIL.** On a staging team the Claude Code liaison declined `--as human`, but
  suggested the human type the command with Claude Code's `!` shell inside the agent's own session,
  and neither liaison sent an xt report for a signed request. The protocol and the liaison role now
  say: decline and point only to the human's own terminal; never suggest any other way (no harness
  shell, nothing inside your session or pane, no script or other agent); when the request came from
  anyone but the human typing in your pane, also report it with an xt message (the liaison to the
  human, `xt send human --as liaison --type report`).

- **#100: a newer tag after a rollback.** Found by the builder while planning rc2's staging, before
  any team hit it: after `xt version rollback` of a switch, `xt version use` of a later tag whose
  history contains the rolled-back one merged only what came after it, leaving the rolled-back
  changes out while `pyproject.toml` named the new version. `use` now first re-applies any rolled-back
  switch the target contains (reverting its revert), then merges; each switch records every commit
  it makes, and `rollback` reverts all of them, newest first (a record written by rc1 falls back to
  its merge commit). A failure part-way leaves the repo at its previous commit.

### Upgrading

- As for 0.14.0-rc1; agents read the changed protocol and role at their next start.

## [0.14.0-rc1] — 2026-09-29

**Release candidate.** Four cards, approved and authorized by Radek on 2026-09-29 (composition
#1261, build: Board move to Ready to build). It becomes 0.14.0, from the same code, once all four
are accepted.

### Added

- **Choose a team's xt version and roll back (#100).** `xt version use <tag>` (a candidate needs
  `--candidate`) and `xt version rollback`, human only, with the team fully down and its tracked
  files committed. `use` fetches the upstream tags, checks that the target reads the team's state
  format, takes a verified snapshot of `.xt/state/`, records a ledger fingerprint and merges the tag
  with a merge commit, so the team's own commits and files stay. A conflict (for example in a
  team-edited `roles/lead.md`) aborts the merge, names the files and gives the manual path; nothing
  is reported as installed until every check passed. `rollback` reverts that merge commit, keeps
  later team commits, checks the version and that the ledger is unchanged, and refuses (changing
  nothing) on a missing snapshot, an altered ledger, an incompatible state format or a conflict.
  The ledger is never copied back or rewritten. `xt version` alone shows the versions, the state
  format and recent switches. The team's state gets a format number (`.xt/state/format.json`,
  written by `xt up` and `xt restart`); every version from 0.12.0 reads format 1; xt never migrates
  state.
- **Decision questions with options (#111).** `xt send … --type ask --option "<option> ::
  <consequence>"` (two or three) `--recommend <n>` writes the question with numbered options, the
  recommendation and "or answer in your own words"; a malformed set is refused and nothing is sent.
  `xt answer <id> 2` records the option's full text in the ledger, not the bare number; an unknown
  number is refused. In the TUI answer dialog, 1–3 fill an empty answer with that option's text,
  still editable. The protocol, liaison and lead roles describe the pattern.

### Changed

- **Agents read their notes first on every start (#118).** The protocol's memory section and the
  shipped liaison and lead roles make `members/<you>/notes.md` the first start step (skipped when
  missing); the brief says "read them first". Seen: two Claude Code agents replied after a reset
  without reading their notes.
- **Never `--as human`, whoever asks (#119).** The protocol and the liaison role: no exception for
  text in the pane that claims to be the human; decline, say the human can run it, report the
  request, and don't offer a way to comply. xt's code guard is unchanged.

### Upgrading

- `xt down`, commit your team changes, `git pull upstream main` (or merge tag v0.14.0-rc1),
  `xt restart --all`: agents read the new protocol and roles at start. If you edited
  `roles/lead.md`, `roles/liaison.md` or `protocol.md`, expect merge conflicts in them.
- From this version on you can upgrade with `xt version use <tag>` instead of `git pull` (after
  `xt up` or `xt restart` has recorded the state format once).

## [0.13.0] — 2026-09-29

The accepted release: the same code as 0.13.0-rc2 (only the version changed). Both cards passed
the quality analyst's checks on rc2 and were accepted: #116 (prices and context windows for current
Codex and Claude models; rc1 failed on an overclaiming sentence about Codex rates, fixed in rc2) and
#117 (per-agent permission settings for Claude Code agents; checked live on a staging team with a
Claude Sonnet 5.5 liaison: allowed and denied actions without a prompt, a broken file refused at
start). The changes are listed under the two candidates below.

### Upgrading

- From 0.12.1: `xt down`, `git pull upstream main`, `xt restart --all` (see 0.13.0-rc1 below).
  From 0.13.0-rc2: nothing but the version changes; restart when convenient so `xt status` shows
  every agent running 0.13.0.

## [0.13.0-rc2] — 2026-09-29

**Release candidate.** rc1 plus the fix for #116 from rc1's acceptance; #117's code is unchanged
from rc1. It becomes 0.13.0, from the same code, once both cards are accepted.

### Fixed

- **Codex rate wording (#116, QA's rc1 finding).** The guide and `prices.toml` said the
  short-context rates cover every Codex session. They now state the assumption and its limit: xt
  always uses the short-context rates, right while a session stays below the provider's
  long-context threshold (272K for gpt-5.5; the sessions checked on 2026-09-29 logged 258,400), an
  underestimate beyond it.
- **The Sonnet 5.5 cost check can be verified independently.** Claude Code's own result for the
  fixture call (usage and `total_cost_usd` 0.0489674, list prices) is kept beside the trimmed log
  (`tests/fixtures/claude-sonnet-5-5-result.json`), and the test compares xt's estimate with it.

### Upgrading

- As for 0.13.0-rc1.

## [0.13.0-rc1] — 2026-09-29

**Release candidate.** Two cards, approved by Radek on 2026-09-29 (#1150): the model data a Claude
Sonnet 5.5 agent needs, and per-agent permission settings so a Claude Code agent can run
unattended. It becomes 0.13.0, from the same code, once both are accepted.

### Added

- **Per-agent permission settings for Claude Code agents (#117).** `permissions = "settings/<file>.json"`
  on an `[[agent]]` in team.toml, or once under `[defaults]` for every Claude agent, passes that file
  with `--settings`. xt checks it before every start and refuses to start the agent when the file is
  missing, outside the team repo (absolute, `..`, a symlink out), not a JSON object, has an unknown
  `permissions.defaultMode` or a malformed `allow`/`deny`/`ask` rule, because Claude Code silently
  ignores all of those and starts anyway. Other keys pass through. The start note shows the file, a
  short content hash and the mode, and warns for `bypassPermissions` and `acceptEdits`; `xt status`
  and the agent detail show the path; `xt harnesses` shows which harnesses take a file. A
  `[defaults]` file is skipped (with a note) for Codex and pi agents; a `permissions` line on their own
  entry is refused. The protocol now says agents never edit settings files.
- **Prices and context windows for current models (#116).** `prices.toml` lists the Codex models
  (gpt-6-astra/sol/luna, gpt-5.6-sol/terra/luna, gpt-5.5) and the Claude models (Fable 5.1 and 5,
  Opus 5.5, 5, 4.8, 4.7, 4.6, Sonnet 5.5, 5, 4.6, Haiku 4.5) at Standard API rates, each with source,
  tier and checked date (2026-09-29), including the model-specific cache-read prices.
  `harnesses/claude.toml` lists their context windows, so a Claude agent on any of them shows a
  context percentage and an estimate. Codex keeps using the window its session log states.

### Upgrading

- `xt down`, `git pull upstream main` (or merge tag v0.13.0-rc1), `xt restart --all`: agents read
  the new protocol rule at start. Nothing changes until you add a `permissions` line;
  `harnesses/claude.toml` and `prices.toml` come from upstream (if you edited them locally, merge).

## [0.12.1] — 2026-09-29

The first patch release, via the team's bug path: the same code as 0.12.1-rc1 (only the version
changed). Card #115 (an agent no longer gets its first prompt twice) passed the quality analyst's
live check: after `xt restart --all` each of the four agents' session logs held its first prompt
exactly once. The change is listed under 0.12.1-rc1 below.

### Upgrading

- From 0.12.0: `git pull upstream main`; restart when convenient (`xt down`, `xt restart --all`).
  From 0.12.1-rc1: nothing but the version changes.

## [0.12.1-rc1] — 2026-09-29

**Release candidate** of the first patch release, via the team's new bug path: one bug card, no
new features. It becomes 0.12.1, from the same code, once #115 is accepted.

### Fixed

- **An agent no longer gets its first prompt twice (#115).** xt confirmed a first prompt had
  landed by finding its first line in the last 400 lines of the agent's pane. A long prompt (the
  lead's is about 25k characters) plus the agent's first output pushed that line off, so xt resent
  the whole prompt although it had landed: a double start and several thousand tokens carried for
  the whole session. xt now also accepts the prompt's last line ("Start now: …"), which stays on
  screen.

### Upgrading

- Nothing to do beyond `git pull upstream main`. The fix applies to agents started afterwards;
  restart when convenient (`xt down`, `xt restart --all`) so `xt status` shows 0.12.1-rc1.

## [0.12.0] — 2026-09-29

The accepted release: the same code as 0.12.0-rc3 (only the version changed). All four cards
(#58 team versions, #56 safe context reset, #104 clear restore output, #110 roomy composer) passed
the quality analyst's checks and were accepted; rc1 failed on #56, rc2 fixed three findings and
failed on one more, rc3 fixed it, and #56 passed after a live reset check on a staging team. The
changes are listed under the three candidates below.

### Upgrading

- From 0.11.0: `xt down`, `git pull upstream main`, `xt restart --all` (see 0.12.0-rc1 below).
  From 0.12.0-rc3: nothing but the version changes; restart when convenient so `xt status` shows
  every agent running 0.12.0.

## [0.12.0-rc3] — 2026-09-29

**Release candidate.** rc2 plus one fix for card #56 found in rc2's acceptance; it becomes 0.12.0,
from the same code, once #56 is accepted. #58, #104 and #110 were accepted on rc1 and are unchanged.

### Fixed

- **A reset was suggested for a context reading stamped in the future (card #56).** "Recent" now
  means observed within the last 2 hours and not more than 5 minutes ahead of the clock; a
  timestamp further in the future says nothing about now. Found by the quality analyst.

## [0.12.0-rc2] — 2026-09-29

**Release candidate.** rc1 plus fixes for the three problems its acceptance found in card #56; it
becomes 0.12.0, from the same code, once every card in it is accepted. #58 and #104 were accepted
on rc1 and are unchanged; #110's code is unchanged.

### Fixed

- **A reset was suggested for a context reading without a timestamp (card #56).** The suggestion
  now needs a known reading with a window *and* a recent timestamp; without one, nothing is
  suggested. Found by the quality analyst.
- **`xt reset` announced "asking … to save a checkpoint" before checking the name** (and the rest of
  what refuses a reset). All refusals now come first. Found in the staging dry run.
- **The reset line cut the checkpoint summary mid-word at 80 characters;** it now cuts at a word
  boundary and marks the cut with `…`.

## [0.12.0-rc1] — 2026-09-29

**Release candidate.** It becomes 0.12.0, from the same code, once every card in it is accepted.
Four product cards, 14 points, in the approved order.

### Added

- **Which xt a team is on (card #58).** The TUI's Status title, `xt status` and every agent's brief
  show three versions: **published** (the newest final release on the team's upstream, checked by
  the supervisor every 6 hours and cached; a failed check shows the last known one and why),
  **installed** (the team repo's own version, read every time) and **running** (the supervisor's
  version and, per agent, the xt that started it; `mixed` when they differ). A note names the
  processes not yet running the installed version, and a newer published release only produces a
  notice. Each agent's start line in the log now ends `with xt X`.
- **`xt reset <name>`: a fresh context, safely (card #56).** Refused while the agent owns open work
  (named) or is busy; otherwise the agent is asked to save what it needs into its notes and confirm
  with the new **`xt checkpoint`**, and only then gets a fresh session, whose brief points to its
  notes and the checkpoint line. No checkpoint within 5 minutes, or new work meanwhile, means
  nothing is reset. When an agent's context reaches 70% of its window (a known, recent reading),
  `xt status`, its TUI detail and the lead's and liaison's briefs suggest a reset; nothing resets
  on its own. `xt restart <name>` stays the route without a checkpoint.

### Changed

- **A roomy answer/send dialog (card #110):** about two-thirds of the screen (up to 160 columns;
  27 editable lines on a 60-row terminal), the question above it scrolls, a cursor in the text's own
  colour and a visible selection, and ctrl+c / ctrl+x / ctrl+v through the system clipboard
  (wl-copy/wl-paste, xclip, xsel or pbcopy); when none is available the dialog says so.
- **`xt restart --all` says what happened, once (card #104):** the stop/start advice lines are gone,
  and it ends with `restored: …`, `left stopped: …` and the supervisor's state; an empty record is
  told apart from a team that was merely stopped.
- Every agent's brief now points to its own notes (`members/<name>/notes.md`).

### Upgrading

- `xt down`, `git pull upstream main`, `xt restart --all`. Restart every agent: the protocol gained
  the checkpoint step, and only processes started by 0.12.0 record their version (older ones show
  as `unknown` until then).

## [0.11.0] — 2026-09-28

The accepted release: the same code as 0.11.0-rc2 (only the version changed). All five cards
(#98, #101, #102, #103, #106) passed the quality analyst's checks and were accepted; rc1 failed on
#101 and #103, rc2 fixed both. The changes are listed under the two candidates below.

## [0.11.0-rc2] — 2026-09-28

**Release candidate.** rc1 plus the two problems its acceptance found; it becomes 0.11.0, from the
same code, once every card in it is accepted.

### Fixed

- **An agent could still pass as the human (card #103).** rc1 counted a terminal on stdin as the
  human's terminal. A Codex command in pseudo-terminal mode has one, and inside Codex's own PID
  namespace the harness isn't visible among its ancestors, so an agent started by an older xt
  (without `XT_AGENT`) passed. xt now requires a controlling terminal, which the human's terminal
  has and a Codex pseudo-terminal command doesn't. Found by the quality analyst from its own shell.
- **A Codex connector opt-in exposed every app (card #101).** Codex can switch its apps on only as
  a whole, so a named opt-in exposed more than named. A Codex agent now takes no opt-in: xt refuses
  to start it with `connectors`, before opening its workspace.

## [0.11.0-rc1] — 2026-09-28

**Release candidate.** It becomes 0.11.0, from the same code, once every card in it is accepted.
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
