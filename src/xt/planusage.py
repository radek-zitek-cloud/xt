"""Claude Code plan usage from its status line (card #120).

Claude Code writes no rate limits to its session logs; it passes them only to a status-line command,
as JSON on stdin: `rate_limits.five_hour` and `rate_limits.seven_day`, each with `used_percentage`
and `resets_at` (Unix seconds) — seen on Claude Code 2.1.284. A session's first call, before any
model reply, has no `rate_limits` at all. `bin/xt-statusline` runs `main` for a Claude agent whose
settings file opts in (`statusLine`); it keeps each window's last reading in
`<team root>/.xt/state/claude_plan.json`, and `xt status` and the TUI show it (`lines`).

The team root is `XT_ROOT` when set, else the xt checkout the script belongs to. Standard library
only: the script runs with the system Python, outside xt's environment, and must never break the
status line of the agent it runs for."""

import datetime as dt
import json
import math
import os
import tempfile
import time
from pathlib import Path

WINDOWS = (("five_hour", "5h"), ("seven_day", "7d"))
SNAPSHOT = "claude_plan.json"
STALE_SECONDS = 3 * 3600  # older readings show `unknown`: the human shares the plan and keeps using it


def root(env, script_root: Path) -> Path:
    """The team root: `XT_ROOT` when set, else the xt checkout the script lives in."""
    return Path(env["XT_ROOT"]) if env.get("XT_ROOT") else script_root


def snapshot_path(team_root: Path) -> Path:
    return team_root / ".xt" / "state" / SNAPSHOT


TIME_MIN, TIME_MAX = 946684800, 4102444800  # 2000-01-01 … 2100-01-01 UTC: anything else is malformed


def _number(v, low: float, high: float) -> bool:
    """A real number in [low, high]: never a bool, a string, NaN, infinity or an out-of-range value
    (a huge `resets_at` overflowed the date formatting in rc2 and broke status, QA on #120)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    if isinstance(v, float) and not math.isfinite(v):  # isfinite would overflow on a huge int
        return False
    return low <= v <= high


def window(w, observed: bool = False) -> dict | None:
    """One window's reading, checked: `used_percentage` 0–100, `resets_at` (and, from the
    snapshot, `observed_at`) Unix seconds in this century. None when anything is off."""
    if not isinstance(w, dict):
        return None
    keys = ("resets_at", "observed_at") if observed else ("resets_at",)
    if not _number(w.get("used_percentage"), 0, 100) or not all(_number(w.get(k), TIME_MIN, TIME_MAX) for k in keys):
        return None
    return {"used_percentage": float(w["used_percentage"]), **{k: int(w[k]) for k in keys}}


def parse(payload) -> dict:
    """The windows in a status-line payload: {"five_hour": {"used_percentage", "resets_at"}, …}.

    Only well-formed windows; nothing else from the payload (no session ids, paths or costs)."""
    limits = payload.get("rate_limits") if isinstance(payload, dict) else None
    out = {}
    if not isinstance(limits, dict):
        return out
    for key, _ in WINDOWS:
        w = window(limits.get(key))
        if w:
            out[key] = w
    return out


def _load(path: Path) -> dict:
    try:
        d = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def store(team_root: Path, windows: dict, now: float) -> bool:
    """Merge fresh window readings into the snapshot, atomically (a reader never sees a partial
    file). Windows not in this payload keep their last reading. Only into an existing state
    directory: a wrong root never gets one made."""
    state = snapshot_path(team_root).parent
    if not windows or not state.is_dir():
        return False
    snap = _load(snapshot_path(team_root))
    for key, w in windows.items():
        snap[key] = {**w, "observed_at": int(now)}
    fd, tmp = tempfile.mkstemp(dir=state, prefix=".claude_plan.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(snap, fh)
        os.replace(tmp, snapshot_path(team_root))
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return True


def status_text(payload, windows: dict) -> str:
    """The line Claude Code shows under the prompt: the model and the plan windows, nothing else."""
    model = payload.get("model") if isinstance(payload, dict) else None
    name = model.get("display_name") if isinstance(model, dict) else None
    parts = [name if isinstance(name, str) and name else "xt"]
    parts += [f"{label} {windows[key]['used_percentage']:.0f}%" for key, label in WINDOWS if key in windows]
    return " · ".join(parts)


def main(stdin_text: str, env, script_root: Path, now: float | None = None) -> str:
    """Status-line entry point: store the reading, return the line to print. Never raises."""
    try:
        payload = json.loads(stdin_text)
    except ValueError:
        return "xt"
    try:
        windows = parse(payload)
        store(root(env, script_root), windows, time.time() if now is None else now)
        return status_text(payload, windows)
    except Exception:  # the agent's status line matters more than one reading
        return "xt"


def _age(seconds: float) -> str:
    m = int(seconds // 60)
    return "just now" if m < 1 else f"{m}m ago" if m < 60 else f"{m // 60}h {m % 60:02d}m ago"


def window_text(label: str, w, now: float) -> tuple[str, float | None]:
    """One window for status — `5% of 5h, resets Tue 14:30` — and when that reading was taken;
    or why there's no number (and None). Never raises: a snapshot is only data."""
    w = window(w, observed=True)
    # Malformed, or read after now: the script and xt run on the same machine, so any reading
    # timestamped later than now is wrong, with no tolerance (QA on rc4).
    if w is None or w["observed_at"] > now:
        return f"{label} unknown", None
    if w["resets_at"] <= now:
        return f"{label} window reset, no reading since", None
    if now - w["observed_at"] > STALE_SECONDS:
        return f"{label} unknown (last reading {_age(now - w['observed_at'])})", None
    try:
        reset = dt.datetime.fromtimestamp(w["resets_at"]).strftime("%a %H:%M")
    except (OverflowError, OSError, ValueError):
        return f"{label} unknown", None
    return f"{w['used_percentage']:.0f}% of {label}, resets {reset}", w["observed_at"]


def line(team_root: Path, now: float | None = None) -> str:
    """`claude 5% of 5h, resets …; 7% of 7d, resets …; read 2m ago (account-wide)`."""
    now = time.time() if now is None else now
    try:
        snap = _load(snapshot_path(team_root))
    except Exception:  # e.g. a file too deeply nested for json: still only `unknown`
        snap = {}
    shown = [window_text(label, snap.get(key), now) for key, label in WINDOWS]
    parts = [text for text, _ in shown]
    fresh = [seen for _, seen in shown if seen is not None]
    if fresh:
        parts.append(f"read {_age(now - min(fresh))}")
    return "claude " + "; ".join(parts) + " (account-wide)"
