# How xt came to be: the story so far

xt is two days old. It started as a question on a Friday evening in September 2026 and, by
Sunday night, it ran a small newsroom of AI agents that finds its own stories, fact-checks them
and publishes them, and it was about to get a product team of its own. This is how that happened,
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
- **Agents route around friction silently.** They hit a refused command, an unreachable page, a
  wrong link, worked around it and moved on. Every such lesson was found by a human reading the
  log afterwards. xt now asks agents to report friction in one line, and the lead to act on it.
- **The human's job changes, it doesn't disappear.** Approving hires, answering a question from a
  phone, setting a standing rule ("if I don't answer in an hour, pick one yourself"): short,
  high-leverage decisions.
- **Still unproven.** Almost every run used Codex; Claude Code and pi work in single tests but
  haven't carried a real team yet. Nothing shows yet what a team costs to run. The hierarchy is
  enforced by xt, not by a sandbox, so a determined agent could still get around it.

## What's next: a team that manages the product it runs on

The next team is an xt **product team**: a product manager first, then a researcher, a technical
writer and a QA tester. It manages xt's own backlog on a Kanban board, writes specs, research and
release notes in a public wiki, and tests each release by following the user guide. It never
touches the code: Radek and Claude build what it specifies.

You can watch it work in its public space: **[xt Space](https://sb.zvikov.zitek.cloud/xt-space)**.
This page will grow as that story unfolds.

## Read more

- [README](../README.md): what xt is and how to install it
- [User guide](user-guide.md): working with a team day to day, and every command
- [Architecture](architecture.md): how xt works inside
- [Changelog](../CHANGELOG.md): every release
