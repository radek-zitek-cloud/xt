"""Card #198: the notes budget. Each agent's `members/<name>/notes.md` is measured in bytes on disk
against its budget (`notes_budget` in team.toml, `Team.notes_budget`). Over budget, `xt status`
shows the size; over budget for longer than PERIOD, the supervisor raises one `notes:NAME` alert,
which the agent's own brief shows too. xt only measures and tells: it never writes a notes file.
"""

import datetime as dt
import json
import math

from .alerts import Alerts
from .context import Ctx
from .team import HUMAN

PERIOD = 24 * 3600  # seconds a notes file stays over budget before the alert


def size(ctx: Ctx, name: str) -> int | None:
    """Bytes of the agent's notes file on disk; None without one."""
    try:
        return (ctx.paths.members / name / "notes.md").stat().st_size
    except OSError:
        return None


def kb(n: int, exact: bool = False) -> str:
    """Decimal kilobytes (1 kB = 1,000 bytes): a size with one decimal, rounded up so a file just
    over its budget never reads as equal (`16.1 kB`); a budget without one when it's whole (`16 kB`)."""
    if exact and n % 1000 == 0:
        return f"{n // 1000} kB"
    return f"{math.ceil(n / 100) / 10:.1f} kB"


def over(ctx: Ctx, a) -> tuple[int, int] | None:
    """(size, budget) when the agent's notes are over budget (exactly at it is within); else None."""
    n = size(ctx, a.name)
    budget = ctx.team.notes_budget(a)
    return (n, budget) if n is not None and n > budget else None


def status_text(ctx: Ctx, a) -> str | None:
    """`notes 17.2 kB / 16 kB` for `xt status`, only for an agent over budget."""
    o = over(ctx, a)
    return f"notes {kb(o[0])} / {kb(o[1], exact=True)}" if o else None


def alert_text(name: str, n: int, budget: int) -> str:
    return (f"{name}'s notes are over budget: notes {kb(n)} / {kb(budget, exact=True)} for more than "
            f"{PERIOD // 3600} hours. Prune members/{name}/notes.md; see the notes shape in the protocol.")


def check(ctx: Ctx) -> list[str]:
    """The supervisor's step: time each agent's over-budget spell from when it was first seen, and
    raise `notes:NAME` once it lasts longer than PERIOD; then a new period starts, so the alert
    doesn't repeat within one. Back within budget (or no file): the alert clears and the timer
    resets. `.xt/state/notes_budget.json` keeps name -> the start of the current period."""
    path = ctx.paths.state / "notes_budget.json"
    try:
        since = json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        since = {}
    alerts = Alerts(ctx)
    now = ctx.ledger.clock()
    out: list[str] = []
    agents = {a.name: a for a in ctx.team.agents() if a.kind != HUMAN and a.active}
    for name in sorted(set(agents) | set(since)):
        o = over(ctx, agents[name]) if name in agents else None
        if o is None:
            since.pop(name, None)
            alerts.resolve(f"notes:{name}")
            continue
        start = since.setdefault(name, now.isoformat(timespec="seconds"))
        if (now - dt.datetime.fromisoformat(start)).total_seconds() > PERIOD:
            text = alert_text(name, *o)
            if f"notes:{name}" in alerts.active():
                alerts.update_text(f"notes:{name}", text)
            elif alerts.raise_(f"notes:{name}", text):
                out.append(f"alert: {name}'s notes over budget ({kb(o[0])} / {kb(o[1], exact=True)})")
            since[name] = now.isoformat(timespec="seconds")  # a new period
    try:
        path.write_text(json.dumps(since))
    except OSError:
        pass
    return out


def brief_line(ctx: Ctx, name: str) -> str | None:
    """The agent's own `notes:NAME` alert for its brief, where it can act on it."""
    al = Alerts(ctx).active().get(f"notes:{name}")
    return f"Alert for you: {al['text']}" if al else None
