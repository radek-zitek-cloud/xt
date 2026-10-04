"""Detail's thread (card #131): the selected message with the conversation around it.

For a message under a goal (the root of its `ref` chain, as in the Work outline) the thread is the
whole goal: the goal, its tasks and every reply, in time order. For a message without a goal it is
the message and the messages that reply to it through `ref`. A broken ref ends the chain, so such a
message shows alone with its replies.

Detail lays the thread out at its own size: the item's head (its summary and full text), then one
row per thread message (time, sender → receiver, type, first line), the selected one marked
`◀ you are here`, then the usage line and the keys that apply, then any reference text (a goal's
brief). A thread longer than the room left shows a window around the selected message and says how
many rows are hidden above and below; j/k in the focused Detail move that window. In a Detail too
short for the head and the thread together (the bottom band, card #162) the window takes Detail's
height less a row, and Detail scrolls to it first.
"""

import datetime as dt

from rich.console import Group
from rich.text import Text

from ..ledger import PANE_LABEL, is_pane

HERE = "  ◀ you are here"
# Card #208: a thread row's pane label, longest first; "unverified" stays at every width
PANE_FORMS = (PANE_LABEL, "pane, unverified", "unverified")
BODY_FLOOR = 12  # characters of a pane message a row keeps before any ellipsis
MIN_ROWS = 3  # thread rows Detail always shows, however long the head


def thread_of(msg: dict, msgs: list[dict]) -> list[dict]:
    """The thread of `msg` among `msgs` (oldest first), in time order; `msg` itself is always in it."""
    from .work import root_goal  # work imports model, which imports this module

    by_id = {m["id"]: m for m in msgs}
    by_id.setdefault(msg["id"], msg)
    root = root_goal(msg["id"], by_id)
    if root is not None:
        out = [m for m in by_id.values() if root_goal(m["id"], by_id) == root]
    else:
        ids = {msg["id"]}
        for m in sorted(by_id.values(), key=lambda m: m["id"]):
            if m.get("ref") in ids:
                ids.add(m["id"])
        out = [by_id[i] for i in ids]
    return sorted(out, key=lambda m: m["id"])


