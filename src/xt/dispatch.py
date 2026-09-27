"""`xt send`: policy check, log, then deliver now or queue until the target is idle."""

import json
import os

from .context import Ctx
from .herdr import DELIVERABLE
from .ledger import AGENT_TYPES
from .paths import XtError
from .team import HUMAN, SYSTEM, Team


def may_send(team: Team, sender: str, to: str, mtype: str = "report") -> bool:
    try:
        check_policy(team, sender, to, mtype)
        return True
    except XtError:
        return False


def check_policy(team: Team, sender: str, to: str, mtype: str) -> None:
    if sender == SYSTEM:
        return
    s, t = team.agent(sender), team.agent(to)
    if s is None or not s.active:
        raise XtError(f"sender {sender!r} is not an active member of this team")
    if t is None or not t.active:
        raise XtError(f"recipient {to!r} is not an active member of this team")
    if sender == to:
        raise XtError("can't send a message to yourself")
    if mtype not in AGENT_TYPES:
        raise XtError(f"agents send only {', '.join(AGENT_TYPES)} messages")
    if sender == HUMAN:
        return
    downward = t.reports_to == sender
    upward = s.reports_to == to
    if not (downward or upward):
        up = s.reports_to or "nobody"
        down = ", ".join(a.name for a in team.reports(sender)) or "nobody"
        raise XtError(
            f"{sender} may only message {up} (reports_to) and its own reports ({down}), not {to}"
        )
    if mtype == "goal" and not (downward and s.role == "liaison"):
        raise XtError("only the liaison (or the human) opens goals, and only towards the lead")
    if mtype == "task" and not downward:
        raise XtError(f"tasks go downward only; {to} doesn't report to {sender}")


def envelope(ctx: Ctx, msg: dict) -> str:
    ref = f" ref:#{msg['ref']}" if msg.get("ref") is not None else ""
    head = f"[xt #{msg['id']} {msg['type']} from:{msg['from']} to:{msg['to']}{ref}]"
    text = f"{head}\n{msg['body']}"
    if msg["from"] != SYSTEM and may_send(ctx.team, msg["to"], msg["from"]):
        text += (
            f"\n\n(reply: {ctx.paths.xt_bin} send {msg['from']} --as {msg['to']} "
            f"--type report --ref {msg['id']} \"...\""
        )
        if msg["type"] in ("goal", "task"):
            text += f"; when finished: --type done --ref {msg['id']}"
        text += ")"
    return text


class Queue:
    def __init__(self, ctx: Ctx):
        self.path = ctx.paths.state / "queue.json"
        self.ctx = ctx

    def _load(self) -> list[dict]:
        return json.loads(self.path.read_text()) if self.path.exists() else []

    def _save(self, items: list[dict]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, indent=1))
        os.replace(tmp, self.path)

    def pending(self) -> list[dict]:
        with self.ctx.ledger.lock():
            return self._load()

    def add(self, msg_id: int, to: str, reason: str) -> None:
        with self.ctx.ledger.lock():
            items = self._load()
            items.append({"id": msg_id, "to": to, "reason": reason})
            self._save(items)

    def remove_many(self, ids: set[int]) -> None:
        with self.ctx.ledger.lock():
            self._save([i for i in self._load() if i["id"] not in ids])

    def set_reason(self, ids: set[int], reason: str) -> None:
        with self.ctx.ledger.lock():
            items = self._load()
            for i in items:
                if i["id"] in ids:
                    i["reason"] = reason
            self._save(items)


def _stale_note(ctx: Ctx, msg: dict, open_ids: set[int]) -> str | None:
    """Say so when a queued message is about a goal/task that has since been closed."""
    if msg["type"] in ("goal", "task") and msg["id"] not in open_ids:
        return f"#{msg['id']} has since been closed"
    ref = msg.get("ref")
    if ref is not None and ref not in open_ids:
        target = ctx.ledger.message(ref)
        if target and target["type"] in ("goal", "task"):
            return f"it's about #{ref}, which has since been closed"
    return None


def batch_text(ctx: Ctx, msgs: list[dict]) -> str:
    """One prompt for everything waiting for an agent, instead of one wake-up per message."""
    if len(msgs) == 1:
        return envelope(ctx, msgs[0])
    open_ids = {i["id"] for i in ctx.ledger.open_items()}
    parts = [
        f"[xt: {len(msgs)} messages arrived while you were busy, oldest first. Read them all before "
        f"acting; messages marked stale need no action unless something is still wrong.]"
    ]
    for m in msgs:
        stale = _stale_note(ctx, m, open_ids)
        prefix = f"(stale: {stale})\n" if stale else ""
        parts.append(prefix + envelope(ctx, m))
    return "\n\n---\n\n".join(parts)


def _deliver_batch(ctx: Ctx, to: str, msgs: list[dict]) -> None:
    ctx.herdr.prompt(to, batch_text(ctx, msgs))


def deliver_or_queue(ctx: Ctx, msg: dict) -> str:
    """Deliver now if the target is idle (together with anything already queued for it), else
    queue. Returns a short status string."""
    to = msg["to"]
    if to == HUMAN:
        return "for human (see `xt inbox` / TUI)"
    q = Queue(ctx)
    if msg["from"] not in (HUMAN, SYSTEM):
        # Agents never call Herdr: their harness may sandbox the shell (codex blocks Herdr's
        # socket). The supervisor, which runs unsandboxed, delivers within a few seconds.
        q.add(msg["id"], to, "waiting for the supervisor")
        return "queued (the supervisor delivers it within seconds)"
    try:
        status = ctx.herdr.status(to)
    except XtError as e:
        q.add(msg["id"], to, "Herdr unreachable from the sender")
        return f"queued (Herdr unreachable here: {str(e)[:80]})"
    if status in DELIVERABLE:
        waiting = sorted((i["id"] for i in q.pending() if i["to"] == to))
        batch = [m for m in (ctx.ledger.message(i) for i in waiting) if m] + [msg]
        try:
            _deliver_batch(ctx, to, batch)
            q.remove_many(set(waiting))
            return "delivered" if len(batch) == 1 else f"delivered with {len(batch) - 1} earlier queued"
        except XtError as e:
            code = getattr(e, "code", "herdr error")
            q.add(msg["id"], to, f"delivery failed: {code}")
            return f"queued ({code})"
    reason = "not running" if status is None else status
    q.add(msg["id"], to, reason)
    return f"queued ({to} is {reason})"


