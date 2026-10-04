"""Which xt a team is on (card #58): the latest published release, the version installed in the
team's repo, and the versions actually running (the supervisor, and the xt that started each
agent). Three different things during an upgrade, never collapsed into one number.

- published: the newest final release tag (no candidates) on the team's upstream, checked by the
  supervisor at most every few hours and cached in `.xt/state/versions.json`; reading it never
  touches the network, because agents' shells often have none.
- installed: the version in the team repo's own `pyproject.toml`, i.e. the code the next command
  or start will run. Read on every call, so a stale record can't hide an upgrade.
- running: the supervisor records its version when it starts; `spawn` records the version that
  started each agent (its first prompt, protocol and reply hints come from that version).
"""

import datetime as dt
import json
import re
import subprocess
from dataclasses import dataclass, field

from . import __version__
from .context import Ctx
from .lifecycle import stopped, watch_pid

PUBLISHED_EVERY = 6 * 3600  # seconds between the supervisor's checks of the upstream tags
STALE_RETRY = 15 * 60  # sooner while the cache is older than the installed final (card #133)
PENDING = "published ≥ installed, check pending"
UNKNOWN = "unknown (started before xt recorded versions)"
NOT_YET = "not recorded yet (first turn running)"  # card #177
STARTING_FOR = 30 * 60  # seconds a begun start without a record counts as fresh, not as too old
FINAL_TAG = re.compile(r"refs/tags/v(\d+)\.(\d+)\.(\d+)$")


def parse(version: str | None) -> tuple[int, int, int, int, int] | None:
    """(major, minor, patch, final?, rc) for ordering; None when it isn't a version xt knows."""
    if not version:
        return None
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-?rc\.?(\d+))?", version.strip())
    if not m:
        return None
    rc = m.group(4)
    return (int(m[1]), int(m[2]), int(m[3]), 0 if rc else 1, int(rc or 0))


def display(version: str | None) -> str:
    """0.12.0rc1 (Python's spelling) is shown as the tag spells it: 0.12.0-rc1."""
    if not version:
        return "unknown"
    return re.sub(r"(\d)rc(\d+)$", r"\1-rc\2", version)


def _state_path(ctx: Ctx):
    return ctx.paths.state / "versions.json"


def load(ctx: Ctx) -> dict:
    try:
        return json.loads(_state_path(ctx).read_text())
    except (OSError, ValueError):
        return {}


def _save(ctx: Ctx, data: dict) -> None:
    try:
        _state_path(ctx).write_text(json.dumps(data, indent=1))
    except OSError:
        pass  # a read-only sandbox: shown as unknown next time, never guessed


def installed(ctx: Ctx) -> str | None:
    try:
        text = (ctx.paths.root / "pyproject.toml").read_text()
    except OSError:
        return None
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else None


def record_supervisor(ctx: Ctx, now: dt.datetime) -> None:
    data = load(ctx)
    data["supervisor"] = {"version": __version__, "since": now.isoformat(timespec="seconds")}
    data.setdefault("installed_seen", {})[__version__] = now.isoformat(timespec="seconds")
    _save(ctx, data)


def mark_starting(ctx: Ctx, name: str, now: dt.datetime) -> None:
    """A start has begun; its version is recorded once its first prompt is out (card #177), and the
    agent's first brief, built before that, says it's not recorded yet rather than too old."""
    data = load(ctx)
    data.setdefault("starting", {})[name] = now.isoformat(timespec="seconds")
    _save(ctx, data)


def record_agent_start(ctx: Ctx, name: str, now: dt.datetime, codex_options: list[str] | None = None) -> None:
    data = load(ctx)
    rec = {"version": __version__, "since": now.isoformat(timespec="seconds")}
    if codex_options:  # what this start ran with, so status can tell a changed team.toml (card #169)
        rec["codex_options"] = list(codex_options)
    data.setdefault("agents", {})[name] = rec
    data.get("starting", {}).pop(name, None)
    _save(ctx, data)


def ever_started(ctx: Ctx, name: str) -> bool:
    """Whether xt has started this agent at least once (its start record is never removed)."""
    return name in load(ctx).get("agents", {})


def not_started_yet(ctx: Ctx, name: str) -> bool:
    """A member xt has never started and the human hasn't stopped: not running is by design (a new
    team's lead starts when its first goal is dispatched), so a message waiting for it isn't an
    alert (rc4, the human's correction, xt #3413)."""
    return name not in stopped(ctx) and not ever_started(ctx, name)


