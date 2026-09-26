"""Goal lifecycle: a draft shaped by the human and the liaison, dispatched to the lead."""

import datetime as dt
import re

from .context import Ctx
from .dispatch import deliver_or_queue, send
from .paths import XtError
from .spawn import do_spawn
from .team import HUMAN

TEMPLATE = """# {title}

## Outcome
What should exist or be true when this goal is done.

## Constraints
Deadlines, budget, tools or harnesses to use or avoid, data rules.

## Done when
How the human will judge it finished.

## Notes
Anything else from the conversation that the lead needs.
"""


def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    if not s:
        raise XtError("goal slug is empty")
    return s[:60]


def new(ctx: Ctx, slug: str, title: str | None) -> str:
    slug = slugify(slug)
    ctx.paths.drafts.mkdir(parents=True, exist_ok=True)
    f = ctx.paths.drafts / f"{slug}.md"
    if f.exists():
        return f"draft already exists: {f.relative_to(ctx.paths.root)}"
    f.write_text(TEMPLATE.format(title=title or slug.replace("-", " ").capitalize()))
    return f"created {f.relative_to(ctx.paths.root)} — fill it in with the human, then `xt goal dispatch {slug}`"


def _lead(ctx: Ctx):
    lead = ctx.team.lead_of_role("lead")
    if lead is None:
        raise XtError("no active agent with role 'lead' in team.toml")
    return lead


def dispatch(ctx: Ctx, sender: str, slug: str) -> str:
    slug = slugify(slug)
    s = ctx.team.agent(sender)
    if sender != HUMAN and (s is None or s.role != "liaison"):
        raise XtError("only the liaison (or the human) dispatches goals")
    draft = ctx.paths.drafts / f"{slug}.md"
    if not draft.exists():
        raise XtError(f"no draft goals/drafts/{slug}.md")
    final = ctx.paths.goals / f"{slug}.md"
    if final.exists():
        raise XtError(f"goals/{slug}.md already exists — pick another slug")
    text = draft.read_text()
    m = re.search(r"^#\s+(.+)$", text, re.M)
    title = m.group(1).strip() if m else slug
    lead = _lead(ctx)
    via = sender if sender != HUMAN else HUMAN
    body = f"{title}\nBrief: {final.relative_to(ctx.paths.root)} (read it before planning)"
    msg, _ = send(ctx, via, lead.name, "goal", body, deliver=False)
    final.write_text(text.rstrip() + f"\n\n---\nDispatched as goal #{msg['id']} by {sender} on {dt.date.today()}.\n")
    draft.unlink()
    if lead.name in ctx.herdr.agents():
        status = deliver_or_queue(ctx, msg)
        return f"goal #{msg['id']} dispatched to {lead.name}: {status}"
    if sender != HUMAN:
        # The liaison may be sandboxed (codex blocks Herdr): let the supervisor start the lead.
        from .jobs import Jobs

        Jobs(ctx).add("start", {"name": lead.name}, sender)
        return (f"goal #{msg['id']} dispatched; the supervisor starts {lead.name} within seconds "
                f"(the goal is in its first brief) and messages you")
    do_spawn(ctx, lead.name)
    return f"goal #{msg['id']} dispatched; started {lead.name} (the goal is in its first brief)"


def listing(ctx: Ctx) -> str:
    out = []
    drafts = sorted(ctx.paths.drafts.glob("*.md")) if ctx.paths.drafts.exists() else []
    out.append("Drafts:")
    out += [f"  {d.stem}" for d in drafts] or ["  (none)"]
    items = ctx.ledger.open_items()
    goals = [i for i in items if i["type"] == "goal"]
    out.append("Open goals:")
    for g in goals:
        tasks = [i for i in items if i["type"] == "task" and i.get("goal") == g["id"]]
        out.append(f"  #{g['id']} {g['title']} → {g['owner']} ({len(tasks)} open tasks)")
    if not goals:
        out.append("  (none)")
    return "\n".join(out)
