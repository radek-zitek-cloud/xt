"""The agent lifecycle's shared records (card #215): what spawn, watch, reset, jobs, dispatch, pane
input and the brief all read or write about an agent's starts and stops, so that they depend on this
module instead of on each other. It imports none of them.

- the supervisor: its pid and whether it saved live state just now;
- expected and stopped agents: who xt started, and who the human stopped on purpose;
- jobs: Herdr work agents asked for, waiting for the supervisor;
- checkpoints and queued resets (`xt reset`, card #56/#134), and when a reset is suggested.

The actions stay in their modules: starting and stopping in spawn, the reset itself in reset, the
jobs' execution in jobs, the supervisor's loop in watch.
"""

import datetime as dt
import json
import os
import time

from .context import Ctx
from .team import HUMAN, SYSTEM
from .usage import short

# --- the supervisor ---------------------------------------------------------------------------------


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def watch_pid(ctx: Ctx) -> int | None:
    f = ctx.paths.state / "watch.pid"
    if not f.exists():
        return None
    pid = int(f.read_text().strip() or 0)
    return pid if pid and pid_alive(pid) else None


TICKED_WITHIN = 30  # seconds: a supervisor that saved live state this recently is running


def recently_ticked(ctx: Ctx) -> bool:
    """The supervisor saved Herdr's agent list (state/live.json) in the last few ticks. Its pid can
    be invisible from a sandboxed shell (a PID namespace) while it runs fine (card #165, rc2)."""
    try:
        ts = json.loads((ctx.paths.state / "live.json").read_text())["ts"]
        age = (ctx.ledger.clock() - dt.datetime.fromisoformat(ts)).total_seconds()
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return -TICKED_WITHIN <= age <= TICKED_WITHIN


# --- expected and stopped agents --------------------------------------------------------------------


def expected(ctx: Ctx) -> set[str]:
    """Agents xt started and hasn't stopped/retired: if one vanishes, something went wrong."""
    f = ctx.paths.state / "expected.json"
    return set(json.loads(f.read_text())) if f.exists() else set()


def set_expected(ctx: Ctx, name: str, present: bool) -> None:
    with ctx.ledger.lock():
        names = expected(ctx)
        (names.add if present else names.discard)(name)
        f = ctx.paths.state / "expected.json"
        f.write_text(json.dumps(sorted(names)))


def stopped(ctx: Ctx) -> set[str]:
    """Agents the human stopped on purpose (`xt stop`, `xt down`, `x` in the TUI) and nobody has
    started since: not running is what the human wants, so nothing alerts about it."""
    f = ctx.paths.state / "stopped.json"
    return set(json.loads(f.read_text())) if f.exists() else set()


def set_stopped(ctx: Ctx, name: str, present: bool) -> None:
    with ctx.ledger.lock():
        names = stopped(ctx)
        (names.add if present else names.discard)(name)
        (ctx.paths.state / "stopped.json").write_text(json.dumps(sorted(names)))


# --- jobs (see jobs.py) -----------------------------------------------------------------------------


class Jobs:
    def __init__(self, ctx: Ctx):
        self.ctx = ctx
        self.path = ctx.paths.state / "jobs.json"

    def _load(self) -> list[dict]:
        return json.loads(self.path.read_text()) if self.path.exists() else []

    def _save(self, items: list[dict]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, indent=1))
        os.replace(tmp, self.path)

    def pending(self) -> list[dict]:
        with self.ctx.ledger.lock():
            return self._load()

    def add(self, kind: str, args: dict, requester: str) -> int:
        with self.ctx.ledger.lock():
            items = self._load()
            job_id = max((j["id"] for j in items), default=0) + 1
            items.append({"id": job_id, "kind": kind, "args": args, "requester": requester,
                          "added": time.time()})
            self._save(items)
        return job_id

    def remove(self, job_id: int) -> None:
        with self.ctx.ledger.lock():
            self._save([j for j in self._load() if j["id"] != job_id])


# --- checkpoints (see reset.py) ---------------------------------------------------------------------


