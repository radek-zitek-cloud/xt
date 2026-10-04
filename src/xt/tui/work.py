"""The Work pane (card #129): goals and their tasks as one two-level outline.

Level 1 is goals, level 2 their tasks. A task belongs to the goal at the root of its `ref` chain
(through other tasks or messages); a task with no goal the chain reaches sits under a final
`no goal` row. Open goals come first, expanded, newest activity first, their tasks newest first
(card #162); done goals sit under one
`done (N)` fold, collapsed. The model builds every row once; the pane decides which are shown
(fold state, open-only) and lays each out at its width.
"""

import re
from dataclasses import dataclass, field

from rich.text import Text

from .model import fit

OPEN, DONE, FAILED = "●", "✓", "✗"
GLYPH_STYLE = {OPEN: "yellow", DONE: "green", FAILED: "red"}
DONE_FOLD, NO_GOAL = "fold:done", "nogoal"
INDENT = "    "
INDENT_LEN = len(INDENT)
MIN_TEXT = 16  # cells a goal's first line keeps before its owner column gives way
# a task closed with a failed or blocked result: its `done` starts with the verdict word
FAILED_DONE = re.compile(r"^\W*(FAIL|FAILED|BLOCKED)\b")


@dataclass
class Task:
    msg: dict
    state: str  # OPEN, DONE or FAILED


@dataclass
class Goal:
    msg: dict
    open: bool
    tasks: list[Task] = field(default_factory=list)
    newest: str = ""  # ts of the newest message anywhere under the goal
    # card #185: tasks the lead opened after the goal closed; listed below its own tasks, and left
    # out of its count and its newest activity, so the closed goal's row stays as it was
    follow_ups: list[Task] = field(default_factory=list)

    @property
    def done_n(self) -> int:
        return sum(1 for t in self.tasks if t.state != OPEN)


@dataclass
class Outline:
    open: list[Goal]  # newest activity first
    done: list[Goal]  # newest activity first
    orphans: list[Task]  # tasks with no goal they can reach


def root_goal(mid: int, by_id: dict[int, dict]) -> int | None:
    """The goal at the root of a message's `ref` chain, or None when the chain ends elsewhere
    (no ref, or a message the TUI doesn't have)."""
    seen = set()
    m = by_id.get(mid)
    while m is not None and m["id"] not in seen:
        if m["type"] == "goal":
            return m["id"]
        seen.add(m["id"])
        if m.get("ref") is None:
            return None
        m = by_id.get(m["ref"])
    return None


def under_follow_up(mid: int, by_id: dict[int, dict]) -> bool:
    """Whether a message is a follow-up task (card #185) or reaches one through its `ref` chain."""
    seen = set()
    m = by_id.get(mid)
    while m is not None and m["id"] not in seen and m["type"] != "goal":
        if m.get("follow_up"):
            return True
        seen.add(m["id"])
        m = by_id.get(m["ref"]) if m.get("ref") is not None else None
    return False


def outline(msgs: list[dict], open_items: dict[int, dict], blocked: set[str]) -> Outline:
    """Goals, their tasks and the orphans. Open goals and tasks older than the messages read are
    added from the ledger's open items, so an old open goal still shows."""
    msgs = list(msgs)
    have = {m["id"] for m in msgs}
    for i in open_items.values():
        if i["type"] in ("goal", "task") and i["id"] not in have:
            msgs.append({"id": i["id"], "ts": i["opened"], "type": i["type"], "from": i["opener"],
                         "to": i["owner"], "ref": i.get("goal"), "body": i["title"],
                         **({"follow_up": True} if i.get("follow_up") else {})})
    msgs.sort(key=lambda m: m["id"])
    by_id = {m["id"]: m for m in msgs}
    roots = {m["id"]: root_goal(m["id"], by_id) for m in msgs}
    closing: dict[int, dict] = {}  # the `done` that closed each goal or task
    goal_newest: dict[int, str] = {}
    for m in msgs:
        if m["type"] == "done" and m.get("ref") is not None:
            closing[m["ref"]] = m
        g = roots[m["id"]]
        if g is not None and not under_follow_up(m["id"], by_id):
            goal_newest[g] = max(goal_newest.get(g, ""), m["ts"])

    goals = {m["id"]: Goal(m, m["id"] in open_items, newest=goal_newest.get(m["id"], m["ts"]))
             for m in msgs if m["type"] == "goal"}
    orphans = []
    for m in msgs:
        if m["type"] != "task":
            continue
        if m["id"] in open_items:
            state = FAILED if m["to"] in blocked else OPEN
        else:
            end = closing.get(m["id"])
            state = FAILED if end and FAILED_DONE.match(end["body"]) else DONE
        g = roots[m["id"]]
        if g in goals:
            (goals[g].follow_ups if m.get("follow_up") else goals[g].tasks).append(Task(m, state))
        else:
            orphans.append(Task(m, state))
    newest_first = lambda gs: sorted(gs, key=lambda g: (g.newest, g.msg["id"]), reverse=True)
    return Outline(newest_first(g for g in goals.values() if g.open),
                   newest_first(g for g in goals.values() if not g.open), orphans)


def line(text: Text, data: dict, age: str, width: int, expanded: bool) -> Text:
    """One Work row at the pane's width: the fold mark or indent, the text cut with `…` only when it
    doesn't fit, then the goal's owner and `done/total` (never cut; in a narrow pane the owner goes
    first), then the age (#132's helper)."""
    head = Text(no_wrap=True)
    short = data.get("short")  # card #185: the same row in shorter words, before any `…`
    if short is not None and INDENT_LEN + text.cell_len + (len(age) + 1 if age else 0) > width:
        text = short
    if data.get("level") == 2:
        head.append(INDENT)
    elif data.get("foldable"):
        head.append("▾ " if expanded else "▸ ", style="bright_black")
    head.append_text(text)
    for tail in (data.get("tail"), data.get("count")):
        if not tail:
            continue
        room = width - tail.cell_len - (len(age) + 1 if age else 0)
        if room >= MIN_TEXT:
            head = fit(head, "", room)
            head.append(" " * (room - head.cell_len))
            return fit(head + tail, age, width)
    return fit(head, age, width)