def done_recipient(team: Team, sender: str, item: dict) -> str:
    """Whoever opened the item, if the sender may message them; otherwise up the sender's chain
    (e.g. a goal the human dispatched directly: the lead reports done to the liaison)."""
    opener = item["opener"]
    if item["type"] == "ask" and sender == opener:
        return item["owner"]  # the asker withdraws its question: tell the human
    if sender == HUMAN or may_send(team, sender, opener, "done"):
        return opener
    s = team.agent(sender)
    if s and s.reports_to:
        return s.reports_to
    return opener


def send(
    ctx: Ctx, sender: str, to: str, mtype: str, body: str, ref: int | None = None, deliver: bool = True
) -> tuple[dict, str]:
    body = body.strip()
    if not body:
        raise XtError("empty message")
    if mtype == "note":
        s = ctx.team.agent(sender)
        if sender != SYSTEM and (s is None or not s.active):
            raise XtError(f"sender {sender!r} is not an active member of this team")
        msg = ctx.ledger.append(sender, sender, "note", body, ref)
        return msg, "noted (logged, not delivered)"
    check_policy(ctx.team, sender, to, mtype)
    limit = int(ctx.team.log_setting("message_max_kb")) * 1024
    if sender != SYSTEM and len(body.encode()) > limit:
        raise XtError(
            f"message is {len(body.encode())} bytes, over the {limit} limit — "
            "write the payload to a file and send its path instead"
        )
    if mtype == "done":
        if ref is None:
            raise XtError("a done message needs --ref <open goal or task id>")
        item = ctx.ledger.item(ref)
        if item is None:
            raise XtError(f"#{ref} is not an open goal, task or question")
        asker = item["type"] == "ask" and item["opener"] == sender
        if item["owner"] != sender and sender != HUMAN and not asker:
            raise XtError(f"#{ref} is owned by {item['owner']}, not {sender}")
        expected = done_recipient(ctx.team, sender, item)
        if to != expected and sender != HUMAN:
            raise XtError(f"report done for #{ref} to {expected} (`xt done {ref}` picks the right recipient)")
    if mtype == "task" and ref is not None:
        item = ctx.ledger.item(ref)
        if item is None or item["type"] != "goal":
            raise XtError(f"--ref for a task must be an open goal id; #{ref} isn't one")
    closing_goal = mtype == "done" and ctx.ledger.item(ref) and ctx.ledger.item(ref)["type"] == "goal"
    msg = ctx.ledger.append(sender, to, mtype, body, ref)
    if closing_goal:
        close_leftover_tasks(ctx, ref)
    status = deliver_or_queue(ctx, msg) if deliver else "logged"
    return msg, status


def waiting_on_human(ctx: Ctx) -> dict[int, int]:
    """Open items that wait on an open question to the human: {item id: question id}. A question
    counts for the item it refers to and for what that message refers to, a few hops up (the
    liaison asks about the lead's report, which is about a goal)."""
    out: dict[int, int] = {}
    items = ctx.ledger.open_items()
    open_ids = {i["id"] for i in items}
    for q in (i for i in items if i["type"] == "ask"):
        ref, hops = q.get("about"), 0
        while ref is not None and hops < 4:
            if ref in open_ids:
                out.setdefault(ref, q["id"])
            m = ctx.ledger.message(ref)
            ref, hops = (m.get("ref") if m else None), hops + 1
    return out


def close_leftover_tasks(ctx: Ctx, goal_id: int) -> list[int]:
    """A goal is done, so any task still open under it is finished or superseded (e.g. a first
    review task left open after a re-review). Close them in the ledger with a note; nobody is woken."""
    closed = []
    for item in ctx.ledger.open_items():
        if item["type"] == "task" and item.get("goal") == goal_id:
            ctx.ledger.append(SYSTEM, item["owner"], "done",
                              f"Closed automatically: goal #{goal_id} is done.", item["id"])
            closed.append(item["id"])
    return closed


def drain(ctx: Ctx) -> list[str]:
    """Deliver everything queued for each target that has gone idle, as one batch per target."""
    out = []
    q = Queue(ctx)
    live = ctx.herdr.agents()
    by_target: dict[str, list[int]] = {}
    for item in sorted(q.pending(), key=lambda i: i["id"]):
        by_target.setdefault(item["to"], []).append(item["id"])
    for to, ids in by_target.items():
        agent = live.get(to)
        if agent is None or agent.status not in DELIVERABLE:
            continue
        msgs = [m for m in (ctx.ledger.message(i) for i in ids) if m]
        if not msgs:
            q.remove_many(set(ids))
            continue
        try:
            _deliver_batch(ctx, to, msgs)
            q.remove_many(set(ids))
            out.append(f"delivered {', '.join('#' + str(m['id']) for m in msgs)} to {to}")
        except XtError as e:
            q.set_reason(set(ids), f"delivery failed: {getattr(e, 'code', 'herdr error')}")
    return out