def checkpoints_path(ctx: Ctx):
    return ctx.paths.state / "checkpoints.json"


def checkpoints(ctx: Ctx) -> dict:
    try:
        return json.loads(checkpoints_path(ctx).read_text())
    except (OSError, ValueError):
        return {}


# --- queued resets (card #134; see reset.py) --------------------------------------------------------

POLICY = "policy"  # `by` of a reset the automatic policy queued (card #114)


def _resets_path(ctx: Ctx):
    return ctx.paths.state / "resets.json"


def load_resets(ctx: Ctx) -> dict:
    try:
        data = json.loads(_resets_path(ctx).read_text())
    except (OSError, ValueError):
        data = {}
    data.setdefault("queued", {})
    data.setdefault("cooldown", {})
    return data


def save_resets(ctx: Ctx, data: dict) -> None:
    tmp = _resets_path(ctx).with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(_resets_path(ctx))


def queued(ctx: Ctx) -> dict:
    """name -> {"at", "by", "why", "asked", "before"} for every queued reset."""
    return load_resets(ctx)["queued"]


def now_text(ctx: Ctx) -> str:
    return ctx.ledger.clock().isoformat(timespec="seconds")


def queued_text(entry: dict) -> str:
    """'reset queued (by human at 09:12; …)' for `xt status` and the Team detail."""
    by = "xt's reset policy" if entry.get("by") == POLICY else entry.get("by", HUMAN)
    if entry.get("asked"):
        return f"reset queued (by {by} at {entry['at'][11:16]}): asked for a checkpoint at {entry['asked'][11:16]}"
    return f"reset queued (by {by} at {entry['at'][11:16]}): waits until it's idle with no open work"


def drop(ctx: Ctx, name: str, why: str) -> bool:
    """Remove a queued reset, with a ledger line saying why. False when none was queued."""
    with ctx.ledger.lock():
        data = load_resets(ctx)
        entry = data["queued"].pop(name, None)
        if entry is None:
            return False
        if entry.get("by") == POLICY:  # the policy doesn't queue the same reset again at once (#114)
            data["cooldown"][name] = now_text(ctx)
        save_resets(ctx, data)
    ctx.ledger.append(SYSTEM, HUMAN, "system", f"queued reset of {name} dropped: {why}")
    return True


# --- when a reset is suggested (card #56) -----------------------------------------------------------

SUGGEST_AT = 0.70  # context share at which xt suggests a reset (the Team panel's yellow line)
FRESH_FOR = 2 * 3600  # a context reading older than this is too stale to suggest anything
CLOCK_SKEW = 300  # seconds a reading may appear to come from the future (clocks differ a little)


def fresh(reading, now: dt.datetime | None) -> bool:
    """Whether a known reading is recent enough to act on (the 70% suggestion and card #114)."""
    # without a timestamp there's no telling whether the reading is current (#56, rc1 QA)
    if reading is None or not reading.known or not reading.observed or now is None:
        return False
    try:
        seen = dt.datetime.fromisoformat(str(reading.observed).replace("Z", "+00:00"))
        age = (now - seen).total_seconds()
    except (ValueError, TypeError):
        return False
    # recent means observed in the last FRESH_FOR seconds: not older, and not from the future beyond
    # a little clock skew (a future timestamp says nothing about now; rc2 QA)
    return -CLOCK_SKEW <= age <= FRESH_FOR


def suggestion(name: str, reading, now: dt.datetime | None = None) -> str | None:
    """'reset suggested: …' when an agent's context is at or above the threshold, and only when
    the reading is trustworthy: known, with a window, and recent."""
    if reading is None or not reading.known or not reading.window:
        return None
    share = reading.used / reading.window
    if share < SUGGEST_AT or not fresh(reading, now):
        return None
    approx = "~" if reading.approximate else ""
    return (f"reset suggested for {name}: context {approx}{short(reading.used)}/{short(reading.window)} "
            f"({round(100 * share)}%, from the {reading.source}): `xt reset {name}` once its open work is done")
