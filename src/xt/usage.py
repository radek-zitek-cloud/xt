"""Live context per agent: how full each agent's conversation is, read from its harness's own
session log (card #25 / #53).

Every harness keeps a JSONL log per session. xt links an agent to its session by the first prompt
it sent ("You are **name**, an agent in the xt team …"), looking only at logs written since the
agent last started, and keeps the link in `.xt/state/sessions.json`. From the log's tail it reads
the latest usage record: tokens in the context, the window size when known, and when it was
observed. Anything it can't establish is reported as unknown, never guessed; only counters are
read, never prompts or replies.
"""

import datetime as dt
import glob
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass

from .adapters import Adapter, load_adapters
from .context import Ctx
from .team import HUMAN, SYSTEM

NOT_FOUND = "session not found since the agent started"
HEAD_BYTES = 256 * 1024  # where the first prompt is (session header + first user message)
TAIL_BYTES = 512 * 1024  # where the latest usage record is
MODEL_WINDOWS_TTL = 24 * 3600


@dataclass
class Reading:
    used: int | None = None  # tokens in the context after the latest turn
    window: int | None = None  # the model's context window
    approximate: bool = False  # derived from the latest turn's usage, not a live occupancy figure
    observed: str | None = None  # ISO timestamp of the usage record
    source: str = ""  # e.g. "codex session log"
    reason: str = ""  # why it's unknown, when it is
    model: str | None = None  # the model the session log names (card #128: `default` made real)

    @property
    def known(self) -> bool:
        return self.used is not None


def short(n: int | None) -> str:
    if n is None:
        return "?"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1000:
        return f"{round(n / 1000)}k"
    return str(n)


def compact(r: Reading) -> str:
    """'~204k/258k' for the Team row; '—' when there's nothing to show."""
    if not r.known:
        return "—"
    return f"{'~' if r.approximate else ''}{short(r.used)}/{short(r.window)}"


def _iso(ts) -> str | None:
    """Harnesses stamp records as ISO text or epoch milliseconds (pi); keep ISO."""
    if isinstance(ts, (int, float)):
        return dt.datetime.fromtimestamp(ts / 1000 if ts > 1e11 else ts, dt.timezone.utc).isoformat()
    return ts


def describe(r: Reading, now: dt.datetime | None = None) -> str:
    """One line for the agent detail and xt status."""
    if not r.known:
        return f"context unknown ({r.reason or 'no usage recorded yet'})"
    pct = f" ({round(100 * r.used / r.window)}%)" if r.window else ""
    approx = "approximate, " if r.approximate else ""
    age = ""
    if r.observed and now:
        try:
            secs = int((now - dt.datetime.fromisoformat(str(r.observed).replace("Z", "+00:00"))).total_seconds())
            age = f", {secs // 60}m ago" if secs >= 60 else ", just now"
        except (ValueError, TypeError):
            pass
    window = f" / {short(r.window)}" if r.window else " / window unknown"
    return f"context {'~' if r.approximate else ''}{short(r.used)}{window}{pct} · {approx}from the {r.source}{age}"


# --- finding an agent's session -----------------------------------------------------------------


def last_starts(ctx: Ctx) -> dict[str, float]:
    """When xt last started each agent (every start logs 'started <name> (…) in workspace …')."""
    out: dict[str, float] = {}
    for m in ctx.ledger.messages(since_days=30):
        if m["from"] == SYSTEM and m["to"] == HUMAN and m["type"] == "system" and m["body"].startswith("started "):
            name = m["body"].split()[1]
            out[name] = dt.datetime.fromisoformat(m["ts"]).timestamp()
    return out


def _head(path: str) -> str:
    with open(path, "rb") as fh:
        return fh.read(HEAD_BYTES).decode("utf-8", "replace")


def _is_main_session(fmt: str, head: str) -> bool:
    """Codex also logs its approval reviewer ("guardian") as sub-sessions that repeat the prompt."""
    if fmt == "codex":
        first = head.split("\n", 1)[0]
        try:
            source = json.loads(first).get("payload", {}).get("source")
        except ValueError:
            return False
        return not (isinstance(source, dict) and "subagent" in source)
    return True


def _marker_re(name: str, team: str) -> re.Pattern:
    # the first prompt as it appears in a JSON log: quotes around the team name are escaped
    return re.compile(re.escape(f"You are **{name}**, an agent in the xt team ") + r'\\?"' + re.escape(team))


