"""`xt reset <name>`: give one agent a fresh context safely (card #56).

Different from `xt restart <name>`, which simply starts a new session: a reset refuses while the
agent owns open work, first asks the agent to save what it needs into its notes and confirm with
`xt checkpoint`, and only then replaces the session. If the checkpoint doesn't come, or new work
arrives meanwhile, nothing is reset. The fresh session recovers from its first prompt, its brief
(which points to the notes and the last checkpoint) and the ledger. Nothing resets on its own: xt
only suggests a reset when an agent's context passes a threshold.
"""

import datetime as dt
import json
import time

from .context import Ctx
from .paths import XtError
from .team import HUMAN, SYSTEM

CHECKPOINT_TIMEOUT = 300  # seconds an agent gets to save its notes and confirm
SUGGEST_AT = 0.70  # context share at which xt suggests a reset (the Team panel's yellow line)
FRESH_FOR = 2 * 3600  # a context reading older than this is too stale to suggest anything


def _path(ctx: Ctx):
    return ctx.paths.state / "checkpoints.json"


def checkpoints(ctx: Ctx) -> dict:
    try:
        return json.loads(_path(ctx).read_text())
    except (OSError, ValueError):
        return {}


def record_checkpoint(ctx: Ctx, name: str, summary: str) -> str:
    a = ctx.team.agent(name)
    if a is None or not a.active or a.kind == HUMAN:
        raise XtError(f"{name!r} is not an active agent of this team")
    summary = " ".join(summary.split()) or "notes saved"
    now = ctx.ledger.clock().isoformat(timespec="seconds")
    data = checkpoints(ctx)
    data[name] = {"at": now, "summary": summary[:500]}
    _path(ctx).write_text(json.dumps(data, indent=1))
    ctx.ledger.append(name, "", "note", f"checkpoint: {summary[:500]}")
    return f"checkpoint recorded for {name} at {now[11:16]}"


def open_work(ctx: Ctx, name: str) -> list[dict]:
    return [i for i in ctx.ledger.open_items() if i["owner"] == name and i["type"] in ("goal", "task")]


def _request(ctx: Ctx, name: str) -> str:
    xt = ctx.paths.xt_bin
    return (f"[xt reset] The human is resetting your context: this conversation will be replaced by a fresh "
            f"session. Before that, save everything you'd need to continue into members/{name}/notes.md "
            f"(decisions, open threads, where things are; no secrets), then confirm with:\n"
            f"{xt} checkpoint --as {name} <<'XT_END'\none line: what the next session should know first\nXT_END\n"
            f"Don't start new work.")


def preflight(ctx: Ctx, name: str) -> None:
    """Everything that refuses a reset before anything is asked of the agent."""
    a = ctx.team.agent(name)
    if a is None or a.kind == HUMAN or not a.active:
        raise XtError(f"{name!r} is not an active agent of this team")
    live = ctx.herdr.agents().get(name)
    if live is None:
        raise XtError(f"{name} isn't running: `xt spawn {name}` starts it with a fresh session anyway")
    work = open_work(ctx, name)
    if work:
        ids = ", ".join(f"#{i['id']}" for i in work)
        raise XtError(f"{name} owns open work ({ids}): nothing was reset. Let it finish or close that work first "
                      f"(`xt restart {name}` is the emergency route, without a checkpoint)")
    if live.status == "working":
        raise XtError(f"{name} is working right now: nothing was reset; try again when it's idle")


def clip(text: str, limit: int = 80) -> str:
    """Shorten at a word boundary, marking the cut."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:.")
    return (cut or text[:limit]) + "…"


def reset(ctx: Ctx, name: str, timeout: float = CHECKPOINT_TIMEOUT, poll: float = 2.0,
          sleep=time.sleep, clock=time.time) -> list[str]:
    from .spawn import do_spawn, stop

    preflight(ctx, name)
    before = checkpoints(ctx).get(name, {}).get("at")
    ctx.ledger.append(SYSTEM, HUMAN, "system", f"reset requested for {name}: asked it to save a checkpoint")
    ctx.herdr.prompt(name, _request(ctx, name))
    deadline = clock() + timeout
    while True:
        done = checkpoints(ctx).get(name, {})
        if done.get("at") and done.get("at") != before:
            break
        if open_work(ctx, name):
            ctx.ledger.append(SYSTEM, HUMAN, "system", f"reset of {name} abandoned: new work arrived")
            raise XtError(f"new work arrived for {name} while it was saving: nothing was reset; try again later")
        if clock() >= deadline:
            ctx.ledger.append(SYSTEM, HUMAN, "system", f"reset of {name} abandoned: no checkpoint within {int(timeout)} s")
            raise XtError(f"{name} didn't confirm a checkpoint within {int(timeout)} s: nothing was reset "
                          f"(its session is untouched); try again, or look at its pane")
        sleep(poll)

    stop(ctx, name)
    ws = do_spawn(ctx, name)
    msg = (f"reset {name}: checkpoint of {done['at'][11:16]} saved (\"{clip(done['summary'])}\"); fresh session "
           f"in workspace {ws}, recovering from its first prompt, brief and members/{name}/notes.md")
    ctx.ledger.append(SYSTEM, HUMAN, "system", msg)
    return [msg]


def suggestion(name: str, reading, now: dt.datetime | None = None) -> str | None:
    """'reset suggested: …' when an agent's context is at or above the threshold, and only when
    the reading is trustworthy: known, with a window, and recent."""
    if reading is None or not reading.known or not reading.window:
        return None
    share = reading.used / reading.window
    if share < SUGGEST_AT:
        return None
    # without a timestamp there's no telling whether the reading is current: no suggestion (#56, rc1 QA)
    if not reading.observed or now is None:
        return None
    try:
        seen = dt.datetime.fromisoformat(str(reading.observed).replace("Z", "+00:00"))
        if (now - seen).total_seconds() > FRESH_FOR:
            return None
    except (ValueError, TypeError):
        return None
    from .usage import short

    approx = "~" if reading.approximate else ""
    return (f"reset suggested for {name}: context {approx}{short(reading.used)}/{short(reading.window)} "
            f"({round(100 * share)}%, from the {reading.source}): `xt reset {name}` once its open work is done")
