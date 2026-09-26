"""`xt send`: policy check, log, then deliver now or queue until the target is idle."""

import json
import os

from .context import Ctx
from .herdr import DELIVERABLE, HerdrError
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

    def remove(self, msg_id: int) -> None:
        with self.ctx.ledger.lock():
            self._save([i for i in self._load() if i["id"] != msg_id])

    def set_reason(self, msg_id: int, reason: str) -> None:
        with self.ctx.ledger.lock():
            items = self._load()
            for i in items:
                if i["id"] == msg_id:
                    i["reason"] = reason
            self._save(items)


def deliver_or_queue(ctx: Ctx, msg: dict) -> str:
    """Deliver now if the target is idle, else queue. Returns a short status string."""
    to = msg["to"]
    if to == HUMAN:
        return "for human (see `xt inbox` / TUI)"
    q = Queue(ctx)
    if any(i["to"] == to for i in q.pending()):
        q.add(msg["id"], to, "behind earlier queued messages")
        return f"queued (earlier messages to {to} still waiting)"
    status = ctx.herdr.status(to)
    if status in DELIVERABLE:
        try:
            ctx.herdr.prompt(to, envelope(ctx, msg))
            return "delivered"
        except HerdrError as e:
            q.add(msg["id"], to, f"delivery failed: {e.code}")
            return f"queued ({e.code})"
    reason = "not running" if status is None else status
    q.add(msg["id"], to, reason)
    return f"queued ({to} is {reason})"


def send(
    ctx: Ctx, sender: str, to: str, mtype: str, body: str, ref: int | None = None, deliver: bool = True
) -> tuple[dict, str]:
    body = body.strip()
    if not body:
        raise XtError("empty message")
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
            raise XtError(f"#{ref} is not an open goal or task")
        if item["owner"] != sender and sender != HUMAN:
            raise XtError(f"#{ref} is owned by {item['owner']}, not {sender}")
        if item["opener"] != to and sender != HUMAN:
            raise XtError(f"report done for #{ref} to {item['opener']}, who opened it")
    if mtype == "task" and ref is not None:
        item = ctx.ledger.item(ref)
        if item is None or item["type"] != "goal":
            raise XtError(f"--ref for a task must be an open goal id; #{ref} isn't one")
    msg = ctx.ledger.append(sender, to, mtype, body, ref)
    status = deliver_or_queue(ctx, msg) if deliver else "logged"
    return msg, status


def drain(ctx: Ctx) -> list[str]:
    """Deliver queued messages whose target has gone idle. Oldest first, one per target per pass."""
    out = []
    q = Queue(ctx)
    live = ctx.herdr.agents()
    seen: set[str] = set()
    for item in sorted(q.pending(), key=lambda i: i["id"]):
        to = item["to"]
        if to in seen:
            continue
        agent = live.get(to)
        if agent is None or agent.status not in DELIVERABLE:
            continue
        msg = ctx.ledger.message(item["id"])
        if msg is None:
            q.remove(item["id"])
            continue
        seen.add(to)
        try:
            ctx.herdr.prompt(to, envelope(ctx, msg))
            q.remove(item["id"])
            out.append(f"delivered #{msg['id']} to {to}")
        except HerdrError as e:
            q.set_reason(item["id"], f"delivery failed: {e.code}")
    return out
