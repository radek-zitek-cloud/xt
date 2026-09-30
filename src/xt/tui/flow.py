"""Flow (card #130): the ledger as a swim-lane sequence chart, in place of the Log pane.

One lane per agent, left to right: `human`, then `xt` when it sent a shown message, then the
reporting chain (liaison, lead), then the other agents in roster order, then (dim) agents no longer
on the team that appear in the rows on screen. Time runs up a 6-cell column on the left, newest on
top (card #162), with a `── Sep 29 ──` row over each day's rows. Each message is one row: an arrow from the
sender's lane to the receiver's, its type glyph and label at the sender end, the arrowhead at the
receiver end, dotted when the receiver is the human; then, in the right margin, `#id` and the body's
first line cut at the pane width (the #132 row helper). Flow rows carry a clock time, not an age.

Lanes that don't fit collapse into one `+N` lane; a pane narrower than NARROW shows one line per
message instead (list mode).

Pure functions of the messages, the roster and the width, so the drawing is testable without a
terminal; the pane itself (selection, scrolling, filters) is `FlowPane` in app.py.
"""

import datetime as dt
from dataclasses import dataclass, field
from typing import Callable

from rich.text import Text

HUMAN, SYSTEM = "human", "xt"  # as team.HUMAN and team.SYSTEM
SYSTEM_LINES = ("system", "wake", "nudge")  # the only types xt writes that `t` hides
CHAIN = ("liaison", "lead")  # the reporting chain's roles, in lane order
GLYPH = {"goal": "◆", "task": "▸", "done": "◇", "report": "✉", "ask": "⚑", "approval": "⚑",
         "friction": "✱", "alert": "⚠", "note": "○"}
# colour by type as the Log had it; the alert is amber (bold yellow), apart from friction's magenta
STYLE = {"goal": "magenta", "task": "magenta", "done": "green", "report": "cyan", "ask": "cyan",
         "approval": "yellow", "friction": "magenta", "alert": "bold yellow", "note": "bright_black",
         "system": "bright_black", "wake": "bright_black", "nudge": "bright_black"}
TIME = 6  # "HH:MM "
MARGIN = 16  # cells the margin keeps at least
LANE_MIN, LANE_MAX = 9, 12
# Below this the pane is a list. The spec's floor is the time column, human plus two lanes and the
# margin (49 cells); its check 8 wants list mode at 60x20 too, where the full-width pane has 58 cells,
# so the chart starts at 60.
NARROW = max(TIME + 3 * LANE_MIN + MARGIN, 60)
SELECTED = "bold bright_white on blue"


@dataclass
class Data:
    """What Flow draws: the messages (oldest first; the pane lists them newest first), the roster,
    and each message's detail."""

    msgs: list[dict] = field(default_factory=list)
    roster: list[tuple[str, str, bool]] = field(default_factory=list)  # (name, role, active), team order
    detail: Callable[[dict], object] | None = None
    now: dt.datetime | None = None


@dataclass
class Lane:
    name: str
    dim: bool = False  # retired or unknown
    members: tuple[str, ...] = ()  # the `+N` lane: the agents collapsed into it


@dataclass
class Chart:
    lanes: list[Lane]
    width: int  # of each lane, in cells
    where: dict[str, int]  # agent → lane index

    @property
    def collapsed(self) -> tuple[str, ...]:
        return self.lanes[-1].members if self.lanes else ()


def is_system(m: dict) -> bool:
    return m.get("type") in SYSTEM_LINES


def glyph(m: dict) -> tuple[str, str, str]:
    """(glyph, label, style) for a message's type; a message the human typed is `○`."""
    kind = m.get("type") or "?"
    if m.get("from") == HUMAN:
        return "○", kind, ""
    if kind in GLYPH:
        return GLYPH[kind], kind, STYLE.get(kind, "")
    if kind in SYSTEM_LINES:
        return "○", kind, STYLE[kind]
    return "•", kind, ""  # a type this version doesn't know: drawn as best it can


def lanes(roster: list[tuple[str, str, bool]], shown: list[dict], visible: list[dict] | None = None) -> list[Lane]:
    """Every lane in order, before any collapse. `shown` are the messages that pass the system
    toggle: the `xt` lane depends on them, the agent and goal filters don't. `visible` are the
    message rows on screen (after every filter and the viewport; default `shown`): a retired or
    unknown agent gets its dim lane only while one of its rows is among them."""
    out = [Lane(HUMAN)]
    if any(m.get("from") == SYSTEM for m in shown):
        out.append(Lane(SYSTEM))
    active = [(n, r) for n, r, a in roster if a and n not in (HUMAN, SYSTEM)]
    for role in CHAIN:
        out += [Lane(n) for n, r in active if r == role]
    out += [Lane(n) for n, r in active if r not in CHAIN]
    have = {lane.name for lane in out}
    for m in shown if visible is None else visible:
        for n in (m.get("from"), m.get("to")):
            if n and n not in have:
                out.append(Lane(n, dim=True))
                have.add(n)
    return out


