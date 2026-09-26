"""`xt brief`: a recovery summary built only from repo files and Herdr, sized for a prompt (~2k tokens)."""

import datetime as dt

from .context import Ctx
from .team import HUMAN

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

    out.append("\n## Team")
    for a in ctx.team.agents():
        if a.kind == HUMAN or not a.active:
            continue
        la = live.get(a.name)
        state = la.status if la else "not running"
        model = f"/{a.model}" if a.model else ""
        out.append(f"- {a.name} ({a.role}, {a.harness}{model}, reports to {a.reports_to}): {state}")

    items = ctx.ledger.open_items()
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