def started_codex_options(ctx: Ctx, name: str) -> list[str] | None:
    """The Codex options the agent's last start ran with ([] for none); None when xt has no record."""
    rec = load(ctx).get("agents", {}).get(name)
    return None if rec is None else list(rec.get("codex_options", []))


def latest_final(tag_lines: str) -> str | None:
    """The newest final release among `git ls-remote --tags` lines; candidates never count."""
    best = None
    for line in tag_lines.splitlines():
        m = FINAL_TAG.search(line.strip())
        if m:
            v = tuple(int(x) for x in m.groups())
            best = max(best, v) if best else v
    return ".".join(map(str, best)) if best else None


def _upstream(ctx: Ctx) -> str | None:
    for remote in ("upstream", "origin"):
        p = subprocess.run(["git", "-C", str(ctx.paths.root), "remote", "get-url", remote],
                           capture_output=True, text=True)
        if p.returncode == 0 and p.stdout.strip():
            return remote
    return None


def refresh_published(ctx: Ctx, now: dt.datetime, timeout: int = 20) -> str:
    """Ask the upstream for its tags and cache the newest final release. Returns what happened."""
    data = load(ctx)
    remote = _upstream(ctx)
    entry = {"checked": now.isoformat(timespec="seconds")}
    if remote is None:
        entry.update(version=None, error="no upstream remote")
    else:
        try:
            p = subprocess.run(["git", "-C", str(ctx.paths.root), "ls-remote", "--tags", remote],
                               capture_output=True, text=True, timeout=timeout)
            if p.returncode != 0:
                entry.update(version=None, error=(p.stderr.strip().splitlines() or ["git ls-remote failed"])[-1][:200])
            else:
                entry.update(version=latest_final(p.stdout), error=None)
        except (OSError, subprocess.TimeoutExpired) as e:
            entry.update(version=None, error=f"{type(e).__name__}")
    if entry.get("version") is None and data.get("published", {}).get("version"):
        entry["last_known"] = data["published"].get("version")
        entry["last_known_checked"] = data["published"].get("checked")
    data["published"] = entry
    _save(ctx, data)
    return f"published xt: {entry.get('version') or 'unknown'}" + (f" ({entry['error']})" if entry.get("error") else "")


def stale(published: str | None, installed_version: str | None) -> bool:
    """The cached published version is older than the installed final release (card #133): the
    cache missed a release, so it is never shown as the latest."""
    p, i = parse(published), parse(installed_version)
    return bool(p and i and i[3] == 1 and p < i)


def published_due(ctx: Ctx, now: dt.datetime) -> bool:
    """Every PUBLISHED_EVERY; sooner, every STALE_RETRY, while the cache is older than the installed
    final (card #133), so a failed or unhelpful check isn't repeated on every tick."""
    pub = load(ctx).get("published", {})
    if not pub.get("checked"):
        return True
    try:
        age = (now - dt.datetime.fromisoformat(pub["checked"])).total_seconds()
    except (ValueError, TypeError):
        return True
    if stale(pub.get("version") or pub.get("last_known"), installed(ctx)):
        return age >= STALE_RETRY
    return age >= PUBLISHED_EVERY