class ThreadDetail:
    """A Detail view with a thread. The TUI sets `height` (Detail's rows) and `offset` (the window's
    first row, None: placed so the selected message is in view) before it draws it."""

    def __init__(self, head: Text, thread: list[dict], selected: int, usage: str, keys: str,
                 more: Text | None = None, now: dt.datetime | None = None, type_style: dict | None = None):
        head = head.copy()
        head.rstrip()
        self.head, self.thread, self.selected = head, thread, selected
        self.usage, self.keys, self.more = usage, keys, more
        self.now = now
        self.type_style = type_style or {}
        self.height: int | None = None
        self.offset: int | None = None
        self.window = (0, len(thread))  # the rows drawn last time: [start, end)
        self.rows_at, self.rows_n = 0, 0  # where the thread's lines start in Detail, and how many there are

    @property
    def index(self) -> int:
        return next((i for i, m in enumerate(self.thread) if m["id"] == self.selected), 0)

    @property
    def plain(self) -> str:
        """Everything, with the whole thread (for tests and copying)."""
        rows = "\n".join(self.row(m, 400).plain for m in self.thread)
        more = self.more.plain if self.more else ""
        return f"{self.head.plain}\nthread ({len(self.thread)})\n{rows}\n{self.usage}\n{self.keys}\n{more}"

    # --- layout ----------------------------------------------------------------------------------

    def when(self, m: dict) -> str:
        days = {m["ts"][:10] for m in self.thread}
        today = (self.now or dt.datetime.now().astimezone()).isoformat()[:10]
        return m["ts"][5:16].replace("T", " ") if days - {today} else m["ts"][11:16]

    def _head(self, m: dict, names: int, here: bool, compact: bool) -> Text:
        """A row up to its text: time, sender → receiver, type, id. `compact` (a narrow pane-input
        row, card #208): the time without its date, the names unpadded, no type (always `ask`)."""
        out = Text(no_wrap=True, overflow="ellipsis", style="bold" if here else "")
        if compact:
            out.append(f"{m['ts'][11:16]} ", style="bright_black")
            out.append(f"{m['from'][:names]}→{m['to'][:names]} ")
        else:
            out.append(f"{self.when(m)}  ", style="bright_black")
            out.append(f"{m['from'][:names]:<{names}} → {m['to'][:names]:<{names}} ")
            out.append(f"{m['type']:<8} ", style=self.type_style.get(m["type"], ""))
        out.append(f"#{m['id']} ", style="bright_black")
        return out

    def row(self, m: dict, width: int) -> Text:
        names = max((len(x["from"]) for x in self.thread), default=4)
        names = min(12, max(names, max((len(x["to"]) for x in self.thread), default=4)))
        here = m["id"] == self.selected
        body = m.get("body") or ""
        first = body.strip().splitlines()[0] if body.strip() else ""
        mark = len(HERE) if here else 0
        out = self._head(m, names, here, compact=False)
        room = width - out.cell_len - mark
        if is_pane(m):  # card #193; #208: a shorter label rather than no message at all
            def keeps(left: int) -> bool:  # the whole line, or BODY_FLOOR characters before the "…"
                return left >= len(first) or left - 1 >= BODY_FLOOR

            # longest label first; if none keeps the floor, the row's own columns give way (never
            # "unverified"), and in the end the shortest of both
            tries = [(c, f) for c in (False, True) for f in PANE_FORMS]
            compact, label = next(((c, f) for c, f in tries
                                   if keeps(width - self._head(m, names, here, c).cell_len - mark - len(f) - 3)),
                                  tries[-1])
            out = self._head(m, names, here, compact)
            out.append(f"({label}) ", style="yellow")
            room = width - out.cell_len - mark
        line = Text(first)
        if line.cell_len > room:
            line.truncate(max(room, 1), overflow="ellipsis")
        out.append_text(line)
        if here:
            out.append(HERE, style="bold yellow")
        return out

    def place(self, room: int) -> tuple[int, int]:
        """The window [start, end) of at most `room` rows (hidden-row notes included) that keeps the
        selected row in view, starting at `offset` when the human has moved it."""
        n, sel = len(self.thread), self.index
        if n <= room:
            return 0, n
        room = max(3, room)  # a note above, a row, a note below
        if self.offset is None:
            # a little of what came after, when there is any and room for it beside the selection
            after = min(2, n - 1 - sel, room - 3)
            start = sel + 1 + after - (room - 2)  # ends there, with both notes
        else:
            start = self.offset
        start = max(0, min(start, n - 1))
        end = start + room - (1 if start else 0)
        if end >= n:  # nothing hidden below: fill the room from the end
            start = min(start, n - room + 1)
            return start, n
        return start, end - 1  # the last line is the note below

    def scroll(self, step: int) -> bool:
        """Move the window by `step` rows; False when it can't move that way."""
        start, end = self.window
        if (step > 0 and end >= len(self.thread)) or (step < 0 and start <= 0):
            return False
        self.offset = start + step
        return True

    def __rich_console__(self, console, options):
        width = options.max_width
        head = [self.head, Text(f"\nthread ({len(self.thread)})", style="bold")]
        foot = [Text(""), Text(self.usage, no_wrap=True, overflow="ellipsis"),
                Text(self.keys, style="bright_black", no_wrap=True, overflow="ellipsis")]
        above = sum(len(console.render_lines(r, options.update(height=None), pad=False)) for r in head)
        room = max(MIN_ROWS, (self.height or 10**6) - above - len(foot), (self.height or 0) - 1)
        start, end = self.window = self.place(room)
        rows = []
        if start:
            rows.append(Text(f"  ↑ {start} earlier row{'s' if start != 1 else ''} hidden (enter, then k)",
                             style="bright_black"))
        rows += [self.row(m, width) for m in self.thread[start:end]]
        if end < len(self.thread):
            rest = len(self.thread) - end
            rows.append(Text(f"  ↓ {rest} later row{'s' if rest != 1 else ''} hidden (enter, then j)",
                             style="bright_black"))
        self.rows_at, self.rows_n = above, len(rows)
        yield Group(*head, *rows, *foot, *([Text(""), self.more] if self.more else []))
