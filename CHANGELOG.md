# Changelog

All notable changes to xt. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and xt uses [semantic versioning](https://semver.org/) as described in the README's
[Versioning](README.md#versioning) section.

Every release has an **Upgrading** note: what a team that already runs xt has to do after
`git pull upstream main` (or after merging the release tag).

## [Unreleased]

## [0.15.0] — not released yet

**Work entry**, filled in batch by batch. **0.15.0-rc1** (2026-09-29) has the first batch: #122
and #113. **0.15.0-rc2** (2026-09-29) adds #120 and #105; #122 and #113 are unchanged from rc1.
**0.15.0-rc3** (2026-09-29) adds #125 and #107 (research only, no code); the earlier cards are
unchanged from rc2. **0.15.0-rc4** (2026-09-29) is rc3 plus the fix for QA's rc2 FAIL on #120
(see Fixed). **0.15.0-rc5** (2026-09-29) adds the last card, #124 (docs and site); it has all
seven cards of the approved composition, and the code is unchanged from rc4.

### Added

- **One notification when a goal you dispatched is done (#125, rc3).** A goal the liaison opened
  now notifies you exactly once when it closes. The notification is the liaison's report to you
  about it (with `--ref` to the goal or to the lead's `done`); if none arrives within 5 minutes of
  the closure, the supervisor sends "goal #N done" with the first line of the closing summary.
  Other liaison reports to you notify too, once per `--ref`. Tasks, sub-team goals and friction
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
  from a payload); a reading dated in the future shows `unknown`; and the rest of status stays
  usable whatever the snapshot holds.

### Documentation

- **README, architecture, examples and the site caught up (#124, rc5).** The README lists what
  0.12.0 to 0.15.0 added, with links into the user guide, and a first-upgrade path and `xt version
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

- From 0.14.1: `git pull upstream main` (or `xt version use v0.15.0-rc5 --candidate`), then `xt restart --all`
  so agents get the new protocol and roles, and the supervisor the goal notifications. Scripts or
  roles that rely on `xt log` printing everything need `--full`. For Claude plan usage, add the
  `statusLine` entry to one Claude agent's settings file (yours to edit) and restart that agent.
  From an earlier 0.15.0 candidate: the same restart. "Done since you last looked" starts empty
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
