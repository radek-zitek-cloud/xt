# Goals in practice

Part one: three real goals, word for word, as they were sent to xt teams in September 2026, with
what the team did. Part two: [flows and configurations to copy](#part-two-copy-and-adapt), written
for this page and labelled **runnable** or **illustrative**.

Together the three goals
show what the [story](story.md) means by "write outcomes, not steps": what a goal looks like, how
a team reads it, and how a plain-language goal fixes a rule the team followed too faithfully.

Each goal was typed into the team's **liaison** by Claude on Radek's behalf, which is why they
start with "From Claude, on Radek's behalf". The liaison turned each into a goal brief for the
**lead**, which planned the work and ran the team. Two details were redacted: a local file path
and an internal board id. They are records of what happened then: today you would give the same
goal in `xt chat` (see 4).

- [1. Hire a scout](#1-hire-a-scout-the-newsroom-finds-its-own-stories): outcomes only; the
  team designed the solution
- [2. Correct the auto-pick rule](#2-correct-the-auto-pick-rule-fixing-what-the-team-did-exactly-right):
  fixing a rule the team followed exactly
- [3. Set up the xt product team](#3-set-up-the-xt-product-team-a-team-with-a-working-method):
  a new team, with a working method passed on as part of the goal
- Part two: [4. a goal with read-back](#4-a-goal-with-read-back-in-chat) ·
  [5. a question with options](#5-a-question-with-options) ·
  [6. a hire waiting for your yes](#6-a-hire-waiting-for-your-yes) ·
  [7. a drive grant](#7-hand-your-coding-agent-the-wheel-for-half-an-hour) ·
  [8. a capability block](#8-a-teamtoml-with-a-capability-block) ·
  [9. network for one Codex agent](#9-network-for-one-codex-agent) ·
  [10. automatic resets](#10-reset-heavy-agents-automatically) ·
  [11. the board watch](#11-tell-the-lead-when-a-card-is-ready-to-build) ·
  [12. an operator's staging check](#12-let-your-own-coding-agent-run-a-staging-check) ·
  [13. a chat session](#13-a-chat-session-an-operator-the-pane-and-a-question)

## 1. Hire a scout: the newsroom finds its own stories

*Illustrative: a record of a real run, word for word.*

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

*Illustrative: a record of a real run, word for word.*

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

*Illustrative: a record of a real run, word for word.*

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

These are written for this page, not taken from a run; adjust names, paths and rules to your team.
Each is labelled:

- **Runnable**: run it yourself as shown, in a throwaway team: a fresh checkout of xt with `herdr`
  and `git` installed, set up with `./bin/xt init --yes --name example --session example` (it
  needs no running Herdr session for these). The expected output is shown.
- **Illustrative**: shown to explain, not to run as is, because it needs a running team or your
  own authority (an answer, an approval, a grant). The commands and flags are real.

## 4. A goal with read-back, in chat

*Illustrative: it needs a running liaison.*

**Context.** You want something done and talk it through with the liaison in `xt chat`. The
liaison drafts the goal in `goals/drafts/`, then reads it back to you as a yes/no question before
it goes to the lead: nothing is dispatched on a misunderstanding.

In **your own terminal**, `xt chat`, then type what you want and press `enter`. A few turns later
chat shows, at 80 columns:

```text
xt chat with liaison (claude) · pane input recorded
12:00 you  #4
I'd like a short digest of what the team shipped each week, ready on Friday
morning.

12:00 liaison  #5  ⚑ yes/no
Here is the goal as I'd send it to the lead:
Outcome: every Friday by 09:00, digests/<year>-<week>.md lists the week's merged
work, one line each, with links.
Done when: the first digest is written and the weekly schedule is approved.

Dispatch it as written?

Answer yes or no.
⚑ waits for your answer: tab picks it
```

Press `tab`: the question opens above the input line, which reads `answer #5 ›`. Type `yes` and
press `enter`; chat confirms `#6 answer to #5 → liaison: …` and the question shows `✓ answered #6:
yes`. `no` instead, and the liaison asks what to change. Your yes doesn't dispatch the goal by
itself: the liaison does, with `xt goal dispatch`, and chat shows it as a dimmed line
(`12:01 to lead: goal #7 …`). When the goal closes you get one notification.

- What makes a good goal: the outcome, constraints, and when it's done; leave the how to the team.
  Part one has three real ones.
- The same question waits in the TUI's Inbox (`s` on it, then `y`), and `xt answer 5 yes` answers
  it from any terminal of yours. A `yes` typed into the liaison's own pane doesn't: pane text is
  unverified (see 13).
- See the [user guide](user-guide.md#3-giving-the-team-a-goal).

## 5. A question with options

*Illustrative: the liaison sends it, and only you answer it.*

**Context.** When the team needs a decision only you can make, the liaison asks it through xt as
one self-contained sentence with two to four options, each with what follows from it, and one
recommendation; `--other` lets you answer in your own words as well.

What the liaison sends:

```sh
xt send human --as liaison --type ask --ref 212 \
  --option "Publish the digest today :: readers get it on time; the last section is unreviewed" \
  --option "Publish tomorrow :: fully reviewed, one day late" \
  --recommend 2 --other <<'XT_END'
Should the weekly digest go out today or tomorrow?
XT_END
```

What you see in chat and the Inbox (TUI and `xt inbox`), with a desktop notification:

```text
Should the weekly digest go out today or tomorrow?

Options:
1. Publish the digest today — readers get it on time; the last section is unreviewed
2. Publish tomorrow — fully reviewed, one day late
Recommended: 2
Other: answer in your own words.
```

Answer with the number (`tab` in chat, then `2`; `xt answer 230 2`; or in the TUI `s` on it, `2`,
ctrl+s), and the log records "Option 2: Publish tomorrow — fully reviewed, one day late", so it says
what you chose. Your own words work because the question has `--other`; without it, xt accepts only
an option's number. A yes/no question is `--closed` instead of options (`xt answer 231 yes`). xt
refuses a question with fewer than two or more than four options, an empty option or one without
` :: ` and its consequence, no single recommendation, or `--other` on a closed question, and shows
your text back so nothing is lost. See [`xt answer`](user-guide.md#xt-answer).

## 6. A hire waiting for your yes

*Illustrative: the lead asks, and only you approve.*

**Context.** The lead decides it needs a writer. It writes `roles/writer.md` and asks to hire one;
every agent turn costs money, so the hire waits for you.

What the lead runs, and what xt answers it:

```sh
xt spawn writer --harness claude --role writer --as lead
# approval #6 requested from the human; you'll get a message when it's decided
```

What you see in chat at 80 columns (the TUI's Inbox shows `⚑ #6 spawn writer (writer,
claude/default)  yes/no`, with a desktop notification):

```text
12:00 xt  #6  ⚑ yes/no
lead asks to spawn writer as writer on claude, reporting to lead.
Approve its start: write enforced; network advisory (role text only).

Answer yes or no: xt answer 6 yes|no (or s, then y / n on it in the TUI's
Inbox). xt approve 6 and xt deny 6 (a / d) still work.
⚑ waits for your answer: tab picks it
```

The sentence says what the agent may do and which of it its harness can only keep advisory. Here
the writer inherits the `[defaults.capabilities]` block `xt init` wrote: Claude Code enforces its
`write` list, and network stays advisory. In a team without any block the request starts with a
warning instead: `writer would start without generated settings, so the operator's own claude
defaults apply`. Answer `yes` (`tab` in chat, or
`xt answer 6 yes`): `#6: spawned writer in workspace …`, and the lead hears it. `no` denies it.

## 7. Hand your coding agent the wheel for half an hour

*Illustrative: it needs a registered operator (see 12) and your grant.*

**Context.** You use your own coding-agent session, registered as the operator `helper` (see 12),
and you're away from the keyboard for half an hour: the team shouldn't wait on you, so the operator
answers your questions, decides approvals and gives the liaison its next goal. In **your own
terminal**:

```sh
xt delegate helper --for 30m --scope drive   # replaces any other grant; at most 60m
```

The operator finds what waits for you, whole (text, answer type, options, recommendation):

```sh
XT_OPERATOR_TOKEN=$(cat /path/to/team/.xt/operators/helper.token) \
  /path/to/team/bin/xt inbox --questions
```

and answers it, approves a hire, and gives a goal, each with the token and `--as helper`:

```sh
xt answer 1290 2 --as helper            # recorded as "Option 2: …", checked like your answer
xt answer 1291 yes --as helper          # approves hire #1291
xt send liaison --as helper --type goal <<'XT_END'
After the digest: draft next week's reading list from the scout's stories.
XT_END
```

Each lands under `helper`, never `human`, ending in `(helper, delegated by human until 15:30: an
operator acting on the human's behalf)`, and shows in your Inbox and in chat. Back at the
keyboard, answering #1290 yourself shows what was decided: `#1290 already answered by helper
(operator, delegated by you until 15:30): "Option 2: …" — nothing sent.` At 15:30 the log says
`drive grant for helper ended 15:30`, and the operator's next answer is refused; `xt delegate
--revoke` ends it sooner.

- A drive grant doesn't run `restart` or `spawn`; grant those separately when you need them (the new
  grant replaces drive).
- `xt down`, `xt restart --all`, version switches and granting stay yours, grant or no grant. See
  the [user guide](user-guide.md#15-an-operator-acting-for-you).

## 8. A team.toml with a capability block

*Runnable: in a throwaway team (see above).*

**Context.** A Claude Code agent nobody watches must never stop at a permission prompt, and must
never do more than its role needs. Give it a capability block in `team.toml`: xt turns it into a
Claude Code settings file (`dontAsk`: anything not allowed is refused at once instead of waiting).
`team.toml` and settings files are yours: agents never edit them.

Add this to the end of `team.toml`:

```toml
[[agent]]
name = "researcher"
role = "researcher"
harness = "claude"
model = "claude-sonnet-5-5"
reports_to = "lead"
status = "active"
[agent.capabilities]
commands = ["rg", "cat", "git status", "git log"]
extras = "settings/researcher.json"
```

and write `settings/researcher.json`, for what the block can't say:

```json
{
  "permissions": {
    "deny": ["Bash(git push *)", "Bash(curl *)", "Bash(rm *)"]
  },
  "statusLine": {"type": "command", "command": "/path/to/team/bin/xt-statusline"}
}
```

Check that xt reads it: any command that loads the team does, and `./bin/xt goal list` changes
nothing:

```text
Drafts:
  (none)
Open goals:
  (none)
```

A mistake is refused at load, naming it. Write `netwerk = "on"` in the block, and the same command
prints, on standard error:

```text
xt: agent researcher's capabilities.netwerk in team.toml isn't a capability (write, deny, commands, network, connectors, skills, credential_clis, and require and extras)
```

- Its own notes, `team.toml`, `settings/`, network off and the credential CLIs need no line: they
  are the defaults. xt itself is always allowed.
- `commands` is the shell commands it may run; everything else is refused.
- `extras` puts the file on top of the generated settings, where it may only restrict: a rule that
  would loosen the block refuses the start, naming the rule. Without anything left to say, leave
  `extras` out.
- `statusLine` is optional: it shows the Claude plan's usage in `xt status` (one agent is enough).

In a running team, `xt spawn researcher` then starts it (or the lead's request asks for your
approval, which shows what it may do in one sentence, as in 6). The start note names the file and a
hash of its content, and `xt status` shows the agent's `caps:` row. See the
[user guide](user-guide.md#13-what-agents-may-do-capabilities).

## 9. Network for one Codex agent

*Illustrative: it needs a running Codex agent.*

**Context.** Codex agents work in Codex's sandbox without network. A quality analyst that runs the
project's test suite and `uv run` in its own clean clone needs packages and local sockets that the
sandbox refuses. Give that one agent network, and nobody else.

In `team.toml` (yours to edit; agents never do), a block that also lets the sandbox write the
clean clone:

```toml
[[agent]]
name = "qa"
role = "quality-analyst"
harness = "codex"
reports_to = "lead"
status = "active"
[agent.capabilities]
network = "on"
write = ["/tmp/qa-check"]          # passed to Codex as --add-dir /tmp/qa-check
```

Then `xt restart qa`: the block applies at the next start. Codex enforces `network` (its sandbox);
its other capabilities show `advisory` in the row.

**Running the suite in the clean clone.** Network alone isn't enough for `uv run`: Codex's sandbox
keeps uv's default cache under the home directory read-only. Point the cache into the clone:

```sh
git clone --branch vX.Y.Z-rcN /path/to/the/builders/clone /tmp/qa-check
cd /tmp/qa-check
UV_CACHE_DIR=/tmp/qa-check/.uv-cache uv run pytest -q
```

When the operator first checked this (with the same network switch the block sets), the suite
passed this way without an escalation; with network on but the default cache, `uv run` failed. xt
adds no option for the cache path.

- Codex opens the network wholesale: the agent can reach any host, not just a package index.
  Give it only to an agent whose workspace holds no credentials (here a clean clone). xt doesn't
  check that; it's your rule.
- See the [user guide](user-guide.md#13-what-agents-may-do-capabilities).

## 10. Reset heavy agents automatically

*Illustrative: it needs running agents with a context to measure.*

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
isn't in its notes is gone. See the [user guide](user-guide.md#9-pausing-resuming-and-resetting).

## 11. Tell the lead when a card is Ready to build

*Illustrative: it needs your board tool and its token.*

**Context.** You approve work by moving its card on the Board into Ready to build, and the lead
should start on it without a message from you. The board watch runs a command you name and tells
the lead about each card that enters the column. Here the Board is Fizzy, with its command-line
client `fizzy`.

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

## 12. Let your own coding agent run a staging check

*Illustrative: it needs a running team and your grant.*

**Context.** You use your own coding-agent session (here Claude Code, in a terminal outside the
team) to help with a staging check. It should be able to report to the liaison and restart agents
while you're away from the keyboard, but never act as you, never take the team down and never answer
or approve anything.

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
Staging check of the release candidate: steps 1-9 pass; step 10 waits for a lead restart.
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

- **Never delegated:** `xt down`, `xt restart --all`, `xt version use` and `rollback`, `xt operator
  add` and `xt delegate`. They stay yours, grant or no grant, and `--as human` keeps working only
  from your own terminal. Answers and approvals need a drive grant (see 7).
- Both the token and the registered process are needed: the token copied into another shell, or the
  operator's process without the token, is refused. A new operator session needs a new `xt
  operator add`.
- `xt status` and the TUI's Team header show the grant and its end time while it lasts. See the
  [user guide](user-guide.md#15-an-operator-acting-for-you).

## 13. A chat session: an operator, the pane and a question

*Illustrative: it needs a running liaison and a registered operator.*

**Context.** You talk to the liaison in `xt chat`. Three kinds of line surprise newcomers most: one
from an operator, one you typed into the liaison's own pane, and a question answered in place (ids
and times below are from a fresh team). Chat needs 80 columns. In **your own terminal**:

```sh
xt chat
```

Type `Where is the digest?` and press `enter`. Meanwhile an operator registered as `op` (as
`helper` is in 12) reports to the liaison:

```sh
XT_OPERATOR_TOKEN=$(cat /path/to/team/.xt/operators/op.token) \
  /path/to/team/bin/xt send liaison --as op --type report <<'XT_END'
Staging check passed: steps 1-9.
XT_END
```

and you type `Ship the digest after QA's run` into the liaison's pane in Herdr instead of chat.
Chat shows, at 80 columns:

```text
xt chat with liaison (claude) · pane input recorded

12:00 you  #4
Where is the digest?

12:00 » op (operator)  #5
Staging check passed: steps 1-9.
(sent by op, an operator, on the human's behalf)

12:00 you (typed in the pane, unverified)  #6
Ship the digest after QA's run

12:00 liaison  #7  ⚑ yes/no
QA passed the digest. Publish it now?

Answer yes or no.
⚑ waits for your answer: tab picks it

liaison › 
enter send · tab answer (1) · ctrl+t goals · pgup/pgdn scroll · ctrl+d leave
```

- **The operator's line** is marked `» op (operator)` (magenta) and ends with its `(sent by op, …)`
  mark: it is the operator's report, never yours.
- **The pane line** is yours as far as xt can tell: the supervisor read it from the liaison's
  session log, which is why the header says `pane input recorded`. The label says
  `unverified` because anything that can type into that pane is recorded the same way, so such a
  line never answers, approves or closes anything.
- **The question:** press `tab`. Its text shows above the input line, which now reads
  `answer #7 › `, and the line under it `enter send #7 · esc back · ctrl+t goals · pgup/pgdn scroll ·
  ctrl+d leave`. Type `yes` and press `enter`: chat says `#8 answer to #7 → liaison: …`, the
  question shows `✓ answered #8: yes`, and the answer is recorded exactly as `xt answer 7 yes`
  would record it. `esc` instead goes back to messaging the liaison.
- `PageUp`, `PageDown`, `Home` and `End` scroll the conversation without leaving your draft.
