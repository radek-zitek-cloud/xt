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

PUBLISHED_EVERY = 6 * 3600  # seconds between the supervisor's checks of the upstream tags
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


def record_agent_start(ctx: Ctx, name: str, now: dt.datetime) -> None:
    data = load(ctx)
    data.setdefault("agents", {})[name] = {"version": __version__, "since": now.isoformat(timespec="seconds")}
    _save(ctx, data)


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


def published_due(ctx: Ctx, now: dt.datetime) -> bool:
    checked = load(ctx).get("published", {}).get("checked")
    if not checked:
        return True
    try:
        return (now - dt.datetime.fromisoformat(checked)).total_seconds() >= PUBLISHED_EVERY
    except (ValueError, TypeError):
        return True


@dataclass
class Versions:
    published: str | None
    published_note: str  # "checked 2h ago", "last known 0.11.0, check failed: …", "not checked yet"
    installed: str | None
    supervisor: str | None  # None while running = started before xt recorded versions
    agents: dict[str, str | None] = field(default_factory=dict)  # running agents → version that started them
    supervisor_running: bool = True

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
        out += f" · published {display(self.published)}" if self.published else " · published ?"
        return out

    def line(self) -> str:
        """Labelled, for `xt status` and briefs."""
        parts = [f"published {display(self.published)} ({self.published_note})",
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
            n for n, v in self.agents.items() if v is None)
        if unknown:
            notes.append(f"version unknown (started before xt recorded versions): {', '.join(unknown)}")
        if self.upgrade_available:
            notes.append(f"a newer release is published ({display(self.published)}); nothing upgrades on its own")
        return out + "".join(f"\n  {n}" for n in notes)

    def detail(self) -> str:
        sup = ("not running" if not self.supervisor_running else
               display(self.supervisor) if self.supervisor else "unknown (started before xt recorded versions)")
        lines = [f"supervisor: {sup}"]
        lines += [f"{n}: {display(v) if v else 'unknown (started before xt recorded versions)'}"
                  for n, v in sorted(self.agents.items())]
        return "\n".join(lines)


def current(ctx: Ctx, live_names: set[str] | None = None, supervisor_running: bool | None = None,
            now: dt.datetime | None = None) -> Versions:
    """The three versions as far as they can be known right now, from local files only."""
    from .watch import watch_pid

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
    return Versions(published, note, installed(ctx), supervisor, agents, supervisor_running)


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
