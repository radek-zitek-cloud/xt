# Goals in practice

Part one: three real goals, word for word, as they were sent to xt teams in September 2026. Part
two: [configurations and questions to copy](#part-two-copy-and-adapt), written for this page.

Together the three goals
show what the [story](story.md) means by "write outcomes, not steps": what a goal looks like, how
a team reads it, and how a plain-language goal fixes a rule the team followed too faithfully.

Each goal was typed into the team's **liaison** by Claude on Radek's behalf, which is why they
start with "From Claude, on Radek's behalf". The liaison turned each into a goal brief for the
**lead**, which planned the work and ran the team. Two details were redacted: a local file path
and an internal board id.

- [1. Hire a scout](#1-hire-a-scout-the-newsroom-finds-its-own-stories): outcomes only; the
  team designed the solution
- [2. Correct the auto-pick rule](#2-correct-the-auto-pick-rule-fixing-what-the-team-did-exactly-right):
  fixing a rule the team followed exactly
- [3. Set up the xt product team](#3-set-up-the-xt-product-team-a-team-with-a-working-method):
  a new team, with a working method passed on as part of the goal
- [4. A Claude Code agent with a permissions file](#4-a-claude-code-agent-with-a-permissions-file):
  settings to copy (part two)
- [5. A decision question with options](#5-a-decision-question-with-options): what the liaison
  sends and what you see (part two)

## 1. Hire a scout: the newsroom finds its own stories

**Context.** A newsroom team of six agents (a lead, a researcher, an author, an editor and a
publisher, plus the liaison) had so far written articles on request. This goal asked it to find
its own stories from news feeds, without the human in the loop for every choice.

**What to notice.** The goal says *what* the scout must achieve (never re-evaluate a seen item,
survive losing its memory, stay cheap) and explicitly leaves the design to the team: "How to
achieve this is the team's design." It also states the no-answer policy (auto-pick) and its
limits (quiet hours, a daily cap), and says when the goal is done, so it doesn't stay open
forever.

```
From Claude, on Radek's behalf. Radek authorized this goal and approves dispatching it to the lead without a read-back. Please pass it on in full, including the feed list.

Goal: make the newsroom find its own stories. Hire a scout that checks news feeds every hour and proposes topics; the newsroom writes and publishes the ones picked.

The scout
- A new agent, `scout`, reporting to the lead. Its only job is finding and ranking topics; it never writes articles.
- Woken every 60 minutes by an xt schedule (`xt schedule`). The spawn and the schedule both need Radek's approval; ask for them the usual way.
- Sources: these RSS feeds only. No scraping of web pages; the researchers still open the articles when they work a topic.
  - ČTK: https://www.ceskenoviny.cz/sluzby/rss/zpravy.php
  - ČT24: https://ct24.ceskatelevize.cz/rss/hlavni-zpravy
  - iROZHLAS: https://www.irozhlas.cz/rss/irozhlas
  - BBC World: https://feeds.bbci.co.uk/news/world/rss.xml
  - Euronews: https://www.euronews.com/rss
  - ECB press releases: https://www.ecb.europa.eu/rss/press.html
  - ČNB press releases: https://www.cnb.cz/cs/.content/rss-feed/rss-feed_tz.rss
  - Ars Technica: https://feeds.arstechnica.com/arstechnica/index
  - Hacker News: https://news.ycombinator.com/rss
- Only new or changed items: the scout must never re-evaluate a feed item it has already seen, only new items and ones that changed. This must survive the scout losing its memory (restart, context reset), and each hourly run must stay cheap. It also keeps track of topics already proposed or covered, and raises one again only for a real new development, marked as an update. How to achieve this is the team's design.
- Fetching feeds needs network access, so an escalation. Justify it honestly (reading the team's news feeds); if one is refused or waits for Radek, report it; don't get around it.
- If a run finds nothing worth proposing, it says so in one line and stops.

Batches and picking
- Each run with something worth writing sends the lead a batch of 2–3 ranked topics: headline, why it matters, source items, suggested language. The lead forwards it to the liaison, which asks Radek to pick.
- If Radek hasn't picked from a batch by the time the next batch arrives, the lead picks the top topic of the new batch itself and the newsroom writes it. Topics from the unpicked batch are dropped, not queued.
- A pick by Radek always wins, whenever it comes.

Writing
- Czech topics are written in Czech, everything else in English. Balanced, general public, about 500 words, through the newsroom's usual workflow (skills/article-workflow/SKILL.md): research → author → editor → publisher, including publishing to SilverBullet.
- Two researchers can work in parallel, so a picked topic doesn't wait behind another one. Hiring the second researcher needs Radek's approval too.

Limits
- No scout runs between 21:00 and 05:00 (xt still wakes the scout hourly; at night it answers "quiet hours" in one line and stops).
- At most 6 auto-picked articles a day; after that, only Radek's picks.

Done when: the scout is hired, scheduled, and its first run has worked (a batch reached Radek, or a one-line "nothing worth proposing"), and the lead reports how the scout avoids re-reading seen items (what it built, where it keeps state). Then close this goal. From then on the scout runs on its schedule, and each picked topic (Radek's or auto-picked) becomes its own task.
```

**What happened.** In about three minutes the lead wrote the scout's role, a skill and a small
feed scanner: it keeps a fingerprint of every item it has seen, skips feeds that haven't changed
(HTTP cache headers), and marks a batch as seen only after it has been delivered, so a crash loses
nothing. That was a better design than the one we had in mind. The first run read 251 items and
proposed three topics; the next hourly run read only the 19 new ones. The human picked a topic,
and the article was published 19 minutes after the goal was sent. Hiring the scout, a second
researcher and the hourly schedule each waited for the human's approval.

## 2. Correct the auto-pick rule: fixing what the team did exactly right

**Context.** Goal 1 said: if the human hasn't picked when the next batch arrives, "the lead picks
the top topic of the new batch". The lead did exactly that, and also sent the same new batch to
the human to decide, so the human's choice would have come after the writing started, and the
batch he'd had a full hour to consider was thrown away. The mistake was in the goal, not in the
team.

**What to notice.** The correction explains *why* the old rule was wrong, gives the new rule in
full, says what to do right now with the work in progress, and says where the rule must be written
down so it outlives the goal (the lead's notes and the scout's skill, not the goal brief).

```
From Claude, on Radek's behalf. Radek authorized this goal and approves dispatching it to the lead without a read-back. Please pass it on in full.

Goal: correct the standing auto-pick rule for scout batches. The current rule (goal #161's brief: "the lead picks the top topic of the new batch") is wrong: it auto-picks from the batch that was just sent to Radek, so his choice from that batch comes after writing has started, and the batch he had a whole hour to decide on is thrown away.

Correct rule, replacing the old one from now on:
- Every batch goes to Radek for a decision, as now.
- When a new batch arrives and the previous batch is still unpicked, the lead auto-picks the top topic of the PREVIOUS batch, and the new batch goes to Radek for his decision. Every batch gets an hour for Radek, then an auto-pick if he didn't choose.
- Skip a topic that has gone stale or is already covered or in progress, and take the next one from the same batch. If none is still worth writing, no auto-pick.
- A pick by Radek always wins, whenever it arrives. The limit of six auto-picks a day stays.

Right now: let the RAF Fairford article (#202) finish; it counts as today's first auto-pick. The 16:36 batch is Radek's to decide. If he hasn't picked when the 17:36 batch arrives, auto-pick from the 16:36 batch under the new rule (Fairford is already covered, so the next topic).

Where the rule lives: this is a standing duty, so write it into members/lead/notes.md and wherever the scout workflow is described (skills/rss-scout/SKILL.md or roles/scout.md), not only in a goal brief. The scout's wake message currently points at goals/scheduled-story-scout.md; point it at the scout's skill or role instead (that change is a schedule change, so it will need Radek's approval).

Liaison: tell Radek in plain words that the 16:36 batch is open for him to pick (topics 2 and 3; topic 1 is already being written).

Done when: the rule is written in those files, the wake message points at the skill or role, and the lead reports the changed lines.
```

**What happened.** About a minute later the lead reported the rule rewritten in its notes, the
scout's skill and the scout's role, and asked to point the scout's hourly wake-up message at the
skill instead of the old goal (a schedule change, so it waited for the human's approval). At the
next batch it auto-picked from the previous, unanswered one, as intended. When the human later
answered a batch with "none", the lead recorded it as a decision; a one-line follow-up goal made
that explicit too: a pass is a decision, never overridden by an auto-pick.

## 3. Set up the xt product team: a team with a working method

**Context.** A new team, whose job is product management for xt itself: the backlog on a Kanban
board (Fizzy), specs, research, documentation and release notes in a public wiki (SilverBullet).
It never touches the code or any machine; Radek and Claude build what it specifies.

**What to notice.** Most of the goal is a *working method*: who decides (the human is the product
owner), what "ready" and "done" mean, how items are ordered and sized. A lead can't guess a
discipline the human wants followed, so it's passed on as part of the goal. The board's design is
left to the team, within three constraints, one of them a single approval point that only the
human can move work past. Because the wiki is public, the goal says what must never appear in it.
Tool quirks the team would otherwise stumble on (a token the sandbox can't reach) are stated up
front.

```
From Claude, on Radek's behalf. Radek authorized this goal and approves dispatching it to the lead
without a read-back. Please pass it on in full: the working method below is part of the goal.

GOAL: SET UP THE XT PRODUCT TEAM

Purpose. This team runs product management for xt (https://github.com/radek-zitek-cloud/xt, the
tool this team itself runs on): backlog, discovery and specs, research, documentation, release
notes and, later, QA. The team never changes xt's code, its repo or any machine; Radek and Claude
build what the team specifies. Radek is the product owner.

Tools
- Fizzy board "xt Board" (id <board id>), via the `fizzy` CLI. Its token is in the
  system keyring, which your sandbox cannot reach: every fizzy command needs an escalation, even
  read-only ones ("auth_required" inside the sandbox means exactly that, not a missing token).
- SilverBullet space "xt Space", via the user's `silverbullet` skill with `--space xt`. It needs
  the network, so escalate too. Follow the skill's rules: plain Markdown, one line per paragraph,
  paths end in `.md`, links as wikilinks, read before you rewrite, never --force.
- Justify escalations honestly. No secrets on cards or pages.

Public. xt Space is public: anyone on the internet can read it, and it is linked from xt's
README. Write every page, card and comment for an outside reader. Never include personal
information, local paths (/home/...), hostnames or machine names, anything about other teams or
systems beyond xt itself, or secrets. When you migrate the backlog, rewrite each note for that
reader instead of copying it (the source mentions internal runs, paths and other teams).

Working method (the PM's discipline; put it in the PM's role and the skills)
- Roles. Radek is the product owner: he decides what gets built and in which order, approves
  items as ready, and accepts them as done. The PM runs the backlog for him: collects, clarifies,
  sizes and orders items, and proposes; it doesn't decide. Radek and Claude are the delivery team.
- Discovery before delivery. Discovery answers "is this worth doing, and what exactly?" and ends
  in a spec page; delivery is building it.
- Definition of Ready: a clear problem, acceptance criteria ("done when…"), a size, a linked spec
  when it's more than trivial, and Radek's approval. Definition of Done: built, tested, documented
  (user guide and changelog), released.
- One ordered list: the top is what comes next. Order by value against size (impact, confidence,
  size); keep it simple. The PM proposes the order, Radek confirms it.
- Item types as tags: feature, bug, chore, docs, research, idea. Size 0-9 as a tag `size:N`
  (0 trivial, 9 massive change). Velocity = the sum of sizes of cards closed per week.
- Discussions go on the cards as comments, so the reasoning stays with the item. Every spec page
  links to its card and every card to its page.
- Fizzy moves cards untouched for 30 days to "Not now". Fine for ideas; make sure it never
  buries a committed item (use golden cards for the committed top of the list).

What to build
1. The board. Design the columns yourselves, within these constraints: discovery and delivery
   are visibly separate; there is one approval point that only Radek moves cards past (nothing is
   built before it); the number of cards being built at once is limited. Create the columns and
   tags on xt Board. Write the conventions as skill `skills/xt-board/SKILL.md` (columns and what
   each means, tags, card template, who moves what, "search before you create").
2. The space. Structure xt Space with an index and sections for specs, research, docs, releases
   and planning notes, with page templates. Write the conventions as skill `skills/xt-space/SKILL.md`.
3. Hire a product manager (only the PM for now; more roles later, each with Radek's approval).
   Its role describes the working method above.
4. Product direction. As its first step, the PM proposes a one-line product direction ("xt is
   for …, not for …") and asks Radek to confirm it.
5. Migrate the backlog from the project's backlog file (backlog.md in the lab repo) (read it; don't edit it): one
   card per item, keeping its number in the title (e.g. "#30 Harness coverage…"), its size, type
   and notes (rewritten for the public, see above). Open items go in the right columns; done
   items go in as closed cards so velocity history is kept; watching and decided items as closed
   cards with a note. The migration is checked by Radek before the board becomes the backlog;
   until then backlog.md stays the truth.
6. Propose a rhythm for Radek's approval (schedules need it): daily triage of new cards; a
   weekly planning note as a page in xt Space (proposed order, what's ready, velocity, stale
   items), announced to Radek with its link through the liaison; a check when a new xt release
   tag appears. Use quiet hours (--between) for anything scheduled.

Done when: the columns and tags exist; both skills are written; the PM is hired; the product
direction is proposed to Radek; the migration is done and reported with counts (open, done,
closed) for Radek to check; the rhythm is proposed.
```

**What happened.** The goal was sent at 21:30. Within a minute the lead had written the
product manager's role and both conventions and asked to hire the PM; after Radek's approval the PM
built the board (five columns, among them one approval point only Radek can pass and a column
where finished work waits for his acceptance) and the public space's structure, and proposed the
product direction, which Radek confirmed. At 21:41 the backlog was migrated: 36 items, 10 open and
26 closed as history, every note rewritten for outside readers (none of the 36 cards mentions a
local path, a machine or another team). Radek checked it a minute later, and the board became
xt's backlog. The PM also proposed a working rhythm (a daily wake-up between 09:00 and 17:00 to
triage new cards and check for releases, and a weekly planning note), which Radek approved.

Two things went less smoothly, and both became cards on the board: the PM checked the board's
display in Radek's own browser with a computer-use tool (read-only, but outside xt's rules; the
team now uses command-line tools only), and the lead asked the PM for the product direction
twice, so the liaison had to withdraw its first question and ask again with the final wording.

## Part two: copy and adapt

These are written for this page, not taken from a run. They follow the setup of xt's own
product team (from 0.15.0); adjust names, paths and rules to your team.

## 4. A Claude Code agent with a permissions file

**Context.** A Claude Code agent nobody watches must never stop at a permission prompt, and must
never do more than its role needs. Give it a settings file in the team repo. Settings files are
yours, like `team.toml`: agents never edit them.

`settings/researcher.json`:

```json
{
  "permissions": {
    "defaultMode": "dontAsk",
    "allow": [
      "Bash(/path/to/team/bin/xt *)",
      "Bash(rg *)",
      "Bash(cat *)",
      "Bash(git status *)",
      "Bash(git log *)",
      "Edit(members/researcher/**)",
      "Read"
    ],
    "deny": [
      "Bash(git push *)",
      "Bash(curl *)",
      "Bash(rm *)",
      "Edit(settings/**)",
      "Edit(team.toml)",
      "WebFetch"
    ]
  },
  "statusLine": {"type": "command", "command": "/path/to/team/bin/xt-statusline"}
}
```

- `dontAsk` refuses anything not on the `allow` list at once, instead of waiting at a prompt
  nobody sees. `deny` wins over `allow`.
- The `xt` rule uses the team's absolute path, as in the agent's first prompt.
- `statusLine` is optional: it shows the Claude plan's usage in `xt status` (one agent is enough).

The lead asks for the hire with the file (the approval names it and its mode; without one, it
warns that the agent would start with your own Claude defaults):

```sh
xt spawn researcher --harness claude --model claude-sonnet-5-5 --role researcher \
  --permissions settings/researcher.json --as lead
```

After your approval, the agent's entry in `team.toml` has the line (you can also add it by hand):

```toml
[[agent]]
name = "researcher"
role = "researcher"
harness = "claude"
model = "claude-sonnet-5-5"
permissions = "settings/researcher.json"
reports_to = "lead"
status = "active"
```

xt checks the file before every start (missing, not JSON, an unknown `defaultMode` or a malformed
rule refuses the start) and the start note shows its path, a hash of its content and the mode. To
give every Claude agent the same file, set it once under `[defaults]`: `permissions =
"settings/claude-agents.json"`. See the [user guide](user-guide.md#11-memory-and-recovery).

## 5. A decision question with options

**Context.** When the team needs a decision only you can make, the liaison asks it through xt as
one self-contained sentence with two or three options, each with what follows from it, and one
recommendation.

What the liaison sends:

```sh
xt send human --as liaison --type ask --ref 212 \
  --option "Publish the digest today :: readers get it on time; the last section is unreviewed" \
  --option "Publish tomorrow :: fully reviewed, one day late" \
  --recommend 2 <<'XT_END'
Should the weekly digest go out today or tomorrow?
XT_END
```

What you see in the Inbox (TUI and `xt inbox`), with a desktop notification:

```text
Should the weekly digest go out today or tomorrow?

Options:
1. Publish the digest today — readers get it on time; the last section is unreviewed
2. Publish tomorrow — fully reviewed, one day late
Recommended: 2
Or answer in your own words.
```

Answer with the number (`xt answer 230 2`, or in the TUI `s` on it, `2`, ctrl+s), and the log records
"Option 2: Publish tomorrow — fully reviewed, one day late", so it says what you chose. Your own
words work too. xt refuses a question with fewer than two or more than three options, an option
without ` :: ` and its consequence, or no single recommendation. See
[`xt answer`](user-guide.md#xt-answer).

## 6. Reset heavy agents automatically

**Context.** Every turn re-reads an agent's whole context, so a long-running agent gets more
expensive by the hour. The automatic reset policy (off by default) gives an idle agent without open
work a fresh context once it's above a size in tokens, through the same checkpoint as `xt reset`.

In `team.toml` (yours to edit; agents never do), turn it on for the team:

```toml
[policy]
auto_reset = true                 # default false: nothing resets on its own
auto_reset_tokens = 150000        # the threshold in tokens, whatever the agent's window
auto_reset_cooldown_hours = 6     # at most one reset per agent in this many hours
```

Then give one agent a higher threshold, and exempt another that is in the middle of long, delicate
work:

```toml
[[agent]]
name = "builder"
role = "builder"
harness = "claude"
reports_to = "lead"
status = "active"
auto_reset_tokens = 250000        # this agent's own threshold

[[agent]]
name = "analyst"
role = "analyst"
harness = "claude"
reports_to = "lead"
status = "active"
auto_reset_tokens = "off"         # never reset automatically
```

The supervisor reads `team.toml` on every tick, so no restart is needed. An agent is reset only
when it's idle, owns no open goal or task, has no messages waiting, its context reading is from the
last 2 hours and above its threshold, and no reset ran for it in the cool-down. While it waits,
`xt status` shows `reset queued (by xt's reset policy at 14:02): …`, and the log says why:

```text
reset of builder queued by xt's reset policy (context 262000 tokens, above the threshold of 250000
tokens; policy auto_reset): the supervisor runs it when builder is idle with no open work
```

`xt reset builder --cancel` removes a queued one (the cool-down then applies). The trade-off: a fresh
context costs a turn re-reading the first prompt, the brief and the agent's notes, and whatever
isn't in its notes is gone. See the [user guide](user-guide.md#8-pausing-and-resuming-the-team).

## 7. Network for one Codex agent

**Context.** Every Codex agent runs in Codex's sandbox without network. A quality analyst that runs
the project's test suite and `uv run` in its own clean clone needs packages and local sockets that
the sandbox refuses. Give that one agent network, and nobody else (from 0.19.0).

In `team.toml` (yours to edit; agents never do):

```toml
[[agent]]
name = "qa"
role = "quality-analyst"
harness = "codex"
reports_to = "lead"
status = "active"
codex_options = ["sandbox_workspace_write.network_access=true"]
```

Then `xt restart qa`: options apply at the next start. xt passes the option as
`-c sandbox_workspace_write.network_access=true`, and the start note, `xt status`, the brief and the
agent's detail show `codex options: sandbox_workspace_write.network_access=true (network on: it can
reach any host)`.

**Running the suite in the clean clone.** Network alone isn't enough for `uv run`: Codex's sandbox
keeps uv's default cache under the home directory read-only. Point the cache into the clone:

```sh
git clone --branch vX.Y.Z-rcN /path/to/the/builders/clone /tmp/qa-check
cd /tmp/qa-check
UV_CACHE_DIR=/tmp/qa-check/.uv-cache uv run pytest -q
```

On the operator's check of 0.19.0-rc1 this passed (532 tests in about 90 s) without an
escalation; with network on but the default cache, `uv run` failed. xt adds no option for the
cache path: the network switch is the only one (a decision for this release).

- Codex opens the network wholesale: the agent can reach any host, not just a package index.
  Give it only to an agent whose workspace holds no credentials (here a clean clone). xt doesn't
  check that; it's your rule.
- xt accepts only the network switch (`=true` or `=false`). Any other key or value refuses the
  agent's start and names what is allowed, because Codex may silently accept a key it doesn't know.
- An agent without the line runs as before, with no network. See the
  [user guide](user-guide.md#11-memory-and-recovery).

## 8. Tell the lead when a card is Ready to build

**Context.** You approve work by moving its card on the Board into Ready to build, and the lead
should start on it without a message from you. The board watch runs a command you name and tells
the lead about each card that enters the column (from 0.19.0). Here the Board is Fizzy, with its
command-line client `fizzy`.

Find the board's and the column's IDs once, in your own terminal:

```sh
fizzy column list --board BOARD_ID --jq '[.data[] | {id,name}]'
```

Then in `team.toml` (yours to edit; agents never do):

```toml
[board_watch]
command = ["fizzy", "card", "list", "--board", "BOARD_ID", "--column", "COLUMN_ID", "--all", "--jq", "[.data[] | {number, title}]"]
interval = "5m"
timeout = "30s"
column = "Ready to build"
```

The `--jq` projection makes Fizzy print exactly the contract: a JSON array of `{number, title}`.

**Run it once by hand first** and check it lists the cards you expect in Ready to build:

```sh
fizzy card list --board BOARD_ID --column COLUMN_ID --all --jq '[.data[] | {number, title}]'
```

A wrong column id isn't an error to Fizzy: it prints `[]` and exits 0, so the watch would report
`0 card(s) in the column` without an alert and never tell the lead. After the first run, the count
in `xt status` (`board watch: last success … (N card(s) in the column)`) should match what you saw.
The supervisor picks the section up on its next tick. Its first run records the cards already in
the column; after that, moving card 129 there gives the lead:

```text
Card 129 (Work outline) is now in Ready to build (seen by the board watch)
```

- Fizzy reads its token from your keyring. The command runs in the supervisor's environment (the
  pane of the team's Herdr session), so run the `fizzy column list` above in a new pane of that
  session first: if it prints the columns, the watch can reach the keyring too.
- If the command fails (Fizzy down, the token expired), one `boardwatch` alert says why (Fizzy's
  error JSON from its standard output, when its error output is empty) and clears at the next
  success; cards that entered meanwhile are reported then.
- Any other board works the same way: a command, or a small script, that prints the array.

## 9. Let your own coding agent run a staging check

**Context.** You use your own coding-agent session (here Claude Code, in a terminal outside the
team) to help with a staging check. It should be able to report to the liaison and restart agents
while you're away from the keyboard, but never act as you, never take the team down and never answer
or approve anything (from 0.19.0).

In the operator's session, ask it to run:

```sh
/path/to/team/bin/xt operator pid
# 48213 (claude): give the human this pid for `xt operator add NAME --pid 48213`
```

In **your own terminal**, register it under a name and give it a grant:

```sh
xt operator add helper --pid 48213      # writes .xt/operators/helper.token (readable by you only)
xt delegate helper --for 45m            # restart, reset, spawn, up; at most 60m, 30m by default
```

The operator's commands then carry the token and its name. A report to the liaison:

```sh
XT_OPERATOR_TOKEN=$(cat /path/to/team/.xt/operators/helper.token) \
  /path/to/team/bin/xt send liaison --as helper --type report <<'XT_END'
Staging check of 0.19.0-rc2: steps 1-9 pass; step 10 waits for a lead restart.
XT_END
```

and, under the grant, a restart:

```sh
XT_OPERATOR_TOKEN=$(cat /path/to/team/.xt/operators/helper.token) \
  /path/to/team/bin/xt restart lead --as helper
```

The log records it as `helper, delegated by human until 15:30: xt restart lead`, and the report
arrives at the liaison from `helper`, marked `(sent by helper, an operator, on the human's
behalf)`. When the check is done:

```sh
xt delegate --revoke                    # or let it expire
```

- **Never delegated:** `xt down`, `xt restart --all`, answers, approvals, `xt version use` and
  `rollback`, `xt operator add` and `xt delegate`. They stay yours, grant or no grant, and `--as
  human` keeps working only from your own terminal.
- Both the token and the registered process are needed: the token copied into another shell, or the
  operator's process without the token, is refused. A new operator session needs a new `xt
  operator add`.
- `xt status` and the TUI's Team header show the grant and its end time while it lasts. See the
  [user guide](user-guide.md#13-an-operator-acting-for-you).
