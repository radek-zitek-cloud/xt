"""The human's Inbox in three groups (card #127), the same for the TUI and `xt inbox`.

- **Needs you**: open questions, pending approvals and active alerts. They stay until answered,
  decided or cleared at the source.
- **New**: goals the human dispatched that closed, and reports (`report` or `done`) to the human,
  since the human last looked: the done marker of card #125 (`goaldone.seen_upto`). What New
  showed before that marker, from the last seven days, the TUI keeps folded under it (card #157).
- **Friction**: unread friction only; seen friction is counted and folded.

Friction's read state sits next to the done marker in `state/inbox_seen.json`: every friction up to
`friction_upto` is seen, and so is every id in `friction_seen` (friction seen one by one above it).
On the first run `friction_upto` is the end of the log, so an upgraded team starts with no unread
friction. Only the human marks friction seen: the TUI for the friction rows it showed while the
human had the Inbox focused (when they leave it or quit) and `c` on one row, and `xt inbox` in the
human's own terminal for the friction it printed. An agent's `xt inbox` changes nothing.
"""

import datetime as dt
from dataclasses import dataclass, field

from .alerts import Alerts
from .context import Ctx
from .goaldone import done_since, liaison_goal, load_seen, save_seen, seen_upto
from .spawn import Approvals
from .team import HUMAN

KEEP_SEEN = 1000  # friction ids kept one by one; older ones fold into friction_upto
NEW_TYPES = ("report", "done")  # what counts as a report to the human in New
EARLIER_DAYS = 7  # how far back the TUI's `(N earlier, seen)` fold under New reaches (card #157)


@dataclass
class Inbox:
    questions: list[dict] = field(default_factory=list)  # open `ask` items, oldest first
    approvals: list[tuple[str, dict]] = field(default_factory=list)  # (id, request)
    alerts: list[tuple[str, dict]] = field(default_factory=list)  # (key, alert)
    new: list[tuple[dict, dict | None]] = field(default_factory=list)  # (message, goal if a done goal), newest first
    unread: list[dict] = field(default_factory=list)  # unread friction, newest first
    seen: list[dict] = field(default_factory=list)  # seen friction, newest first
    earlier: list[tuple[dict, dict | None]] = field(default_factory=list)  # New items seen, last 7 days (#157)
    upto: int = 0  # the done marker to set once the human has looked

    @property
    def counts(self) -> tuple[int, int, int]:
        """(needs you, new, unread friction)."""
        return len(self.questions) + len(self.approvals) + len(self.alerts), len(self.new), len(self.unread)

    def title(self) -> str:
        """`⚑ 1 · ✉ 2 · ✱ 1`, leaving out a zero count."""
        return " · ".join(f"{g} {n}" for g, n in zip("⚑✉✱", self.counts) if n)


def friction_marker(ctx: Ctx) -> tuple[int, set[int]]:
    """(friction_upto, ids seen above it). The first call sets friction_upto to the end of the log."""
    d = load_seen(ctx)
    try:
        upto = int(d["friction_upto"])
    except (ValueError, KeyError, TypeError):
        upto = ctx.ledger.last_id()
        d["friction_upto"], d["friction_seen"] = upto, []
        save_seen(ctx, d)
    seen = {i for i in d.get("friction_seen") or [] if isinstance(i, int)}
    return upto, seen


def mark_friction_seen(ctx: Ctx, ids) -> None:
    """Record these friction ids as seen (the human's look only; callers check who is looking)."""
    upto, seen = friction_marker(ctx)
    new = {int(i) for i in ids if int(i) > upto} - seen
    if not new:
        return
    seen = sorted(seen | new)
    if len(seen) > KEEP_SEEN:
        upto = seen[-KEEP_SEEN - 1]
        seen = seen[-KEEP_SEEN:]
    d = load_seen(ctx)
    d["friction_upto"], d["friction_seen"] = upto, seen
    save_seen(ctx, d)


def earlier(ctx: Ctx, msgs: list[dict], open_ids: set[int], upto: int) -> list[tuple[dict, dict | None]]:
    """What New showed and the human has since seen (up to the done marker), from the last
    EARLIER_DAYS: [(message, goal if a done goal)], newest first. The TUI folds them under New
    (card #157); nothing is stored for it."""
    since = ctx.ledger.clock() - dt.timedelta(days=EARLIER_DAYS)

    def recent(m: dict) -> bool:
        try:
            return dt.datetime.fromisoformat(m["ts"]) >= since
        except (KeyError, TypeError, ValueError):
            return False

    out = []
    for m in msgs:
        if m["id"] > upto or not recent(m):
            continue
        if m["type"] == "done" and (goal := liaison_goal(ctx, m.get("ref"), msgs)):
            out.append((m, goal))
        elif m["to"] == HUMAN and m["type"] in NEW_TYPES and m["id"] not in open_ids:
            out.append((m, None))
    return out[::-1]


def build(ctx: Ctx, msgs: list[dict], open_items: list[dict] | None = None) -> Inbox:
    """The Inbox from the recent messages `msgs` (oldest first)."""
    if open_items is None:
        open_items = ctx.ledger.open_items()
    open_ids = {i["id"] for i in open_items}
    box = Inbox()
    box.questions = [i for i in open_items if i["type"] == "ask"]
    box.approvals = sorted(Approvals(ctx).pending().items(), key=lambda kv: int(kv[0]))
    box.alerts = sorted(Alerts(ctx).active().items(), key=lambda kv: kv[1].get("id", 0))
    done, box.upto = done_since(ctx, msgs)
    upto = seen_upto(ctx)  # the marker before this look (done_since has set it on a first run)
    new = [(d, g) for g, d in done]
    new += [(m, None) for m in msgs if m["id"] > upto and m["to"] == HUMAN and m["type"] in NEW_TYPES
            and m["id"] not in open_ids]
    box.new = sorted(new, key=lambda p: -p[0]["id"])
    box.earlier = earlier(ctx, msgs, open_ids, upto)
    f_upto, f_seen = friction_marker(ctx)
    friction = [m for m in msgs if m["type"] == "friction"][::-1]
    box.unread = [m for m in friction if m["id"] > f_upto and m["id"] not in f_seen]
    box.seen = [m for m in friction if m["id"] <= f_upto or m["id"] in f_seen]
    return box