def chart(all_lanes: list[Lane], width: int) -> Chart | None:
    """The lanes that fit `width` (the rest in one `+N` lane) and their width; None: list mode."""
    if width < NARROW or not all_lanes:
        return None
    room = width - TIME - MARGIN
    kept = all_lanes
    if len(all_lanes) * LANE_MIN > room:
        k = max(1, room // LANE_MIN - 1)
        rest = all_lanes[k:]
        kept = all_lanes[:k] + [Lane(f"+{len(rest)}", members=tuple(lane.name for lane in rest))]
    lw = max(LANE_MIN, min(LANE_MAX, room // len(kept)))
    where = {}
    for i, lane in enumerate(kept):
        for name in lane.members or (lane.name,):
            where[name] = i
    return Chart(kept, lw, where)


def local(m: dict) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(m["ts"]).astimezone()
    except (KeyError, TypeError, ValueError):
        return None


def clock(m: dict) -> str:
    when = local(m)
    return when.strftime("%H:%M") if when else "--:--"


def first_line(m: dict) -> str:
    body = m.get("body") or ""
    return body.strip().splitlines()[0] if body.strip() else ""


def entries(msgs: list[dict], now: dt.datetime | None) -> list[tuple[str, object]]:
    """The pane's rows, in the order of `msgs` (Flow passes them newest first): ("msg", message),
    and ("day", date) over the first row of each day (over the first row too when it isn't today)."""
    today = (now or dt.datetime.now()).astimezone().date()
    out: list[tuple[str, object]] = []
    prev = None
    for m in msgs:
        when = local(m)
        day = when.date() if when else prev
        if day is not None and day != prev and (prev is not None or day != today):
            out.append(("day", day))
        prev = day
        out.append(("msg", m))
    return out


def fit(text: Text, width: int) -> Text:
    from .model import fit as fit_row  # model imports this module

    return fit_row(text, "", width)


def header(c: Chart, width: int) -> Text:
    out = Text("time".ljust(TIME), style="bright_black")
    for lane in c.lanes:
        name = lane.name if len(lane.name) <= c.width - 1 else lane.name[: c.width - 2] + "…"
        out.append(name.ljust(c.width), style="bright_black" if lane.dim else "bold")
    return fit(out, width)


def separator(day: dt.date, width: int) -> Text:
    return fit(Text(f"── {day:%b} {day.day} ──", style="bright_black"), width)


def ends(m: dict, c: Chart) -> tuple[int, int]:
    """The sender's and receiver's lanes. No receiver (or an unknown one): the sender's own lane."""
    src, dst = c.where.get(m.get("from") or ""), c.where.get(m.get("to") or "")
    if src is None:
        src = dst if dst is not None else 0
    return src, src if dst is None else dst


def arrow(m: dict, c: Chart) -> Text:
    """The lanes part of a row: the glyph and label at the sender, the arrowhead at the receiver."""
    g, label, style = glyph(m)
    total = len(c.lanes) * c.width
    cells = [" "] * total
    a, b = (i * c.width for i in ends(m, c))
    if a == b:  # to itself (or nowhere): glyph and label only, in its lane
        mark = f"{g} {label}"
        mark = mark if len(mark) <= total - a else g
        cells[a:a + len(mark)] = mark
        lo, hi = a, a + len(mark) - 1
    else:
        lo, hi = min(a, b), max(a, b)
        inner = hi - lo - 1
        body = ["·" if m.get("to") == HUMAN else "─"] * inner
        if len(label) + 2 <= inner:  # else the label is dropped; glyph and arrowhead stay
            at = 1 if b > a else inner - 1 - len(label)
            body[at:at + len(label)] = label
        cells[lo + 1:hi] = body
        cells[a] = g
        cells[b] = "▶" if b > a else "◀"
    out = Text("".join(cells[:lo]))
    out.append("".join(cells[lo:hi + 1]), style=style)
    out.append("".join(cells[hi + 1:]))
    return out


def margin(m: dict, c: Chart | None) -> Text:
    """`#id` and the first line; a collapsed agent's name first, so the `+N` lane is never a riddle."""
    out = Text()
    hidden = [n for n in dict.fromkeys((m.get("from"), m.get("to"))) if c and n in c.collapsed]
    if hidden:
        out.append("→".join(hidden) + ": ", style="bold")
    out.append(f"#{m.get('id', '?')} ", style="bright_black")
    out.append(first_line(m))
    return out


def chart_row(m: dict, c: Chart, width: int) -> Text:
    out = Text(clock(m).ljust(TIME), style="bright_black")
    out.append_text(arrow(m, c))
    out.append(" ")
    out.append_text(margin(m, c))
    return fit(out, width)


def list_row(m: dict, width: int) -> Text:
    """List mode (a narrow pane): time, sender → receiver, the glyph, `#id` and the first line."""
    g, _, style = glyph(m)
    out = Text(clock(m) + " ", style="bright_black")
    out.append(f"{m.get('from') or '?'} → {m.get('to') or '—'} ")
    out.append(g + " ", style=style)
    out.append(f"#{m.get('id', '?')} ", style="bright_black")
    out.append(first_line(m))
    return fit(out, width)