def _later_markers(ctx: Ctx, name: str) -> list[str]:
    """Two pieces of the first prompt's first paragraph after its opening: they survive when the
    harness loses the opening characters (card #167)."""
    return [f"The team's repo (your home, not your workspace) is {ctx.paths.root}.",
            f"Always pass `--as {name}` when you use xt."]


def _recent_logs(adapter: Adapter, since: float | None) -> list[str]:
    """The adapter's session logs written since `since` (two minutes' slack), newest first."""
    floor = (since or time.time() - 3 * 86400) - 120
    candidates = []
    for path in glob.glob(os.path.expanduser(adapter.sessions)):
        try:
            if os.path.getmtime(path) >= floor:
                candidates.append(path)
        except OSError:
            continue
    return sorted(candidates, key=os.path.getmtime, reverse=True)


def find_session(ctx: Ctx, adapter: Adapter, name: str, since: float | None) -> str | None:
    """The newest main session log whose first prompt is this agent's, written since it started."""
    if not adapter.sessions:
        return None
    marker = _marker_re(name, ctx.team.name)
    for path in _recent_logs(adapter, since):
        try:
            head = _head(path)
        except OSError:
            continue
        if marker.search(head) and _is_main_session(adapter.session_format, head):
            return path
    return None


WHOLE, INCOMPLETE = "whole", "incomplete"


def prompt_in_log(ctx: Ctx, adapter: Adapter, name: str, since: float) -> str | None:
    """How the agent's first prompt arrived, read from its session log (card #167): WHOLE when its
    opening is there, INCOMPLETE when only its later parts are, None when no log has it yet."""
    if not adapter.sessions:
        return None
    marker = _marker_re(name, ctx.team.name)
    later = _later_markers(ctx, name)
    for path in _recent_logs(adapter, since):
        try:
            head = _head(path)
        except OSError:
            continue
        if not _is_main_session(adapter.session_format, head):
            continue
        if marker.search(head):
            return WHOLE
        if all(m in head for m in later):
            return INCOMPLETE
    return None


def session_for(ctx: Ctx, adapter: Adapter, name: str, started: float | None) -> str | None:
    """The agent's current session log, remembered in .xt/state/sessions.json per start."""
    state_path = ctx.paths.state / "sessions.json"
    try:
        known = json.loads(state_path.read_text()) if state_path.exists() else {}
    except ValueError:
        known = {}
    rec = known.get(name)
    if rec and rec.get("started") == started and os.path.exists(rec.get("path", "")):
        return rec["path"]
    path = find_session(ctx, adapter, name, started)
    if path:
        known[name] = {"path": path, "started": started, "harness": adapter.name}
        try:
            state_path.write_text(json.dumps(known, indent=1))
        except OSError:
            pass  # read-only here (e.g. a sandbox): find it again next time
    return path


# --- reading the latest usage -------------------------------------------------------------------


def _tail_lines(path: str) -> list[str]:
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        fh.seek(max(0, size - TAIL_BYTES))
        data = fh.read().decode("utf-8", "replace")
    lines = data.split("\n")
    if size > TAIL_BYTES:
        lines = lines[1:]  # the first one is probably cut
    return [ln for ln in reversed(lines) if ln.strip()]


def codex_model(lines: list[str]) -> str | None:
    """The model of the newest `turn_context` record (Codex writes one per turn; `lines` newest
    first), the same record usage recording prices turns by."""
    for ln in lines:
        if '"turn_context"' not in ln:
            continue
        try:
            model = json.loads(ln)["payload"].get("model")
        except (ValueError, KeyError, AttributeError, TypeError):
            continue
        if isinstance(model, str) and model:
            return model
    return None


def _codex(lines: list[str], adapter: Adapter) -> Reading:
    model = codex_model(lines)
    for ln in lines:
        if '"token_count"' not in ln:
            continue
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        info = (d.get("payload") or {}).get("info")
        if not info or not info.get("last_token_usage"):
            continue
        return Reading(used=info["last_token_usage"].get("total_tokens"), window=info.get("model_context_window"),
                       approximate=True, observed=d.get("timestamp"), source="codex session log", model=model)
    return Reading(source="codex session log", reason="no usage recorded yet", model=model)


