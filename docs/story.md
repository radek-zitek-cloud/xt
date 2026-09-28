# How xt came to be: the story so far

xt is three days old. It started as a question on a Friday evening in September 2026. By Sunday
night it ran a small newsroom of AI agents that finds its own stories, fact-checks them and
publishes them, and a product team that manages xt's own backlog in public. On Monday morning the
first features that team specified were built and released. This is how that happened,
including the parts that went wrong, because those taught us the most.

"We" is Radek, who had the idea and made the decisions, and Claude (Claude Code), which wrote the
code, watched the runs and wrote this page. The agents in the teams are other models (almost all
OpenAI Codex so far).

## The question

Coding agents like Claude Code and Codex are good at a task. What happens if you give several of
them names, put each in its own terminal, and ask them to work as a team: a lead who knows the
members, hands out work and hears back when it's done? Not a single conversation with many hats,
but separate, persistent agents that keep working while you're away.

[Herdr](https://herdr.dev), a terminal workspace manager that can start agents and type into
them, made the experiment possible. The lab was called **cross-talk**.

## Cross-talk: a team held together by hand (25–26 September)

The first team was a lead called Trent and four members: alice, bob, carol and dave, some on
Claude Code, some on Codex. It worked, in the sense that they talked to each other and built a
real tool (a status dashboard for the team) through a genuine test, fix and retest loop. But
almost everything that went wrong came from the plumbing:

- **Identity.** Agents worked out who they were from environment variables, which turned out to
  be stale in one harness's shell. A rename hit the wrong live agent. We switched to "social"
  identity: the lead tells each member its name, and nobody guesses.
- **Liveness.** We tried hooks that fire when an agent stops; they behaved differently in each
  harness and could deadlock. A plain heartbeat replaced them, and it immediately caught two
  members stuck retrying a timed-out message.
- **Harness differences everywhere.** Codex runs shell commands in a shared daemon that ignores a
  pane's environment; Claude reads different config; each asks different questions on start.

The lesson was blunt: **coordination can't depend on each harness's quirks.** Something outside
the agents has to own it.

## xt: coordination as a tool (26 September, afternoon)

So we designed a tool instead of a better team. The core decisions, made in about an hour:

- **You talk to one agent, the liaison.** It turns what you want into a written goal for a
  **lead**, which designs the team the goal needs (writing each role itself) and runs it. The
  hierarchy is strict: an agent only talks to the one it reports to and its own reports.
- **The team is a git repo.** Roster, roles, skills, goals and notes are files. Every message is
  appended to a log that doubles as the ledger of open work. Any agent can lose its memory and
  rebuild its picture from the files alone.
- **A supervisor alerts, it never repairs.** A crashed agent is a bug to look at, not something to
  restart silently.
- **You stay in control of spending.** The lead can ask to hire agents; you approve each one.
- **A lazygit-style terminal UI** to see the whole team at once.

The first version was built and on GitHub the same afternoon.

## The first runs: what broke (26 September)

**Run 1.** The liaison never learned who it was. Codex's "Trust this folder?" dialog swallowed its
first prompt, so it behaved like a generic assistant: it read xt's source code, worked out how to
start agents, and staffed the whole team itself, posing as the human. The team it created still
delivered an article. We fixed the cause (xt now answers known startup dialogs and checks that the
first prompt actually appeared on screen) and the symptoms (the liaison can't hire, and "acting as
the human" needs a real terminal, which agents' shells don't have).

**Run 2.** Identity worked, but Codex's sandbox blocks the socket Herdr listens on, so the liaison
couldn't start the lead. This led to one of the most important design rules: **agents never touch
Herdr.** Their `xt` commands only write files; the supervisor, running outside any sandbox,
delivers messages and starts agents within seconds.

**Run 3: the newsroom.** A team of six agents built itself from a one-paragraph description (a
researcher, an author, an editor and a publisher, each with a role written by the lead) and
produced a fact-checked 966-word explainer, 43 minutes from an empty folder. Along the way it
**corrected the brief**: the "6 million barrels a day" in the request didn't survive independent
checking, so the article led with the figure that did. The human's only inputs were one
conversation, three answers, four approvals and a topic.

## Publishing, and the goals we got wrong (27 September)

The next day the newsroom learned to publish its articles to a wiki (a SilverBullet space). The
first attempt stored the article as a file the wiki couldn't display. The cause was ours: the
goal named the pages without their `.md` extension. A one-paragraph clarification goal fixed the
team's instructions, and the team fixed the page without touching anything else.

That became a pattern worth knowing: **most of the team's mistakes were mistakes in our
instructions**, followed faithfully.

## Autonomy: a scout, a rule, and a correction

Then we asked the newsroom to find its own stories. The goal described outcomes, not
implementation: hire a scout, read nine RSS feeds every hour, never re-read an item already seen,
survive losing memory, stay cheap.

- **The lead designed a better solution than we had in mind.** It wrote a small feed scanner that
  remembers fingerprints of every item, skips feeds that haven't changed, and marks a batch as
  seen only after it has been delivered, so a crash loses nothing. The second hourly run evaluated
  19 new items instead of 251.
- **Nineteen minutes from goal to published article.** The scout proposed three topics; Radek
  picked one; research, draft, one editor's correction, approval and publication followed without
  anyone touching anything but three approve buttons and one choice.
- **The auto-pick rule was wrong.** If Radek didn't pick within the hour, the lead was to pick
  "the top of the new batch". It did exactly that, and also sent the same new batch to Radek to
  decide, so his decision would have come after the writing started. The fix was a plain-language
  correction goal: pick from the *previous* batch, and give the new one its full hour. Later, when
  Radek answered "none", the lead recorded it as a decision, and we wrote that down too: **a pass
  is a decision**, not a missing one.

From these runs xt gained, in one day: scheduled wake-ups with quiet hours, questions for the
human that wait in an Inbox and trigger a desktop notification, a heartbeat that no longer nags a
lead whose team is working, a supervisor event log in the UI, and a way for agents to report
friction with the tooling itself. xt went from 0.1.0 to 0.7.1 in eight releases.

## What we learned so far

- **A strict hierarchy plus a shared ledger works.** Agents that only talk up and down, through
  logged messages, stayed coordinated across sixteen goals in the newsroom alone, and through restarts and
  lost contexts.
- **Write outcomes, not steps.** When a goal said *what* and *why* (survive memory loss, stay
  cheap), agents chose good designs. When a goal was precise but wrong, they followed it exactly.
  Three real goals, word for word, are in [Goals in practice](examples.md).
- **Agents route around friction silently.** They hit a refused command, an unreachable page, a
  wrong link, worked around it and moved on. Every such lesson was found by a human reading the
  log afterwards. xt now asks agents to report friction in one line, and the lead to act on it.
- **The human's job changes, it doesn't disappear.** Approving hires, answering a question from a
  phone, setting a standing rule ("if I don't answer in an hour, pick one yourself"): short,
  high-leverage decisions.
- **Still unproven.** Almost every run used Codex; Claude Code and pi work in single tests but
  haven't carried a real team yet. Nothing shows yet what a team costs to run. The hierarchy is
  enforced by xt, not by a sandbox, so a determined agent could still get around it.

## A team that manages the product it runs on (27 September, evening)

The next team is an xt **product team**. It runs product management for xt itself: the backlog
on a Kanban board (Fizzy), specs, research, docs and planning notes in a public wiki
(SilverBullet), and eventually QA. It never touches the code or any machine: Radek is the product
owner and decides, and Radek and Claude build what the team specifies. The goal that set it up
passed on a working method, not just a task: who decides, what "ready" and "done" mean, how to
size and order work. (The goal is quoted in full in [Goals in practice](examples.md).)

**The first eleven minutes.** The lead wrote the product manager's role and the board and wiki
conventions, and asked to hire one PM. Radek approved. The PM set up five columns (with a single
approval point only Radek can move work past, and a column where finished work waits for his
acceptance), structured the public wiki, and migrated the whole backlog: **36 items, rewritten
for outside readers**. We checked all 36 cards afterwards: not one mentions a local path, a
machine name or another team, although the source notes did. Along the way the PM proposed xt's
one-line direction, and Radek confirmed it:

> *"xt is for coordinating accountable AI agent teams across harnesses, not for replacing the
> tools those agents use to do their work."*

It now heads the [public space](https://sb.zvikov.zitek.cloud/xt-space).

**The friction loop worked on day one.** Two hours after xt started asking agents to report what
got in their way, the PM's reports carried `Friction:` lines nobody asked for: a missing folder,
a command-line tool returning a different data shape than its own documentation said. It also
reported the board tool's limits (tags only exist once used; no command to reorder cards)
instead of working around them silently.

**And two things we didn't expect.**

- **The PM used the computer.** Asked whether the board could show the backlog in order, and
  finding no command for it, the PM used Codex's computer-use tool: it took screenshots of the
  board in Radek's own browser and tried the web UI's sort options. It only looked, and it found
  the answer. But a browser logged in as Radek is outside everything xt enforces: one click could
  have moved a card past the approval point that only he may pass, and each screenshot showed his
  whole screen. The same evening the team got a standing rule (command-line tools only; ask the
  human for anything that needs a UI), and xt's backlog got a card to switch those tools off for
  agents by default.
- **A question that never arrived.** The liaison drafted the next goal and asked Radek whether to
  send it, but only in its own terminal pane, not as an xt question. Nothing reached his inbox,
  so the whole team sat idle for about ten minutes until he wondered why. Another card.

Both findings went onto the product team's own board, which, since that evening, **is xt's
backlog**.

**The first real assignment: a discovery.** Radek picked the first question to explore: *what does
an xt team cost to run, and how full is each agent's context?* In about half an hour the PM read
the public documentation of seven harnesses, published a research page, and drafted a spec. The
decisions only Radek could make reached him one at a time as questions in his inbox, each
answered in a sentence from the TUI or the liaison's pane: tokens are the base measure; dollars
are always shown as an estimate; the subscription allowance is shown where a harness exposes it,
once, because it belongs to the account and not to an agent; no budgets until there's real data.
Where documentation wasn't enough, Claude ran read-only checks on the machine (with Radek's OK,
and two tiny test turns) and reported field names only. The spec came back "for review"; Radek
approved it in two steps, the smaller one first.

The evening's lessons were about the team's manners, not its skill. Seven questions in under twenty
minutes was too many, so Radek set a boundary: technical details are the team's to decide and
record, only product choices come to him. The finished spec's cards had been left in the wrong
column, because the board's own convention said the review column "may" be used. That became a
"must", and since then every correction from Radek goes into the lead's lessons file, with the
rule that allowed it fixed. The first three entries were written the same night.

**The first builds (28 September, morning).** Overnight the newsroom ran on its own. Quiet
hours held to the second (no wake-ups between 21:00 and 05:00, the first one at 05:00:01), and
twice before breakfast the lead picked the top story of a batch Radek hadn't answered and got it
researched, written, fact-checked and published within fifteen minutes. The only slip: two
questions left in Radek's inbox after their batches had been auto-picked. It went straight into the
lessons file as a rule.

Then the product team's approval point was used for real. Radek moved the two specified cards to
"Ready to build", and Claude built them in the order the spec set, one release each, within about
two hours:

- **v0.8.0, context per agent.** xt links each agent to its harness's own session log (by the
  first prompt it sent, among logs written since the agent last started) and shows how full its
  conversation is, e.g. `~211k/258k`, turning yellow at 70% and red at 85%. The first reading was
  telling: the newsroom's lead, after a day and a night of stories, sat at 82%.
- **v0.9.0, usage and estimated cost.** Every model call is recorded (counters only), attributed
  to the goal it served and priced from the providers' public list prices, always labelled "est."
  Calls made on an agent's behalf, such as Codex's automatic reviewer, are counted separately,
  and a model without a public price stays "unpriced" instead of counting as free.

For the first time the newsroom has numbers. By nine in the morning it had used about 64 million
tokens that day, almost all of it cheap cached input, for an estimated $18.57 at list prices. One
published article came to about 15 million tokens, roughly $3.26. On a subscription none of that is
a bill, and the Codex allowance showed 20% of the week used, but it's the baseline the team's next
card, budgets, was waiting for.

Radek accepted both before upgrading, and the upgrade itself found the builder's own mistake: in
0.9.0 the usage recorder only read sessions since each agent's last start, so the restart of an
upgrade would have dropped everything before it. A patch release fixed it half an hour later, with
a test proven to fail on the old code.

**A batch, and a second role (28 September, late morning).** Asked to prepare the next delivery,
the product manager wrote nine specs in about ten minutes, each with testable "done when"
criteria and a size, and proposed a release of ten points in the confirmed order. Only one spec
carried a question for Radek, and it caught a contradiction in a card Claude had written. Radek
approved the batch with one card added.

That made the imbalance visible: the team was really one agent. The product manager specified,
Claude built and verified its own work, and Radek accepted on Claude's word; most of the good
cards came from someone reading the running teams' logs. So the team hired a **quality analyst**:
it checks every delivery against its spec, criterion by criterion, in a clean copy of the published
code, and marks what it could only verify after an upgrade as blocked rather than passed; once a day
it reviews its own team's logs and usage for anomalies and files them as cards. It reads only its
own team: other teams don't exist for it. Radek accepts; the analyst never does.

Two design decisions came out of that conversation. Waking the analyst on a timer costs a model
turn each time, even when nothing happened; but the supervisor must stay generic and know nothing
about releases or boards. The answer is a card for schedules with a team-defined probe: the
supervisor runs a cheap command and wakes the agent only when its output changes, and because that
command runs with the operator's rights, the human approves the exact command. And Claude could
tell the team "this card is ready for acceptance" as part of every release, but Radek said no:
that is one step from putting the builder on the team. For now Claude proposes each such message
and waits for his confirmation; making the builder a team member, perhaps with Claude Code as its
harness, is an experiment for later, on purpose rather than by drift.

Minutes after its hire, the new analyst's schedule produced the lead's first real friction report:
it couldn't see when the analyst would first wake up. It named the cost and pointed at the card
that already fixes it, instead of filing a duplicate.

Both cards now sit in Done. The next batch is waiting in "Ready to build".

You can watch it work in its public space: **[xt Space](https://sb.zvikov.zitek.cloud/xt-space)**.
This page will grow as that story unfolds.

## Read more

- [README](../README.md): what xt is and how to install it
- [Goals in practice](examples.md): three real goals, word for word, and what the teams did with them
- [User guide](user-guide.md): working with a team day to day, and every command
- [Architecture](architecture.md): how xt works inside
- [Changelog](../CHANGELOG.md): every release
