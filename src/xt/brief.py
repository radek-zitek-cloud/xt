"""`xt brief`: a recovery summary built only from repo files and Herdr, sized for a prompt (~2k tokens)."""

import datetime as dt

from .context import Ctx
from .team import HUMAN, harness_model, schedule_text

MAX_ITEMS = 50
RECENT = 20
MEMBER_RECENT = 10
BODY = 200


def _age(ts: str, now: dt.datetime) -> str:
    secs = int((now - dt.datetime.fromisoformat(ts)).total_seconds())
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


def _trim(s: str) -> str:
    s = " ".join(s.split())
    return s if len(s) <= BODY else s[: BODY - 1] + "…"


def _line(m: dict) -> str:
    ref = f" ref:#{m['ref']}" if m.get("ref") is not None else ""
    return f"#{m['id']} {m['ts'][5:16]} {m['type']} {m['from']}→{m['to']}{ref}: {_trim(m['body'])}"


def build(ctx: Ctx, name: str | None = None) -> str:
    now = ctx.ledger.clock()
    live = ctx.herdr.agents()
    out = [f"# xt brief — team {ctx.team.name} — {now.isoformat(timespec='minutes')}"]
    if name:
        out[0] += f" — for {name}"

    from . import versions

    try:
        out.append(versions.current(ctx, live_names=set(live)).line())
    except Exception as e:  # a brief must always build
        out.append(f"xt versions: unknown ({type(e).__name__})")
    out.append("\n## Team")
    viewer = ctx.team.agent(name) if name else None
    # context usage is for whoever decides about resets: the human, the lead and the liaison
    show_context = name is None or name == HUMAN or (viewer is not None and viewer.role in ("lead", "liaison"))
    contexts = {}
    if show_context:
        from . import usage

        contexts = usage.readings(ctx, [a.name for a in ctx.team.agents() if a.kind != HUMAN and a.active])
    for a in ctx.team.agents():
        if a.kind == HUMAN or not a.active:
            continue
        la = live.get(a.name)
        state = la.status if la else "not running"
        wakes = f", woken {schedule_text(a)}" if a.wake_every else ""
        cx = (f", context {usage.compact(contexts[a.name])}"
              if la and a.name in contexts and contexts[a.name].known else "")
        out.append(f"- {a.name} ({a.role}, {harness_model(a.harness, a.model)}, reports to {a.reports_to}{wakes}{cx}): {state}")
    if show_context:
        from . import turns
        from .reset import suggestion

        out.append(f"Team usage today: {turns.fmt(turns.today(ctx).team_today)}")
        for n, r in contexts.items():
            tip = suggestion(n, r, now) if n in live else None
            if tip:
                out.append(tip)
    if viewer is not None and viewer.kind != HUMAN:
        from .reset import checkpoints

        out.append(f"Your notes: members/{name}/notes.md (read them after any restart or reset).")
        cp = checkpoints(ctx).get(name)
        if cp:
            out.append(f"Your last checkpoint ({cp['at'][:16].replace('T', ' ')}): {cp['summary']}")

    items = [i for i in ctx.ledger.open_items() if i["type"] != "ask"]  # questions: see below
    if name and name not in (HUMAN,) and ctx.team.agent(name) and ctx.team.agent(name).role not in ("lead", "liaison"):
        items = [i for i in items if i["owner"] == name or i["opener"] == name]
    out.append(f"\n## Open goals and tasks ({len(items)})")
    if not items:
        out.append("(none)")
    shown = items[-MAX_ITEMS:]
    if len(items) > MAX_ITEMS:
        out.append(f"({len(items) - MAX_ITEMS} older open items not shown — `xt log` for all)")
    for i in shown:
        goal = f" [goal #{i['goal']}]" if i.get("goal") else ""
        out.append(f"- #{i['id']} {i['type']} → {i['owner']}{goal}, open {_age(i['opened'], now)}: {i['title']}")

    if name == "liaison" or name is None:
        drafts = sorted(ctx.paths.drafts.glob("*.md")) if ctx.paths.drafts.exists() else []
        out.append(f"\n## Goal drafts ({len(drafts)})")
        out += [f"- {d.relative_to(ctx.paths.root)}" for d in drafts] or ["(none)"]

    agent = ctx.team.agent(name) if name else None
    if name is None or name == HUMAN or (agent and agent.role in ("liaison", "lead")):
        out += waiting_on_human(ctx)

    recent = [m for m in ctx.ledger.messages(since_days=1)]
    cutoff = (now - dt.timedelta(hours=24)).isoformat(timespec="seconds")
    recent = [m for m in recent if m["ts"] >= cutoff]
    if name:
        recent = [m for m in recent if name in (m["from"], m["to"])][-MEMBER_RECENT:]
    else:
        recent = recent[-RECENT:]
    out.append(f"\n## Recent messages ({len(recent)}, last 24h)")
    out += [_line(m) for m in recent] or ["(none)"]
    out.append(f"\nFull history: {ctx.paths.xt_bin} log --help")
    return "\n".join(out)


def waiting_on_human(ctx: Ctx) -> list[str]:
    """What only the human can resolve, with the exact commands, so the liaison can pass it on."""
    from .alerts import Alerts
    from .spawn import Approvals, approval_what

    approvals = Approvals(ctx).pending()
    alerts = Alerts(ctx).active()
    questions = [i for i in ctx.ledger.open_items() if i["type"] == "ask"]
    now = ctx.ledger.clock()
    out = [f"\n## Waiting on the human ({len(questions)} questions, {len(approvals)} approvals, "
           f"{len(alerts)} alerts)"]
    for q in questions:
        about = f" (about #{q['about']})" if q.get("about") is not None else ""
        out.append(f"- question #{q['id']} from {q['opener']}{about}, waiting {_age(q['opened'], now)}: {q['title']}")
    if questions:
        out.append("  → the human answers with `xt answer <id> \"...\"` (or `s` on it in the TUI's Inbox); "
                   "the answer reaches the asker as a report with --ref to the question. If the human "
                   "answers some other way, or the question is no longer needed, the asker closes it: "
                   "`xt done <id> --as <asker> \"why\"`. Work that waits on an open question is not nudged.")
    for rid, r in sorted(approvals.items(), key=lambda kv: int(kv[0])):
        out.append(f"- approval #{rid}: {r['requester']} asks to {approval_what(r)}")
    if approvals:
        ids = " ".join(sorted(approvals, key=int))
        out.append(f"  → the human approves with `xt approve {ids}` (or `a` on each in the TUI's Inbox), "
                   f"or denies with `xt deny <id>`")
    for key, a in sorted(alerts.items(), key=lambda kv: kv[1].get("id", 0)):
        out.append(f"- alert: {a['text']}  (clear: `xt clear {key}`, or `c` in the TUI's Inbox)")
    if not approvals and not alerts and not questions:
        out.append("(nothing)")
    return out
