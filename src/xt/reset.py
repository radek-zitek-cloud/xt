"""`xt reset <name>`: give one agent a fresh context safely (card #56).

Different from `xt restart <name>`, which simply starts a new session: a reset refuses while the
agent owns open work, first asks the agent to save what it needs into its notes and confirm with
`xt checkpoint`, and only then replaces the session. If the checkpoint doesn't come, or new work
arrives meanwhile, nothing is reset. The fresh session recovers from its first prompt, its brief
(which points to the notes and the last checkpoint) and the ledger. xt suggests a reset when an
agent's context passes a share of its window.

`xt reset <name> --when-idle` (card #134) queues the same reset instead of refusing a busy agent: the
supervisor performs it, through the same checkpoint, the next time the agent is idle with no open
work. The queue lives in .xt/state/resets.json, so it survives a supervisor restart. The automatic
policy (card #114, off by default) queues such a reset for an idle agent whose context is above an
absolute token threshold.
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
CLOCK_SKEW = 300  # seconds a reading may appear to come from the future (clocks differ a little)


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


def _request(ctx: Ctx, name: str, who: str = "The human is") -> str:
    xt = ctx.paths.xt_bin
    return (f"[xt reset] {who} resetting your context: this conversation will be replaced by a fresh "
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

    if name in queued(ctx):
        drop(ctx, name, "a plain `xt reset` ran first")
    return [_replace(ctx, name, done)]


def _replace(ctx: Ctx, name: str, done: dict, why: str = "") -> str:
    """The checkpoint is saved: stop the old session, start a fresh one, record it."""
    from .spawn import do_spawn, stop

    stop(ctx, name)
    ws = do_spawn(ctx, name)
    msg = (f"reset {name}{why}: checkpoint of {done['at'][11:16]} saved (\"{clip(done['summary'])}\"); fresh session "
           f"in workspace {ws}, recovering from its first prompt, brief and members/{name}/notes.md")
    ctx.ledger.append(SYSTEM, HUMAN, "system", msg)
    _set_cooldown(ctx, name)
    return msg


# --- card #134: a reset queued until the agent is idle ---------------------------------------------

POLICY = "policy"  # `by` of a reset the automatic policy queued (card #114)


def _queue_path(ctx: Ctx):
    return ctx.paths.state / "resets.json"


def _load(ctx: Ctx) -> dict:
    try:
        data = json.loads(_queue_path(ctx).read_text())
    except (OSError, ValueError):
        data = {}
    data.setdefault("queued", {})
    data.setdefault("cooldown", {})
    return data


def _save(ctx: Ctx, data: dict) -> None:
    tmp = _queue_path(ctx).with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(_queue_path(ctx))


def queued(ctx: Ctx) -> dict:
    """name -> {"at", "by", "why", "asked", "before"} for every queued reset."""
    return _load(ctx)["queued"]


def _now(ctx: Ctx) -> str:
    return ctx.ledger.clock().isoformat(timespec="seconds")


def queued_text(entry: dict) -> str:
    """'reset queued (by human at 09:12; …)' for `xt status` and the Team detail."""
    by = "xt's reset policy" if entry.get("by") == POLICY else entry.get("by", HUMAN)
    if entry.get("asked"):
        return f"reset queued (by {by} at {entry['at'][11:16]}): asked for a checkpoint at {entry['asked'][11:16]}"
    return f"reset queued (by {by} at {entry['at'][11:16]}): waits until it's idle with no open work"


def queue(ctx: Ctx, name: str, by: str = HUMAN, why: str = "") -> str:
    """Record a reset to run when the agent is idle with no open work; returns at once."""
    a = ctx.team.agent(name)
    if a is None or a.kind == HUMAN or not a.active:
        raise XtError(f"{name!r} is not an active agent of this team")
    if name not in ctx.herdr.agents():
        raise XtError(f"{name} isn't running: nothing to reset (`xt spawn {name}` starts it with a fresh session)")
    with ctx.ledger.lock():
        data = _load(ctx)
        if name in data["queued"]:
            return f"{name}: already {queued_text(data['queued'][name])} (`xt reset {name} --cancel` removes it)"
        data["queued"][name] = {"at": _now(ctx), "by": by, "why": why, "asked": None, "before": None}
        _save(ctx, data)
    who = "xt's reset policy" if by == POLICY else by
    ctx.ledger.append(SYSTEM, HUMAN, "system",
                      f"reset of {name} queued by {who}{f' ({why})' if why else ''}: the supervisor runs it "
                      f"when {name} is idle with no open work")
    return (f"reset of {name} queued: the supervisor asks it for a checkpoint when it's idle with no open work "
            f"(`xt reset {name} --cancel` removes it)")


def drop(ctx: Ctx, name: str, why: str) -> bool:
    """Remove a queued reset, with a ledger line saying why. False when none was queued."""
    with ctx.ledger.lock():
        data = _load(ctx)
        entry = data["queued"].pop(name, None)
        if entry is None:
            return False
        if entry.get("by") == POLICY:  # the policy doesn't queue the same reset again at once (#114)
            data["cooldown"][name] = _now(ctx)
        _save(ctx, data)
    ctx.ledger.append(SYSTEM, HUMAN, "system", f"queued reset of {name} dropped: {why}")
    return True


def cancel(ctx: Ctx, name: str) -> str:
    if not drop(ctx, name, "cancelled by the human"):
        raise XtError(f"no reset of {name} is queued")
    return f"queued reset of {name} cancelled"


def _set_cooldown(ctx: Ctx, name: str) -> None:
    with ctx.ledger.lock():
        data = _load(ctx)
        data["cooldown"][name] = _now(ctx)
        _save(ctx, data)


def _update(ctx: Ctx, name: str, **fields) -> None:
    with ctx.ledger.lock():
        data = _load(ctx)
        if name in data["queued"]:
            data["queued"][name].update(fields)
            _save(ctx, data)


def advance(ctx: Ctx, live: dict, pending_to: set[str], timeout: float = CHECKPOINT_TIMEOUT) -> list[str]:
    """One supervisor step for each queued reset; never waits. Returns lines for the supervisor log.

    Waiting: when the agent is idle (no messages queued for it either) and owns no open goal or task,
    ask it for a checkpoint. Asked: once the checkpoint is confirmed, replace the session; if work
    arrived meanwhile, go back to waiting (the reset stays queued); if no checkpoint comes within
    the timeout, drop the queued reset (the session is untouched, as with a plain reset)."""
    from .herdr import DELIVERABLE

    out = []
    now = ctx.ledger.clock()
    for name, entry in list(queued(ctx).items()):
        a = ctx.team.agent(name)
        if a is None or a.kind == HUMAN or not a.active:
            drop(ctx, name, f"{name} is no longer an active agent")
            out.append(f"queued reset of {name} dropped: not an active agent")
            continue
        agent = live.get(name)
        if agent is None:
            continue  # stopping drops it (spawn.stop); a crash raises its own alert, and the reset waits
        by = "xt's reset policy" if entry.get("by") == POLICY else f"the {entry.get('by', HUMAN)}"
        if entry.get("asked"):
            done = checkpoints(ctx).get(name, {})
            if open_work(ctx, name):  # first: never reset an agent that owns open work
                _update(ctx, name, asked=None, before=None)
                ctx.ledger.append(SYSTEM, HUMAN, "system",
                                  f"queued reset of {name} postponed: new work arrived while it was saving; "
                                  f"it stays queued")
                out.append(f"queued reset of {name} postponed: new work arrived")
            elif done.get("at") and done.get("at") != entry.get("before"):
                with ctx.ledger.lock():
                    data = _load(ctx)
                    data["queued"].pop(name, None)
                    _save(ctx, data)
                why = f" (queued by {by} at {entry['at'][11:16]}{'; ' + entry['why'] if entry.get('why') else ''})"
                out.append(_replace(ctx, name, done, why))
            elif (now - dt.datetime.fromisoformat(entry["asked"])).total_seconds() >= timeout:
                drop(ctx, name, f"no checkpoint within {int(timeout)} s (its session is untouched; queue it "
                                f"again or look at its pane)")
                out.append(f"queued reset of {name} dropped: no checkpoint")
            continue
        if agent.status not in DELIVERABLE or name in pending_to or open_work(ctx, name):
            continue
        before = checkpoints(ctx).get(name, {}).get("at")
        who = "xt's automatic reset policy is" if entry.get("by") == POLICY else "The human is"
        try:
            ctx.herdr.prompt(name, _request(ctx, name, who))
        except XtError as e:
            out.append(f"queued reset of {name}: couldn't ask it for a checkpoint ({e}); trying again")
            continue
        _update(ctx, name, asked=_now(ctx), before=before)
        ctx.ledger.append(SYSTEM, HUMAN, "system", f"queued reset of {name}: it's idle with no open work; "
                                                   f"asked it to save a checkpoint")
        out.append(f"queued reset of {name}: asked it for a checkpoint")
    return out


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
    from .usage import short

    approx = "~" if reading.approximate else ""
    return (f"reset suggested for {name}: context {approx}{short(reading.used)}/{short(reading.window)} "
            f"({round(100 * share)}%, from the {reading.source}): `xt reset {name}` once its open work is done")


# --- card #114: the automatic reset policy (off by default) -----------------------------------------


def threshold(team, agent) -> tuple[int | None, str | None]:
    """(tokens, problem): this agent's threshold in tokens, None when the policy doesn't apply to it
    (policy off, or its own `auto_reset_tokens = "off"`), and a problem text for a bad setting."""
    if team.policy("auto_reset") is not True:
        return None, None
    own = agent.auto_reset_tokens
    value = own if own is not None else team.policy("auto_reset_tokens")
    where = f"agent {agent.name}'s auto_reset_tokens" if own is not None else "[policy] auto_reset_tokens"
    if isinstance(value, str) and value.strip().lower() == "off":
        return None, None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        whom = f"for {agent.name}" if own is not None else "for agents without their own"
        return None, f"{where} = {value!r} in team.toml isn't a token count or \"off\": no automatic reset {whom}"
    return int(value), None


def cooldown_seconds(team) -> tuple[float, str | None]:
    value = team.policy("auto_reset_cooldown_hours")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        default = 6
        return default * 3600.0, (f"[policy] auto_reset_cooldown_hours = {value!r} in team.toml isn't a number of "
                                  f"hours: using {default}")
    return float(value) * 3600, None


def apply_policy(ctx: Ctx, live: dict, pending_to: set[str], readings: dict) -> tuple[list[str], list[str]]:
    """Queue a reset (card #134's path) for each idle agent without open work whose fresh context
    reading is above its threshold in tokens and that had no reset inside the cool-down.
    Returns (supervisor log lines, problems with the settings)."""
    from .herdr import DELIVERABLE
    from .usage import short

    team = ctx.team
    if team.policy("auto_reset") is not True:
        return [], []
    out, problems = [], []
    cooldown, problem = cooldown_seconds(team)
    if problem:
        problems.append(problem)
    now = ctx.ledger.clock()
    data = _load(ctx)
    for a in team.agents():
        if a.kind == HUMAN or not a.active or a.name in data["queued"]:
            continue
        limit, problem = threshold(team, a)
        if problem and problem not in problems:
            problems.append(problem)
        agent = live.get(a.name)
        if limit is None or agent is None or agent.status not in DELIVERABLE or a.name in pending_to:
            continue
        reading = readings.get(a.name)
        if not fresh(reading, now) or reading.used <= limit:
            continue
        last = data["cooldown"].get(a.name)
        if last and (now - dt.datetime.fromisoformat(last)).total_seconds() < cooldown:
            continue
        if open_work(ctx, a.name):
            continue
        approx = "~" if reading.approximate else ""
        why = f"context {approx}{reading.used} tokens, above the threshold of {limit} tokens; policy auto_reset"
        queue(ctx, a.name, by=POLICY, why=why)
        out.append(f"auto reset: queued a reset of {a.name} (context {approx}{short(reading.used)}, "
                   f"threshold {short(limit)})")
    return out, problems
