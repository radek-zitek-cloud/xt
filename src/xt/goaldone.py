"""Telling the human when a goal is done (card #125).

A goal the human dispatched is a goal the liaison opened. It gives the human exactly one
notification, when it's done: the liaison's report about it after the closure (a `report` to the
human whose `--ref` is the goal or the lead's `done`), or, if no such report arrives within
FALLBACK_SECONDS of the closure, the supervisor's own "goal done" with the first line of the
closing summary. Liaison reports about a goal that's still open don't notify. Other liaison
reports to the human (not about a goal) notify, deduplicated by their `ref`. The Inbox lists goals closed since the human
last looked (`state/inbox_seen.json`) until they've seen them."""

import json

from .context import Ctx
from .team import HUMAN

FALLBACK_SECONDS = 300  # the liaison's report normally follows the lead's `done` within a turn
NOTICES = "goal_notices.json"
SEEN = "inbox_seen.json"
KEEP_NOTIFIED = 500

_messages: dict[tuple[str, int], dict | None] = {}  # the log is append-only: a message never changes


def message(ctx: Ctx, msg_id, msgs=()) -> dict | None:
    if not isinstance(msg_id, int):
        return None
    for m in msgs:
        if m["id"] == msg_id:
            return m
    key = (str(ctx.paths.root), msg_id)
    if key not in _messages:
        _messages[key] = ctx.ledger.message(msg_id)
    return _messages[key]


def liaisons(ctx: Ctx) -> set[str]:
    return {a.name for a in ctx.team.agents() if a.role == "liaison"}


def liaison_goal(ctx: Ctx, goal_id, msgs=()) -> dict | None:
    """The goal message, when `goal_id` is a goal the liaison opened (one the human dispatched)."""
    m = message(ctx, goal_id, msgs)
    return m if m and m["type"] == "goal" and m["from"] in liaisons(ctx) else None


def goal_of_report(ctx: Ctx, m: dict, msgs=()) -> int | None:
    """The liaison goal a report is about: its ref is the goal, or the `done` that closed it."""
    ref = message(ctx, m.get("ref"), msgs)
    if ref and ref["type"] == "done":
        ref = message(ctx, ref.get("ref"), msgs)
    return ref["id"] if ref and liaison_goal(ctx, ref["id"], msgs) else None


def first_line(text: str, width: int = 180) -> str:
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return line if len(line) <= width else line[:width - 1] + "…"


class Notices:
    """The supervisor's goal-done bookkeeping: closures waiting for the liaison's report, and what
    has already notified (by goal, or by a report's ref)."""

    def __init__(self, ctx: Ctx):
        self.ctx = ctx
        self.path = ctx.paths.state / NOTICES
        try:
            d = json.loads(self.path.read_text())
        except (OSError, ValueError):
            d = {}
        self.pending: dict[str, dict] = d.get("pending", {})
        self.notified: list[str] = d.get("notified", [])

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"pending": self.pending, "notified": self.notified[-KEEP_NOTIFIED:]}))
        tmp.replace(self.path)

    def _once(self, key: str) -> bool:
        if key in self.notified:
            return False
        self.notified.append(key)
        return True

    def see(self, m: dict, now: float, msgs=()) -> tuple[str, str] | None:
        """Take in one new message; return (title, body) when it should notify the human."""
        ctx = self.ctx
        if m["type"] == "done" and liaison_goal(ctx, m.get("ref"), msgs):
            if f"goal:{m['ref']}" not in self.notified:
                self.pending[str(m["ref"])] = {"closed_at": now, "done": m["id"],
                                               "summary": first_line(m["body"])}
            return None
        if m["type"] != "report" or m["to"] != HUMAN or m["from"] not in liaisons(ctx):
            return None
        goal = goal_of_report(ctx, m, msgs)
        if goal is not None:
            # A goal notifies exactly once, when it's done (Radek's amendment, QA on rc3): the
            # liaison's report after the closure, else the fallback. Progress on an open goal, and
            # anything after the goal's one notification, stays in the Inbox only.
            if str(goal) not in self.pending:
                return None
            del self.pending[str(goal)]
            if self._once(f"goal:{goal}"):
                return f"goal #{goal} done", first_line(m["body"])
            return None
        if m.get("ref") is not None and not self._once(f"ref:{m['ref']}"):
            return None
        return f"report from {m['from']}", first_line(m["body"])

    def due(self, now: float) -> list[tuple[str, str]]:
        """Fallbacks: closed goals the liaison hasn't reported within FALLBACK_SECONDS."""
        out = []
        for goal, p in list(self.pending.items()):
            if now - p["closed_at"] < FALLBACK_SECONDS:
                continue
            del self.pending[goal]
            if self._once(f"goal:{goal}"):
                out.append((f"goal #{goal} done", p["summary"]))
        return out


# --- the Inbox's "Done since you last looked" -----------------------------------------------------


def seen_upto(ctx: Ctx) -> int:
    """The last message id the human has seen the Inbox's done goals up to. Starts at the current
    end of the log, so a team upgrading to 0.15.0 isn't shown its whole history."""
    path = ctx.paths.state / SEEN
    try:
        return int(json.loads(path.read_text())["upto"])
    except (OSError, ValueError, KeyError, TypeError):
        upto = ctx.ledger.last_id()
        mark_seen(ctx, upto)
        return upto


def mark_seen(ctx: Ctx, upto: int) -> None:
    path = ctx.paths.state / SEEN
    try:
        old = int(json.loads(path.read_text())["upto"])
    except (OSError, ValueError, KeyError, TypeError):
        old = 0
    if upto > old or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"upto": max(upto, old)}))
        tmp.replace(path)


def done_since(ctx: Ctx, msgs: list[dict]) -> tuple[list[tuple[dict, dict]], int]:
    """Goals the human dispatched that closed since they last looked: [(goal, done)], oldest first,
    and the id to mark as seen once they have looked (the newest message considered)."""
    upto = seen_upto(ctx)
    out = [(goal, m) for m in msgs
           if m["id"] > upto and m["type"] == "done" and (goal := liaison_goal(ctx, m.get("ref"), msgs))]
    newest = max((m["id"] for m in msgs), default=upto)
    return out, max(newest, upto)
