# Developing xt

For people changing xt itself. Using xt is in the [user guide](user-guide.md); how it works inside
is in [architecture.md](architecture.md).

## Running the tests

```sh
uv sync && uv run pytest
```

The suite needs no Herdr server and no harness: tests use a fake Herdr and temporary team repos.
A change comes with its tests, a CHANGELOG entry under `[Unreleased]` (or the release being
built), and the documents it changes: the user guide for anything users see, the README's feature
lines when users see something new, [architecture.md](architecture.md) when a module is added or
its job changes, and [examples.md](examples.md) for a configuration or workflow users copy.

The user documents (README, guide, examples) describe the release they ship with: every command,
flag, key and file name checked against the code, no version-history notes inside instructions
(the CHANGELOG has them), and examples labelled **runnable** (prerequisites and expected output
shown) or **illustrative** (anything that needs your authority, such as an approval or an answer).

## Layout

| xt's own (from upstream) | Your team's (committed in your repo) | Runtime (gitignored) |
|---|---|---|
| `bin/`, `src/`, `tests/`, `pyproject.toml`, `uv.lock`, `mise.toml`, `prices.toml` | `team.toml` (roster, settings) | `.xt/log/` message log = ledger; `.xt/usage/` per-turn usage |
| `protocol.md`, `harnesses/`, `docs/`, `site/` | `roles/*` written by the lead | `.xt/state/` queue, jobs, approvals, alerts, snapshots |
| `roles/lead.md`, `roles/liaison.md` | `skills/*`, `goals/`, `members/<name>/`, `settings/`, outputs | `.xt/cache/` |

`.agents/skills` and `.claude/skills` are symlinks to `skills/`, so codex, pi and claude also
discover team skills natively.

## Versioning

xt uses [semantic versioning](https://semver.org/); `xt --version` prints the version, and
[CHANGELOG.md](../CHANGELOG.md) lists every release with an **Upgrading** note for running teams.

A change is **breaking** when a team has to change its own files or its agents would behave
differently: the CLI (commands, flags), the `team.toml` format, the message protocol
(`protocol.md`, message types, the envelope), the ledger and `.xt/` state formats, the harness
adapter format, and the shipped `roles/lead.md` and `roles/liaison.md`.

While xt is `0.x`, a breaking change or a notable feature raises the minor version (0.1 → 0.2) and
a fix raises the patch version (0.1.0 → 0.1.1). `1.0.0` comes once `team.toml` and the protocol
are stable.

## Releasing

A release starts as a **candidate** and becomes final only once it's accepted, so a team that
upgrades to check a release never runs code presented as final that nobody accepted yet.

1. Move the `[Unreleased]` entries in CHANGELOG.md under a new `## [X.Y.Z-rcN] — YYYY-MM-DD`
   heading, with an **Upgrading** note.
2. Set `version = "X.Y.ZrcN"` in `pyproject.toml` (Python's spelling of `-rcN`), run `uv lock` and
   `uv run pytest`.
3. Commit (`Release vX.Y.Z-rcN`), tag it `git tag -a vX.Y.Z-rcN -m "xt vX.Y.Z-rcN"`, push both
   (`git push origin main vX.Y.Z-rcN`) and create a **pre-release** from the tag with that
   section as its notes: `gh release create vX.Y.Z-rcN --prerelease --title "xt vX.Y.Z-rcN" --notes-file <section>`.
4. If acceptance finds a problem, fix it and release `-rcN+1` the same way.
5. When every card in it is accepted, release the accepted code as final: add a `## [X.Y.Z]`
   heading above the candidates' entries saying which candidate it is, set `version = "X.Y.Z"`,
   `uv lock`, commit (`Release vX.Y.Z`), tag `vX.Y.Z`, push, and `gh release create vX.Y.Z` (not a
   pre-release). Between the accepted candidate and the final only the version, the changelog and
   the site's version and feature text change, which `git diff vX.Y.Z-rcN vX.Y.Z` shows.

## Reporting a problem

Use the [issue forms](https://github.com/radek-zitek-cloud/xt/issues/new/choose) (bug, question, or
how a first try went). Don't paste secrets, tokens or your team's private files into an issue.