def _claude(lines: list[str], adapter: Adapter) -> Reading:
    for ln in lines:
        if '"usage"' not in ln:
            continue
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        msg = d.get("message")
        if d.get("isSidechain") or not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
            continue
        u = msg["usage"]
        used = sum(int(u.get(k) or 0) for k in
                   ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))
        return Reading(used=used, window=adapter.context_windows.get(msg.get("model", "")),
                       observed=d.get("timestamp"), source="claude session log",
                       model=msg.get("model") if isinstance(msg.get("model"), str) else None)
    return Reading(source="claude session log", reason="no usage recorded yet")


def _pi_windows(ctx: Ctx) -> dict[str, int]:
    """pi's model table (`pi --list-models`: provider, model, context, …), cached for a day."""
    cache = ctx.paths.state / "model_windows.json"
    try:
        d = json.loads(cache.read_text())
        if time.time() - d.get("at", 0) < MODEL_WINDOWS_TTL:
            return d["pi"]
    except (OSError, ValueError, KeyError):
        pass
    windows: dict[str, int] = {}
    try:
        out = subprocess.run(["pi", "--list-models"], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.TimeoutExpired):
        return windows
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 3 and re.fullmatch(r"[\d.]+[KM]", parts[2]):
            n = float(parts[2][:-1]) * (1000 if parts[2][-1] == "K" else 1_000_000)
            windows[f"{parts[0]}/{parts[1].lstrip('~')}"] = int(n)
    try:
        cache.write_text(json.dumps({"at": time.time(), "pi": windows}))
    except OSError:
        pass
    return windows


def _pi(lines: list[str], adapter: Adapter, ctx: Ctx | None = None) -> Reading:
    for ln in lines:
        if '"usage"' not in ln:
            continue
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        msg = d.get("message") if isinstance(d.get("message"), dict) else d
        u = msg.get("usage")
        if not isinstance(u, dict):
            continue
        used = u.get("totalTokens") or sum(int(u.get(k) or 0) for k in ("input", "output", "cacheRead", "cacheWrite"))
        key = f"{msg.get('provider', '')}/{msg.get('model', '')}"
        window = adapter.context_windows.get(key) or (_pi_windows(ctx).get(key) if ctx else None)
        return Reading(used=used, window=window, observed=_iso(msg.get("timestamp") or d.get("timestamp")),
                       source="pi session log", model=msg.get("model") if isinstance(msg.get("model"), str) else None)
    return Reading(source="pi session log", reason="no usage recorded yet")


def reading(ctx: Ctx, name: str, adapters: dict[str, Adapter] | None = None,
            starts: dict[str, float] | None = None) -> Reading:
    """The agent's current context, or an unknown Reading saying why."""
    a = ctx.team.agent(name)
    adapters = adapters if adapters is not None else load_adapters(ctx.paths)
    starts = starts if starts is not None else last_starts(ctx)
    adapter = adapters.get(a.harness) if a else None
    if adapter is None or not adapter.session_format:
        return Reading(reason=f"xt can't read {a.harness if a else '?'} sessions yet")
    path = session_for(ctx, adapter, name, starts.get(name))
    if not path:
        return Reading(source=f"{adapter.name} session log", reason=NOT_FOUND)
    try:
        lines = _tail_lines(path)
    except OSError as e:
        return Reading(source=f"{adapter.name} session log", reason=f"can't read it: {e.strerror}")
    if adapter.session_format == "codex":
        r = _codex(lines, adapter)
        if r.model is None:  # one very long turn: the session's first turn_context is in the head
            try:
                r.model = codex_model(_head(path).split("\n")[:-1])
            except OSError:
                pass
        return r
    if adapter.session_format == "claude":
        return _claude(lines, adapter)
    if adapter.session_format == "pi":
        return _pi(lines, adapter, ctx)
    return Reading(reason=f"unknown session format {adapter.session_format!r}")


def readings(ctx: Ctx, names: list[str]) -> dict[str, Reading]:
    adapters = load_adapters(ctx.paths)
    starts = last_starts(ctx)
    out = {}
    for n in names:
        try:
            out[n] = reading(ctx, n, adapters, starts)
        except Exception as e:  # never let a harness's log format break status, brief or the TUI
            out[n] = Reading(reason=f"couldn't read it ({type(e).__name__})")
    return out