@dataclass
class Versions:
    published: str | None
    published_note: str  # "checked 2h ago", "last known 0.11.0, check failed: …", "not checked yet"
    installed: str | None
    supervisor: str | None  # None while running = started before xt recorded versions
    agents: dict[str, str | None] = field(default_factory=dict)  # running agents → version that started them
    supervisor_running: bool = True
    starting: set[str] = field(default_factory=set)  # agents without a record whose start began lately (#177)

    def _unknown(self, name: str) -> str:
        return NOT_YET if name in self.starting else UNKNOWN

    @property
    def running(self) -> list[str | None]:
        return ([self.supervisor] if self.supervisor_running else []) + list(self.agents.values())

    @property
    def running_label(self) -> str:
        values = self.running
        if not values:
            return "nothing running"
        if any(v is None for v in values):
            known = {v for v in values if v}
            return "unknown" if not known else "mixed"
        return display(values[0]) if len(set(values)) == 1 else "mixed"

    @property
    def pending(self) -> bool:
        """The cache is older than the installed final: shown as PENDING, never as that number."""
        return stale(self.published, self.installed)

    @property
    def upgrade_available(self) -> bool:
        p, i = parse(self.published), parse(self.installed)
        return bool(p and i and p > i)

    @property
    def restart_needed(self) -> bool:
        """Only a known, different version counts; unknown is reported as unknown, never guessed."""
        return bool(self.installed and any(v is not None and v != self.installed for v in self.running))

    def title(self) -> str:
        """Short, for the TUI's Status title."""
        out = f"installed {display(self.installed)} · running {self.running_label}"
        if self.pending:
            return out + " · published ≥ installed"
        out += f" · published {display(self.published)}" if self.published else " · published ?"
        return out

    def published_text(self) -> str:
        """`published 0.16.1 (checked 2 h ago)`, or PENDING when the cache is older than the installed final."""
        return PENDING if self.pending else f"published {display(self.published)} ({self.published_note})"

    def line(self) -> str:
        """Labelled, for `xt status` and briefs."""
        parts = [self.published_text(),
                 f"installed {display(self.installed)}",
                 f"running {self.running_label}"]
        out = "xt versions: " + " · ".join(parts)
        notes = []
        if self.restart_needed:
            old = sorted(n for n, v in self.agents.items() if v is not None and v != self.installed)
            sup = self.supervisor_running and self.supervisor is not None and self.supervisor != self.installed
            who = (["supervisor"] if sup else []) + old
            notes.append(f"not yet running the installed version: {', '.join(who)} (restart to pick it up)")
        unknown = (["supervisor"] if self.supervisor_running and self.supervisor is None else []) + sorted(
            n for n, v in self.agents.items() if v is None and n not in self.starting)
        fresh = sorted(n for n, v in self.agents.items() if v is None and n in self.starting)
        if fresh:
            notes.append(f"version {NOT_YET}: {', '.join(fresh)}")
        if unknown:
            notes.append(f"version {UNKNOWN}: {', '.join(unknown)}")
        if self.upgrade_available:
            notes.append(f"a newer release is published ({display(self.published)}); nothing upgrades on its own")
        return out + "".join(f"\n  {n}" for n in notes)

    def detail(self) -> str:
        sup = ("not running" if not self.supervisor_running else
               display(self.supervisor) if self.supervisor else UNKNOWN)
        lines = [f"supervisor: {sup}"]
        lines += [f"{n}: {display(v) if v else self._unknown(n)}" for n, v in sorted(self.agents.items())]
        return "\n".join(lines)


def current(ctx: Ctx, live_names: set[str] | None = None, supervisor_running: bool | None = None,
            now: dt.datetime | None = None) -> Versions:
    """The three versions as far as they can be known right now, from local files only."""
    data = load(ctx)
    now = now or dt.datetime.now(dt.timezone.utc).astimezone()
    pub = data.get("published", {})
    if not pub:
        note = "not checked yet"
    elif pub.get("version"):
        note = f"checked {_ago(pub.get('checked'), now)}"
    elif pub.get("last_known"):
        note = f"last known, check failed: {pub.get('error')}"
    else:
        note = f"unknown: {pub.get('error') or 'no final release found'}"
    published = pub.get("version") or pub.get("last_known")
    if supervisor_running is None:
        supervisor_running = watch_pid(ctx) is not None
    supervisor = (data.get("supervisor") or {}).get("version") if supervisor_running else None
    if live_names is None:
        live_names = set(ctx.herdr.agents())
    agents = {n: (data.get("agents", {}).get(n) or {}).get("version") for n in sorted(live_names)}
    starting = set()
    for n, since in data.get("starting", {}).items():
        try:
            if n in agents and agents[n] is None and \
                    (now - dt.datetime.fromisoformat(since)).total_seconds() < STARTING_FOR:
                starting.add(n)
        except (ValueError, TypeError):
            continue
    return Versions(published, note, installed(ctx), supervisor, agents, supervisor_running, starting)


def _ago(iso: str | None, now: dt.datetime) -> str:
    try:
        secs = int((now - dt.datetime.fromisoformat(iso)).total_seconds())
    except (ValueError, TypeError):
        return "at an unknown time"
    if secs < 90:
        return "just now"
    if secs < 5400:
        return f"{secs // 60} min ago"
    if secs < 172800:
        return f"{secs // 3600} h ago"
    return f"{secs // 86400} days ago"
