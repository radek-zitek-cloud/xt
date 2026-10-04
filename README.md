# xt

Hierarchical teams of AI agents that run in any harness (Claude Code, Codex, pi) on top of
[Herdr](https://herdr.dev). You talk to one agent, the **liaison**, in `xt chat`. It turns what you
want into goals for a **lead**, which designs and runs whatever team the work needs: a dev team, a
newsroom, an accounting desk. xt owns the coordination (messages, the ledger of open work, the
supervisor, approvals, recovery), so an agent only needs a shell and a prompt.

![xt chat at 100 columns: the human asks for a weekly digest; the liaison reads the goal back as a yes/no question, which is answered yes; a dimmed line shows the goal going to the lead; the liaison confirms it was dispatched; a question with two numbered options, a recommendation and Other waits for an answer, and the key line offers tab to answer it](docs/chat.svg)

*`xt chat`, captured from xt itself (`docs/chat.svg`): a goal read back and dispatched, then a
question with options waiting for your answer.*

**Status:** 0.x and experimental, Linux only. Built by one person with an AI team: the xt-team (a
liaison, a lead, a product manager, a builder, a quality analyst and a UX researcher) plans,
builds, checks and accepts xt's own releases on xt. Every release, with what changed, is in
[CHANGELOG.md](CHANGELOG.md).

## Quick start

```sh
curl -fsSLO https://raw.githubusercontent.com/radek-zitek-cloud/xt/main/bin/xt-clone.sh
sh xt-clone.sh my-team
```

That clones xt into `./my-team`, runs `mise trust` and `xt init` (team and Herdr session both
named `my-team`; it asks which harness and model the liaison and lead use, and whether hires need
your approval), starts the Herdr session in the background, runs `xt up` and attaches you to the
session. Then, in any terminal in `./my-team`:

```sh
xt chat
```

and tell the liaison what you want. The lead starts when the first goal is dispatched. Your clone
becomes your team's own repo: `xt init` renames `origin` to `upstream`, so updates come with
`git pull upstream main`.

## First 10 minutes

- **You need** Linux with [Herdr](https://herdr.dev), `git`, [mise](https://mise.jdx.dev) active in
  your shell (it provides `uv` and puts the clone's `bin/` on `PATH`), and at least one harness CLI
  installed and logged in: `claude`, `codex` or `pi`.
- **It costs** model calls: every agent turn is one, on your harness subscription or API key. You
  approve each hire and each schedule an agent asks for, and `xt status` and the TUI show tokens
  and an estimated cost per agent and goal (list prices, not a bill).

Where a first start usually stops, and what to do:

- `missing prerequisite: herdr` (from `xt-clone.sh`) or `missing essentials: herdr` (from
  `xt init`): install it and run again. `no supported harness is installed`: install and log in to
  one of the three.
- `xt: command not found`: mise isn't active in this shell, or the clone isn't trusted yet. Run
  `mise trust` in the clone, or call `./bin/xt`.
- `xt init` ends with `next: start the Herdr session with herdr --session my-team`: xt runs its
  agents inside that session, so open it first, then run `xt`.
- A Claude Code liaison sits at a permission prompt and the Inbox shows `blocked:liaison`. A new
  team has no capability block, so Claude Code asks before its first command. Answer it in the
  liaison's pane, then give the team a `[defaults.capabilities]` block (see the guide).
- The Inbox shows `noprompt:liaison`: its first prompt never showed on its screen.
  `xt restart liaison` starts it again.

**It works when** the liaison answers you in `xt chat`: a reply under your first message, and
`xt status` shows the supervisor and the liaison running.

## What xt can do

**A day with a team.**

1. In `xt chat` you say what you want. The liaison drafts a goal with you and reads it back as a
   yes/no question; your yes dispatches it to the lead.
2. The lead plans the work, writes the roles and skills the team needs, and asks to hire agents.
   Each hire, and each schedule an agent asks for, waits for your yes, because every agent turn
   costs money.
3. Members work in their own Herdr workspaces and report up the chain; xt delivers every message,
   keeps the ledger of open goals and tasks, and nudges agents that go quiet.
4. When the team needs a decision, the liaison asks it as a question that says what answer it
   takes: yes or no, two to four options with their consequences and a recommendation, or your
   own words. It waits in chat and in the Inbox, with a desktop notification, until you answer.
5. When the goal is done you get one notification, and the liaison tells you what was achieved and
   where the results are.

To see how the work flows, open the TUI (`xt`): the team by harness with each agent's context, the
Inbox of what needs you, goals with their tasks, every message as a lane chart, and the whole
thread of what you select. `xt tui --demo` shows it on made-up data. Your own coding agent can
act for you as a named **operator**, for at most an hour at a time and logged under its own name.

Everything the team builds up (roles, skills, goal briefs, notes, outputs) is plain files in the
team's git repo, so an agent that restarts or loses its context picks up from the files.

**What agents may do.** One capability block per agent in `team.toml` (or one for the whole team) says what it may write,
run and reach, the same on every harness; xt turns it into each harness's own settings and shows
each capability as **enforced** or **advisory**:

```toml
[[agent]]
name = "builder"
[agent.capabilities]
write = ["/home/me/work/clone"]
commands = ["git", "uv", "rg"]
require = ["write"]            # refuse to start where the harness can't enforce it
```

xt switches agents' desktop and browser tools off where the harness allows it, starts them without
your account connectors unless the block names one, and, on Claude Code and pi, without your
personal skills. Command-line tools that hold your credentials are denied by name (enforced on
Claude Code, advisory elsewhere). The [user guide](docs/user-guide.md#13-what-agents-may-do-capabilities)
has the whole vocabulary and what each harness enforces.

## Status and limits

- **Tested on Linux only.** Claude Code has carried most of xt's own team; the quality analyst
  runs on Codex, and pi has run a UX researcher. Mixed-harness teams work, with each harness's
  own limits.
- **The hierarchy is enforced by `xt`, not by a sandbox:** an agent that ignores the protocol
  could still reach other panes through its shell.
- **Capabilities are only as strong as the harness.** Claude Code enforces write, deny and
  commands through its settings (by name, not isolation: an allowed command can still use the
  network); Codex enforces the network through its sandbox; pi enforces skills and connectors.
  `xt status` says which is which for each agent.
- **Costs are estimates** from public list prices (`prices.toml`), not bills; there are no budgets.
- **Text typed into the liaison's pane is recorded as unverified** and never answers or approves
  anything: answer in `xt chat` or the Inbox.
- **Upgrading:** read each release's Upgrading note in [CHANGELOG.md](CHANGELOG.md). A team still
  using the `permissions`, `codex_options` or `connectors` lines converts them before upgrading to
  0.24 ([how](docs/user-guide.md#upgrading-to-024-convert-the-old-permission-lines)).

## Read on

- [User guide](docs/user-guide.md): working in chat, the TUI, running the team, capabilities,
  updating, operators, `team.toml` and every command.
- [Examples](docs/examples.md): real goals given to teams, word for word, and configurations to copy.
- [The story so far](docs/story.md): how xt came to be, what broke and what was learned.
- [Architecture](docs/architecture.md): how xt works inside.
- [Development](docs/development.md): running the tests, the repo layout, versioning and releasing.
- [The direction](https://sb.zvikov.zitek.cloud/xt-space/planning/direction-b-roadmap): where xt is
  heading.

## Say hello

**Tried it? Say hello.** xt is made by Radek, mostly by the AI team it describes. If you try it,
even for five minutes, I'd love to hear how it went, what you used it for or where it stopped you:
[Say hello on GitHub Discussions](https://github.com/radek-zitek-cloud/xt/discussions/1). Found a
bug, have a question, or want to tell how a first try went? [Open an
issue](https://github.com/radek-zitek-cloud/xt/issues/new/choose): there is a short form for each.

## License

MIT, see [LICENSE](LICENSE).
