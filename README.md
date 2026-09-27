# xt

Hierarchical agent teams that run in any harness (Claude Code, Codex, pi, ...) on top of
[Herdr](https://herdr.dev). You talk to one agent, the **liaison**. It turns what you want into
goals for a **lead**, which builds and runs whatever team the work needs: software, accounting,
research, anything. xt itself owns the coordination (messaging, the ledger of open work, the
supervisor, recovery), so agents only need a shell and a prompt.

**How it works:** [docs/architecture.md](docs/architecture.md).

**Status:** early build (v0.1). CLI, dispatcher, ledger, supervisor, roles and the lazygit-style
TUI are in place. Design and history live in the lab repo (`cross-talk/design.md`).

## Prerequisites

- [Herdr](https://herdr.dev)
- [mise](https://mise.jdx.dev) activated in your shell (it provides `uv` and puts `bin/` on PATH)
- At least one harness CLI: `codex` (recommended), `claude`, or `pi`

## Quick start

```sh
bin/xt-clone.sh my-team        # from any xt checkout; or copy the script anywhere on PATH
```

That clones xt from GitHub into `./my-team`, runs `mise trust` and `xt init` (team and Herdr
session both named `my-team`; it asks which harness to use for the liaison and lead), starts the
`my-team` Herdr session in the background if needed, runs `xt up`, and attaches you to the
session. `--no-start` stops after setup. The same by hand:

```sh
git clone <xt repo> my-team && cd my-team
mise trust
herdr --session my-team        # open (or attach) the team's Herdr session
xt                             # first run asks a few questions (xt init), then starts the team
```

`xt` starts a supervisor pane and the liaison in the team's Herdr session. Switch to the
liaison's workspace and tell it what you want. The lead starts when the first goal is
dispatched.

Your clone becomes your team's own repo: `xt init` renames `origin` to `upstream`, so you get xt
updates with `git pull upstream main`, and everything the team builds up (roles, skills, goals,
notes) is committed in your repo.

## Commands

| Command | What it does |
|---|---|
| `xt` | Set up if needed, `xt up`, then open the TUI |
| `xt tui` | The lazygit-style overview: goals, team, tasks, inbox, log; approve/deny spawns with `a`/`d` (`--demo`: sample data) |
| `xt init` | Make this clone your team's repo (asks: team name, session, liaison/lead harness) |
| `xt up` | Start the supervisor and liaison (and the lead if goals are open) |
| `xt schedule <name> 30m\|off [--message …]` | Wake an agent periodically when idle (e.g. a monitor) |
| `xt down` | Stop every running agent and the supervisor cleanly (`--keep-supervisor`: agents only) |
| `xt status` | Team, live state, open work, queue, approvals, alerts |
| `xt inbox` | What needs you: alerts, spawn approvals, messages to the human |
| `xt approve <id>` / `xt deny <id>` | Decide a spawn the lead asked for |
| `xt send <to> --type <t> "..."` | Send a message (agents add `--as <name>`) |
| `xt done <id> "..."` | Close an open goal/task |
| `xt goal new/dispatch/list` | Goal drafts and dispatch (normally the liaison does this) |
| `xt spawn`, `xt retire`, `xt stop` | Start, retire, or stop agents |
| `xt brief [name]`, `xt log` | Recovery summary and full message history |
| `xt harnesses` | Which harnesses are installed and their known limits |
| `xt watch` | The supervisor loop (`xt up` runs it in its own pane) |

## Layout

| xt's own (from upstream) | Your team's (committed in your repo) | Runtime (gitignored) |
|---|---|---|
| `bin/`, `src/`, `pyproject.toml`, `uv.lock`, `mise.toml` | `team.toml` (roster, settings) | `.xt/log/` message log = ledger |
| `protocol.md`, `harnesses/` | `roles/*` written by the lead | `.xt/state/` queue, snapshots, alerts |
| `roles/lead.md`, `roles/liaison.md` | `skills/*`, `goals/`, `members/<name>/notes.md` | `.xt/cache/` |

`.agents/skills` and `.claude/skills` are symlinks to `skills/`, so codex, pi and claude also
discover team skills natively.

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

**Following releases instead of `main`:** `git pull upstream main` gets the latest code. To stay on
a release, merge its tag instead:

```sh
git fetch upstream --tags
git merge v0.1.0
```

Either way, read the release's Upgrading note in CHANGELOG.md; restarting the team (`xt down`, then
`xt`) makes running agents and the supervisor pick up the new code and instructions.

## Releasing

1. Move the `[Unreleased]` entries in CHANGELOG.md under a new `## [X.Y.Z] — YYYY-MM-DD` heading,
   with an **Upgrading** note.
2. Set `version = "X.Y.Z"` in `pyproject.toml`, run `uv lock` and `uv run pytest`.
3. Commit (`Release vX.Y.Z`), tag it `git tag -a vX.Y.Z -m "xt vX.Y.Z"`, and push both:
   `git push origin main vX.Y.Z`.
4. Create the GitHub release from the tag with that version's changelog section as its notes:
   `gh release create vX.Y.Z --title "xt vX.Y.Z" --notes-file <section>`.

## Development

```sh
uv sync && uv run pytest
```

## License

MIT, see [LICENSE](LICENSE).
