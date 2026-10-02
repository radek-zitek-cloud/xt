"""`xt tui`: the lazygit-style overview of a running team (and `--demo` on static data)."""

from typing import Callable

from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Input, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from . import flow, teampane, work
from .model import INBOX_HEADINGS, PANELS, Row, Snapshot, fit
from .thread import ThreadDetail

REFRESH_SECONDS = 2.0
INBOX = PANELS.index("Inbox") + 1  # its pane number
WORK = PANELS.index("Work") + 1
FLOW = PANELS.index("Flow") + 1
TEAM = 0  # the Team pane's key (card #157); last_panel is 0 while it has focus
DETAIL = len(PANELS) + 1  # Detail's key, 4 (card #157)
PICK_AGENT = "select an agent in Team first (0, then j/k)"
# The key line (card #162): the focused pane's own keys first, then the keys that work everywhere.
# Moving around (0-4, j/k, tab, enter, esc) and h and q are left to the help screen. In the Inbox, s
# shows while a question is selected, as `s answer #N` (card #102).
PANE_KEYS = {
    TEAM: [("u/U", "start"), ("x/X", "stop"), ("R", "retire"), ("f", "jump")],
    INBOX: [("a/d", "approve/deny"), ("s", "answer"), ("c", "clear"), ("space", "fold")],
    WORK: [("space", "fold"), ("o", "open only")],
    FLOW: [("t", "system"), ("f", "filter"), ("g/G", "newest/oldest")],
    DETAIL: [],
}
GLOBAL_KEYS = [("S", "message liaison"), ("/", "filter"), ("v", "supervisor")]
# The three bands (card #162), in outer rows: Detail about a fifth of the height (4 to 8 content rows),
# the top band what the team needs, up to 60% of the height and never so much that Work/Flow gets
# fewer than 4 content rows or is no taller than Detail; Work/Flow the rest. The key line takes the
# last row.
DETAIL_MIN, DETAIL_MAX, DETAIL_SHARE = 4, 8, 0.2
MIDDLE_MIN = 4
TOP_MIN, TOP_SHARE = 3, 0.6
TEAM_MIN_WIDTH = 30


def band_heights(total: int, team: int) -> tuple[int, int, int]:
    """(top, middle, detail) outer heights for a terminal `total` rows high whose Team pane needs
    `team` rows, frame included."""
    avail = max(0, total - 1)
    detail = max(DETAIL_MIN + 2, min(DETAIL_MAX + 2, round(avail * DETAIL_SHARE)))
    top = max(TOP_MIN + 2, min(team, int(avail * TOP_SHARE), avail - detail - max(MIDDLE_MIN + 2, detail + 1)))
    middle = avail - top - detail
    if middle < MIDDLE_MIN + 2:  # a small terminal: Detail and the top band give way too
        detail = max(3, min(detail, avail // 4))
        top = max(3, min(top, avail // 3))
        middle = max(0, avail - top - detail)
    return top, middle, detail


def pane_title(number: int, title: str, info: str = "") -> Text:
    """`[n] - Title - info` (card #162): the pane's key, its name, then its counts or filter."""
    return Text(f"[{number}] - {title}" + (f" - {info}" if info else ""))


def retitle(pane) -> None:
    """A pane's title. Work and Flow share the middle band (card #162): both names show like tabs,
    the one on screen with its info, the other dim."""
    partner = getattr(pane, "partner", None)
    if partner is None:
        pane.border_title = pane_title(pane.number, pane.title, pane.info)
        return
    active = pane if pane.display else partner
    out = Text()
    for p in sorted((pane, partner), key=lambda p: p.number):
        if out:
            out.append(" │ ", style="dim")
        out.append_text(pane_title(p.number, p.title, p.info) if p is active
                        else Text(f"[{p.number}] - {p.title}", style="dim"))
    pane.border_title = partner.border_title = out


def key_line(pairs: list[tuple[str, str]], more: list[tuple[str, str]], width: int) -> str:
    """`pairs` all, dropping their words from the end until they fit, then `more` while it fits."""
    words = [w for _, w in pairs]
    line = lambda: " · ".join(f"{k} {w}" if w else k for (k, _), w in zip(pairs, words))
    for i in range(len(words) - 1, -1, -1):
        if len(line()) <= width:
            break
        words[i] = ""
    out = line()
    for k, w in more:
        if len(out) + len(f" · {k} {w}") > width:
            break
        out += f" · {k} {w}"
    return out


class Panel(OptionList):
    def __init__(self, title: str, number: int):
        super().__init__(id=f"panel-{number}", classes="panel")
        self.title = title
        self.number = number
        self.rows: list[Row] = []
        self.all_rows: list[Row] = []
        self.filter = ""
        # the Inbox's open folds, by fold key: seen friction under `(N older, seen)` (card #127), seen
        # notifications under `(N earlier, seen)` (card #157)
        self.open_folds: set[str] = set()
        self.info = ""  # the title's info part (card #162)
        self.partner = None  # Work's is Flow: they share the middle band
        retitle(self)

    def set_counts(self, counts: str) -> None:
        self.info = counts
        retitle(self)

    def set_filter(self, text: str) -> None:
        self.filter = text.strip()
        self.set_rows(self.all_rows)

    def top_row(self) -> int | None:
        """The first row that can be selected."""
        return next((i for i, r in enumerate(self.rows) if r.kind != "heading"), None)

    def set_rows(self, rows: list[Row]) -> None:
        """Replace rows (only those matching the filter, if any), keeping the selection on the
        same item when it still exists, else on the nearest shown row above it in the outline. The
        newest rows are on top (card #162): with the top row selected, the selection stays on the top
        row, so it follows what arrives. Each row is laid out at the panel's width (card #132)."""
        keep = self.current.key if self.current else None
        follow = keep is not None and self.highlighted == self.top_row()
        self.all_rows = rows
        rows = self.visible(rows)
        self.rows = rows
        self.clear_options()
        width = self.content_size.width
        self.add_options([Option(self.line(r, width), disabled=r.kind == "heading") for r in rows])
        if rows:
            parents = {r.key: r.data.get("parent") for r in self.all_rows}
            idx = None
            while keep is not None and idx is None and not follow:
                idx = next((i for i, r in enumerate(rows) if r.key == keep), None)
                keep = parents.get(keep)
            if idx is None:
                idx = self.top_row()
            self.highlighted = idx
        self.update_subtitle()

    def visible(self, rows: list[Row]) -> list[Row]:
        rows = [r for r in rows if not r.data.get("folded") or r.data.get("under") in self.open_folds]
        if self.filter:
            needle = self.filter.lower()
            rows = [r for r in rows if r.kind != "heading" and needle in r.text.plain.lower()]
        return rows

    def line(self, row: Row, width: int) -> Text:
        text = row.text
        if row.kind == "fold" and row.key in self.open_folds:
            text = Text(text.plain.replace("▸", "▾"), style="bright_black")
        return fit(text, row.age, width)

    def on_resize(self) -> None:
        self.set_rows(self.all_rows)  # re-cut every row at the new width

    def fold_of(self, row: Row | None) -> str | None:
        """The fold a row opens or sits under, if any."""
        if row is None:
            return None
        return row.key if row.kind == "fold" else row.data.get("under")

    def toggle_fold(self, key: str | None = None) -> bool:
        """Open or close the selected row's fold (`key`'s when given), keeping the selection on the
        fold row when its rows go; False when there is no fold here."""
        key = key or self.fold_of(self.current)
        if key is None:
            return False
        self.open_folds ^= {key}
        self.set_rows(self.all_rows)
        if key not in self.open_folds:
            self.highlighted = next((i for i, r in enumerate(self.rows) if r.key == key), self.highlighted)
        return True

    async def _on_click(self, event) -> None:
        """A click selects the row and leaves focus here; only enter (or 4) opens Detail (card #157).
        Textual's own handler would select the option, which reads it."""
        event.prevent_default()
        clicked = event.style.meta.get("option")
        if clicked is not None and not self.get_option_at_index(clicked).disabled:
            self.highlighted = clicked

    def in_view(self) -> list[Row]:
        """The rows on screen right now (one line each), and the highlighted one."""
        top = self.scroll_offset.y
        out = self.rows[top: top + self.content_size.height]
        return out + ([self.current] if self.current and self.current not in out else [])

    @property
    def current(self) -> Row | None:
        if self.highlighted is None or not (0 <= self.highlighted < len(self.rows)):
            return None
        return self.rows[self.highlighted]

    def update_subtitle(self) -> None:
        items = [i for i, r in enumerate(self.rows) if r.kind != "heading"]
        n = len(items)
        pos = f"{sum(1 for i in items if i <= (self.highlighted or 0)) if n else 0} of {n}"
        self.border_subtitle = f"/{self.filter} · {pos}" if self.filter else pos

    # Moving past the first or last item does nothing (Textual's OptionList wraps around by default);
    # group headings are skipped.
    def action_cursor_down(self) -> None:
        h = self.highlighted
        if h is not None and not any(r.kind != "heading" for r in self.rows[h + 1:]):
            return
        super().action_cursor_down()

    def action_cursor_up(self) -> None:
        h = self.highlighted
        if h is not None and not any(r.kind != "heading" for r in self.rows[:h]):
            return
        super().action_cursor_up()


class WorkPanel(Panel):
    """Goals and tasks as one outline (card #129). The model gives every row; this pane keeps which
    rows are folded (by key, so it survives a refresh) and the open-only switch."""

    def __init__(self, title: str, number: int):
        super().__init__(title, number)
        self.folds: dict[str, bool] = {}  # what the human folded or unfolded, by row key
        self.open_only = False

    def expanded(self, row: Row) -> bool:
        return self.folds.get(row.key, bool(row.data.get("expanded")))

    def visible(self, rows: list[Row]) -> list[Row]:
        if self.open_only:
            rows = [r for r in rows if r.data.get("open")]
        if self.filter:  # a filter looks through the folds
            needle = self.filter.lower()
            return [r for r in rows if needle in r.text.plain.lower()]
        by_key = {r.key: r for r in rows}

        def shown(r: Row) -> bool:
            parent = r.data.get("parent")
            while parent is not None:
                p = by_key.get(parent)
                if p is None or not self.expanded(p):
                    return False
                parent = p.data.get("parent")
            return True

        return [r for r in rows if shown(r)]

    def line(self, row: Row, width: int) -> Text:
        return work.line(row.text, row.data, row.age, width, self.expanded(row))

    def toggle(self) -> None:
        """space: fold or unfold the selected row; on a task, fold its goal and select that."""
        row = self.current
        if row is None:
            return
        if not row.data.get("foldable"):
            parent = next((r for r in self.all_rows if r.key == row.data.get("parent")), None)
            if parent is None:
                return
            row = parent
            self.folds[row.key] = False
        else:
            self.folds[row.key] = not self.expanded(row)
        self.set_rows(self.all_rows)
        self.highlighted = next((i for i, r in enumerate(self.rows) if r.key == row.key), self.highlighted)

    def toggle_open_only(self) -> None:
        self.open_only = not self.open_only
        self.set_rows(self.all_rows)

    def update_subtitle(self) -> None:
        super().update_subtitle()
        if self.open_only:  # still visible after the toast has gone
            self.border_subtitle = f"open only · {self.border_subtitle}"


class TeamPane(Static):
    """The Team pane, top left (cards #128, #162): the header, today's spend, then each harness's
    usage line and its agents, one column. It never scrolls: what doesn't fit gives way to a
    `+N more` line. `0` (or tab) reaches it; j/k or the arrows, the page keys and a click select a
    row in view for Detail (card #157): the header and each harness line (card #151), then the
    agents, whom the agent keys act on."""

    can_focus = True
    BINDINGS = [Binding("down", "step(1)", show=False), Binding("up", "step(-1)", show=False),
                Binding("home", "edge(-1)", show=False), Binding("end", "edge(1)", show=False),
                Binding("pageup", "page(-1)", show=False), Binding("pagedown", "page(1)", show=False)]

    def __init__(self):
        super().__init__(id="team", classes="panel")
        self.title = "Team"
        self.number = TEAM
        self.info = ""
        retitle(self)
        self.header = Text("")
        self.spend = ""
        self.harnesses: list[teampane.Harness] = []
        self.all_rows: list[Row] = []
        self.rows: list[Row] = []  # the agents in view, in display order
        self.keys: list[str] = []  # every row in view that can be selected, in display order
        self.selected: str | None = None  # the selected row's key: teampane.HEADER, a harness's, an agent's name
        self.header_detail = None
        self.now = None
        self.natural = 3  # the rows the whole pane needs, frame included
        self.limit: int | None = None  # the content rows it gets when that is fewer, else None
        self.hidden = 0  # the harnesses and agents under the `+N more` line

    def set_data(self, snap: Snapshot, now) -> None:
        self.header, self.spend, self.harnesses = snap.header, snap.spend, snap.harnesses
        self.header_detail = snap.header_detail
        self.all_rows = snap.panels.get("Team", [])
        self.now = now
        self.redraw()

    def need_width(self) -> int:
        """The width, frame included, at which an agent's line has its widest bar."""
        return teampane.widths([r.data for r in self.all_rows]).cell(teampane.BAR_MAX) + 2

    def lines(self, width: int) -> list[tuple[Text, str | None]]:
        import datetime as dt

        now = self.now or dt.datetime.now().astimezone()
        return teampane.render(self.header, self.spend, self.harnesses, [r.data for r in self.all_rows],
                               width, now, self.selected if self.has_focus else None)

    def natural_at(self, width: int) -> int:
        """The rows the whole pane needs at `width` (frame included), before it is that wide."""
        return len(self.lines(max(1, width - 2))) + 2

    def redraw(self) -> None:
        width = self.content_size.width or max(20, self.app.size.width // 2 - 2)
        by_name = {r.data["name"]: r for r in self.all_rows}
        lines = self.lines(width)
        shown, self.hidden = teampane.clip(lines, self.limit)
        self.keys = [k for k in dict.fromkeys(k for _, k in shown) if k is not None]
        self.rows = [by_name[k] for k in self.keys if k in by_name]
        if self.keys and self.selected not in self.keys:
            self.selected = self.keys[0]
            if self.has_focus:
                return self.redraw()
        natural, self.natural = self.natural, len(lines) + 2
        self.update(Text("\n").join(line for line, _ in shown))
        if natural != self.natural and self.is_mounted:
            self.app.relayout()

    def on_resize(self) -> None:
        self.redraw()

    def on_focus(self) -> None:
        self.redraw()

    def on_blur(self) -> None:
        self.redraw()

    @property
    def current(self) -> Row | None:
        """The selected row: an agent's, or one made here for the header or a harness line."""
        key = self.selected
        if key == teampane.HEADER:
            detail = self.header_detail or (lambda: Text("(nothing here)", style="bright_black"))
            return Row(key, Text("xt and the team"), detail, "team", {})
        harness = next((h for h in self.harnesses if teampane.harness_key(h.name) == key), None)
        if harness is not None:
            detail = harness.detail or (lambda h=harness: Text(f"{h.name.upper()}: no detail", style="bright_black"))
            return Row(key, Text(harness.name), detail, "harness", {"harness": harness.name})
        return next((r for r in self.rows if r.data["name"] == key), None)

    def select(self, key: str) -> None:
        self.selected = key
        self.redraw()

    def move(self, step: int) -> None:
        if self.selected in self.keys:
            i = max(0, min(len(self.keys) - 1, self.keys.index(self.selected) + step))
            self.select(self.keys[i])

    def page_size(self) -> int:
        """Rows a page key moves by: all of them in view (the pane never scrolls)."""
        return max(1, len(self.keys))

    def action_step(self, step: int) -> None:
        self.move(step)
        self.app.show_detail(self)

    def action_edge(self, step: int) -> None:
        self.action_step(step * len(self.keys))

    def action_page(self, step: int) -> None:
        self.action_step(step * self.page_size())

    def on_click(self, event) -> None:
        """A click on a row selects it; Detail shows it and focus stays here (card #157)."""
        key = event.style.meta.get("agent") or event.style.meta.get("team_row")
        if key is not None and key in self.keys:
            self.focus()
            self.select(key)
            self.app.show_detail(self)


class FlowPane(Widget):
    """The Flow chart (card #130), sharing the middle band with Work (card #162). It keeps which rows
    pass its filters (system lines, one agent or goal, text), which one is selected and where the
    view starts; it draws only the rows in view, so a ledger of thousands of messages scrolls without
    a stall. The newest message is the top row (card #162); while it is selected Flow follows new
    messages."""

    can_focus = True
    BINDINGS = [Binding("g,home", "edge(-1)", show=False), Binding("G,end", "edge(1)", show=False),
                Binding("pageup", "page(-1)", show=False), Binding("pagedown", "page(1)", show=False),
                Binding("down", "step(1)", show=False), Binding("up", "step(-1)", show=False)]
    WHEEL_ROWS = 3  # rows one notch of the mouse wheel scrolls

    def __init__(self, title: str, number: int):
        super().__init__(id=f"panel-{number}", classes="panel")
        self.title = title
        self.number = number
        self.data = flow.Data()
        self.show_system = False
        self.pick: tuple[str, object] | None = None  # ("agent", name) or ("goal", id)
        self.filter = ""  # `/`: text in the body
        self.shown: list[dict] = []  # the messages that pass the system toggle
        self.lanes: list[flow.Lane] = []  # every agent `f` offers: the lanes of all of `shown`
        self.items: list[dict] = []  # the messages that pass every filter, oldest first
        self.rows: list[tuple[str, object]] = []  # what the pane lists, newest first: messages and day separators
        self.selected: int | None = None  # index in rows
        self.top = 0
        self.follow = True
        self.info = ""
        self.partner = None  # Work: they share the middle band (card #162)
        self.update_title()

    # --- data and filters ---------------------------------------------------------------------------

    def set_data(self, data: flow.Data) -> None:
        self.data = data
        self.rebuild()

    def rebuild(self) -> None:
        """Filter and lay out the rows again, newest first, keeping the selection on the same message
        (or the newest one before it), or on the newest while following."""
        keep = None if self.follow else self.message()
        shown = self.shown = [m for m in self.data.msgs if self.show_system or not flow.is_system(m)]
        self.lanes = flow.lanes(self.data.roster, shown)
        if self.pick and self.pick[0] == "goal":
            by_id = {m["id"]: m for m in self.data.msgs if "id" in m}
            thread = {i for i in by_id if work.root_goal(i, by_id) == self.pick[1]}
            shown = [m for m in shown if m.get("id") in thread]
        elif self.pick:
            shown = [m for m in shown if self.pick[1] in (m.get("from"), m.get("to"))]
        if self.filter:
            needle = self.filter.lower()
            shown = [m for m in shown if needle in (m.get("body") or "").lower()]
        self.items = shown
        self.rows = flow.entries(shown[::-1], self.data.now)
        msgs = self.message_rows()
        if not msgs:
            self.selected = None
        elif keep is None:
            self.selected = msgs[0]
        else:
            before = [i for i in msgs if self.rows[i][1].get("id", 0) <= keep.get("id", 0)]
            self.selected = before[0] if before else msgs[-1]
        self.follow = bool(msgs) and self.selected == msgs[0]
        self.place()

    def toggle_system(self) -> None:
        self.show_system = not self.show_system
        self.rebuild()

    def set_pick(self, pick: tuple[str, object] | None) -> None:
        self.pick = pick
        self.follow = True
        self.rebuild()

    def set_filter(self, text: str) -> None:
        self.filter = text.strip()
        self.rebuild()

    def picks(self) -> list[tuple[tuple[str, object], str]]:
        """What `f` offers: every agent with a lane, then the goals, newest first."""
        agents = [(("agent", lane.name), f"agent  {lane.name}") for lane in self.lanes]
        goals = [(("goal", m["id"]), f"goal   #{m['id']} {flow.first_line(m)}")
                 for m in reversed(self.data.msgs) if m.get("type") == "goal" and "id" in m]
        return agents + goals

    def pick_text(self) -> str:
        if not self.pick:
            return ""
        return f"agent {self.pick[1]}" if self.pick[0] == "agent" else f"goal #{self.pick[1]}"

    # --- selection and view -------------------------------------------------------------------------

    def message_rows(self) -> list[int]:
        return [i for i, (kind, _) in enumerate(self.rows) if kind == "msg"]

    def message(self) -> dict | None:
        if self.selected is None or not (0 <= self.selected < len(self.rows)):
            return None
        kind, m = self.rows[self.selected]
        return m if kind == "msg" else None

    @property
    def current(self) -> Row | None:
        m = self.message()
        if m is None:
            return None
        detail = (lambda: self.data.detail(m)) if self.data.detail else (lambda: Text(flow.first_line(m)))
        return Row(f"flow:{m.get('id')}", Text(flow.first_line(m)), detail, "message", {"id": m.get("id")})

    def width(self) -> int:
        return self.content_size.width or max(0, self.app.size.width - 2)

    def chart(self) -> flow.Chart | None:
        """The chart of the rows in view: a retired agent's dim lane only while its rows are on
        screen (after the filters and the viewport, so scrolling and resizing change it too)."""
        if self.width() < flow.NARROW:
            return None
        return flow.chart(flow.lanes(self.data.roster, self.shown, self.in_view()), self.width())

    def view_height(self) -> int:
        # the header row exactly when chart() draws one; no chart() here, it needs this height
        return max(1, self.content_size.height - (1 if self.width() >= flow.NARROW else 0))

    def place(self) -> None:
        """Keep the selected row in view (the top of the list while following), then retitle. While
        Work has the band, the view stays where it was."""
        if not self.display or not self.content_size.height:
            return self.update_title()
        h, n = self.view_height(), len(self.rows)
        if self.follow:
            self.top = 0
        elif self.selected is not None:
            if self.selected < self.top:
                self.top = self.selected
            elif self.selected >= self.top + h:
                self.top = self.selected - h + 1
        self.top = max(0, min(self.top, n - h))
        self.update_title()
        self.refresh()

    def move(self, step: int) -> None:
        """Select the message `step` rows down (up when negative), stopping at the ends."""
        msgs = self.message_rows()
        if not msgs:
            return
        at = msgs.index(self.selected) if self.selected in msgs else 0
        self.selected = msgs[max(0, min(len(msgs) - 1, at + step))]
        self.follow = self.selected == msgs[0]
        self.place()

    def action_step(self, step: int) -> None:
        self.move(step)
        self.app.show_detail(self)

    def action_page(self, step: int) -> None:
        self.move(step * max(1, self.view_height() - 1))
        self.app.show_detail(self)

    def scroll_view(self, step: int) -> None:
        """The wheel (card #157): the view moves `step` rows, the selection only as far as it must to
        stay in view. Scrolled down from the newest row, Flow stops following."""
        msgs = self.message_rows()
        h, n = self.view_height(), len(self.rows)
        self.top = max(0, min(self.top + step, n - h))
        if msgs and self.selected is not None:
            in_view = [i for i in msgs if self.top <= i < self.top + h]
            if in_view and self.selected not in in_view:
                self.selected = in_view[0] if self.selected < in_view[0] else in_view[-1]
            self.follow = self.selected == msgs[0] and self.top == 0
        self.place()
        if self.has_focus:
            self.app.show_detail(self)

    def on_mouse_scroll_down(self, event) -> None:
        event.stop()
        self.scroll_view(self.WHEEL_ROWS)

    def on_mouse_scroll_up(self, event) -> None:
        event.stop()
        self.scroll_view(-self.WHEEL_ROWS)

    def on_click(self, event) -> None:
        """A click on a message row selects it; Detail shows it and focus stays here (card #157)."""
        i = event.style.meta.get("flow_row")
        if i is not None and 0 <= i < len(self.rows) and self.rows[i][0] == "msg":
            self.focus()
            self.selected = i
            self.follow = i == self.message_rows()[0]
            self.place()
            self.app.show_detail(self)

    def action_edge(self, step: int) -> None:
        msgs = self.message_rows()
        if msgs:
            self.move(len(msgs) * step)
            if step < 0:
                self.top = 0
                self.place()
        self.app.show_detail(self)

    def in_view(self) -> list[dict]:
        return [m for kind, m in self.rows[self.top:self.top + self.view_height()] if kind == "msg"]

    def update_title(self) -> None:
        """`N of M` (the messages in view of all that pass the filters), the system switch and any
        filter."""
        parts = [f"{len(self.in_view()) if self.is_mounted else 0} of {len(self.items)}",
                 "system shown (t)" if self.show_system else "system hidden (t)"]
        if self.pick:
            parts.append(self.pick_text() + " (f)")
        if self.filter:
            parts.append(f"/{self.filter}")
        self.info = " · ".join(parts)
        retitle(self)

    def on_resize(self) -> None:
        self.place()

    def on_focus(self) -> None:
        self.refresh()

    def on_blur(self) -> None:
        self.refresh()

    def render(self) -> Text:
        width = self.content_size.width
        c = self.chart()
        lines = [flow.header(c, width)] if c else []
        for i in range(self.top, min(len(self.rows), self.top + self.view_height())):
            kind, x = self.rows[i]
            if kind == "day":
                lines.append(flow.separator(x, width))
                continue
            line = flow.chart_row(x, c, width) if c else flow.list_row(x, width)
            line.append(" " * max(0, width - line.cell_len))  # the whole row takes a click (card #157)
            if i == self.selected:
                line.stylize(flow.SELECTED if self.has_focus else "bold")
            line.stylize(Style.from_meta({"flow_row": i}))
            lines.append(line)
        if not self.items:
            filtered = self.pick or self.filter
            lines.append(Text("(no messages match the filter)" if filtered else "(no messages yet)",
                              style="bright_black"))
        return Text("\n").join(lines)


class FlowPick(ModalScreen[object]):
    """`f` in Flow: one agent's messages or one goal's thread. Picking the active filter again, or
    esc, clears it."""

    BINDINGS = [Binding("escape", "cancel", show=False), Binding("j", "move('down')", show=False),
                Binding("k", "move('up')", show=False)]

    def __init__(self, picks: list[tuple[tuple[str, object], str]], active: tuple[str, object] | None):
        super().__init__()
        self.picks = picks
        self.active = active

    def compose(self) -> ComposeResult:
        box = Vertical(classes="popup pick")
        box.border_title = "Filter Flow"
        box.border_subtitle = ("enter pick · the active one again or esc clears it" if self.active
                               else "enter pick · esc cancel")
        with box:
            yield OptionList(*[Option(("● " if key == self.active else "  ") + text) for key, text in self.picks],
                             id="flow-pick")

    def on_mount(self) -> None:
        options = self.query_one("#flow-pick", OptionList)
        keys = [key for key, _ in self.picks]
        options.highlighted = keys.index(self.active) if self.active in keys else 0
        options.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self.picks[event.option_index][0])

    def action_move(self, direction: str) -> None:  # the app's j/k don't reach a pop-up
        options = self.query_one("#flow-pick", OptionList)
        (options.action_cursor_down if direction == "down" else options.action_cursor_up)()

    def action_cancel(self) -> None:
        self.dismiss("esc")


PANES = (Panel, TeamPane, FlowPane)  # what focus moves between (Detail is reached with enter, 4 or tab)


class DetailPane(VerticalScroll):
    """The detail pane's frame, full width at the bottom (card #162). The wheel moves a thread like
    j/k: its hidden rows first, then the scroll (card #157)."""

    def on_mouse_scroll_down(self, event) -> None:
        event.prevent_default()
        event.stop()
        self.app.scroll_detail("down")

    def on_mouse_scroll_up(self, event) -> None:
        event.prevent_default()
        event.stop()
        self.app.scroll_detail("up")


class DetailBody(Static):
    """Detail's content. A thread is laid out for Detail's height at each draw, so a resize or a
    refresh keeps the selected message in view (card #131)."""

    def render(self):
        view = self.content
        if isinstance(view, ThreadDetail) and self.parent is not None:
            view.height = self.parent.content_size.height or None
        return super().render()

    def on_resize(self) -> None:
        self.refresh(layout=True)


class Toast(Static):
    """The last action's result, one line at the bottom, gone after about ten seconds (card #128)."""

    SECONDS = 10.0

    def __init__(self):
        super().__init__(id="toast")
        self.timers = []
        self.display = False

    def show(self, text: str) -> None:
        for t in self.timers:
            t.stop()
        self.timers = []
        self.remove_class("fading")
        self.update(Text(text, no_wrap=True, overflow="ellipsis"))
        self.display = bool(text)
        if text:  # dim for the last fifth, then gone
            self.timers = [self.set_timer(self.SECONDS * 0.8, lambda: self.add_class("fading")),
                           self.set_timer(self.SECONDS, self.hide)]

    def hide(self) -> None:
        self.timers = []
        self.display = False


class Prompt(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", show=False)]

    def __init__(self, title: str, hint: str):
        super().__init__()
        self.title_text = title
        self.hint = hint

    def compose(self) -> ComposeResult:
        box = Vertical(classes="popup")
        box.border_title = self.title_text
        box.border_subtitle = self.hint
        with box:
            yield Input(placeholder="type and press enter")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class Editor(TextArea):
    """The composer's text box: copy and paste go through the system clipboard (card #110)."""

    def action_copy(self) -> None:
        from . import clipboard

        text = self.selected_text
        if not text:
            return
        self.app.copy_to_clipboard(text)  # the terminal's clipboard too, where it supports it
        if not clipboard.copy(text):
            self.notify("couldn't reach the system clipboard (wl-copy, xclip, xsel or pbcopy)", severity="warning")

    def action_cut(self) -> None:
        text = self.selected_text
        if text:
            self.action_copy()
            self.replace("", *self.selection)

    def action_paste(self) -> None:
        from . import clipboard

        text = clipboard.paste()
        if text is None:
            self.notify("couldn't read the system clipboard (wl-paste, xclip, xsel or pbpaste); "
                        "your terminal's paste (e.g. ctrl+shift+v) still works", severity="warning")
            return
        self.replace(text, *self.selection)


class Compose(ModalScreen[str | None]):
    """A few lines of text (an answer, a message): enter starts a new line, ctrl+s sends."""

    BINDINGS = [Binding("escape", "cancel", show=False), Binding("ctrl+s", "send", show=False)]

    def __init__(self, title: str, context: str | None = None, options: dict[int, str] | None = None):
        super().__init__()
        self.title_text = title
        self.context = context
        self.options = options or {}  # a question's numbered options (card #111)

    def compose(self) -> ComposeResult:
        box = Vertical(classes="popup compose")
        box.border_title = self.title_text
        box.border_subtitle = (("1-3 fill an option · " if self.options else "")
                               + "ctrl+s send · enter new line · ctrl+c/ctrl+v copy/paste · esc cancel")
        with box:
            if self.context:
                with VerticalScroll(classes="compose-context"):
                    yield Static(Text(self.context))
            yield Editor(id="compose-text", soft_wrap=True, show_line_numbers=False)

    def on_mount(self) -> None:
        self.query_one("#compose-text", TextArea).focus()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """In an empty answer, typing 1, 2 or 3 fills that option's full text, still editable; with
        text already there, digits are just digits."""
        area = event.text_area
        if self.options and area.text in {str(n) for n in self.options}:
            area.text = f"Option {area.text}: {self.options[int(area.text)]}"
            area.move_cursor(area.document.end)

    def action_send(self) -> None:
        self.dismiss(self.query_one("#compose-text", TextArea).text)

    def action_cancel(self) -> None:
        self.dismiss(None)


class Confirm(ModalScreen[bool]):
    BINDINGS = [Binding("y", "yes", show=False), Binding("n,escape", "no", show=False)]

    def __init__(self, title: str, question: str):
        super().__init__()
        self.title_text = title
        self.question = question

    def compose(self) -> ComposeResult:
        box = Vertical(classes="popup")
        box.border_title = self.title_text
        box.border_subtitle = "y yes · n no"
        with box:
            yield Static(Text(self.question))

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)


class SupervisorPopup(ModalScreen[None]):
    """`v`: what the supervisor did, newest first, over the TUI (card #131); esc closes it. It follows
    the refresh while it is open."""

    BINDINGS = [Binding("escape,v", "close", show=False), Binding("j", "scroll(1)", show=False),
                Binding("k", "scroll(-1)", show=False)]

    def __init__(self, rows: list[Row]):
        super().__init__()
        self.rows = rows

    def compose(self) -> ComposeResult:
        box = VerticalScroll(id="supervisor", classes="popup supervisor")
        box.border_title = "Supervisor"
        box.border_subtitle = "newest first · j/k scroll · esc close"
        with box:
            yield Static(id="supervisor-body")

    def on_mount(self) -> None:
        self.show(self.rows)
        self.query_one("#supervisor").focus()

    def show(self, rows: list[Row]) -> None:
        self.rows = rows
        text = (Text("\n").join(r.text for r in rows) if rows
                else Text("(the supervisor hasn't logged anything yet)", style="bright_black"))
        self.query_one("#supervisor-body", Static).update(text)

    def action_scroll(self, step: int) -> None:  # the app's j/k don't reach a pop-up
        box = self.query_one("#supervisor", VerticalScroll)
        (box.scroll_down if step > 0 else box.scroll_up)(animate=False)

    def action_close(self) -> None:
        self.dismiss(None)


class Help(ModalScreen[None]):
    BINDINGS = [Binding("escape,q,h,question_mark", "close", show=False)]

    KEYS = [
        ("Move", ""),
        (f"{TEAM}-{DETAIL}", "jump to a pane: " + ", ".join(["Team", *PANELS, "Detail"])),
        (f"{WORK} / {FLOW}", "Work and Flow share the middle pane: 2 shows Work, 3 shows Flow; each keeps "
                             "its selection"),
        ("tab / l", "next pane"),
        ("shift+tab", "previous pane"),
        ("j / k", "down / up; the arrows too (in the detail pane: the thread's hidden rows first, then scroll)"),
        ("enter", "read the detail pane: the selected item and its thread"),
        ("/", "filter the focused pane (empty clears it)"),
        ("esc", "back from the detail pane to the pane you came from"),
        ("mouse", "a click selects a row and keeps focus in its pane; the wheel scrolls Flow and the detail pane"),
        ("v", "the supervisor's log, newest first, in a pop-up (esc closes it)"),
        (f"Inbox ({INBOX})", ""),
        ("a / d", "approve / deny the selected spawn (asks y/n)"),
        ("c", "clear the selected alert; on unread friction: mark it seen"),
        ("enter/space", "on (N older, seen): show or hide the friction you've seen; on (N earlier, seen): "
                        "the notifications you've seen in the last 7 days; on (N answered, last 7 days): "
                        "your answers"),
        (f"Work ({WORK})", ""),
        ("space", "fold or unfold the selected goal, done (N) or no goal row (on a task: fold its goal)"),
        ("o", "open work only: hide done (N) and done tasks; again: show them"),
        ("enter", "show the selected goal or task in the detail pane"),
        (f"Flow ({FLOW})", ""),
        ("j / k", "select a message (the newest is on top); with the newest selected, Flow follows new ones"),
        ("pgup/pgdn", "a page up / down"),
        ("g / G", "the newest (top) / the oldest (bottom) message (home / end too)"),
        ("enter", "show the selected message and its thread in the detail pane"),
        ("t", "show or hide system lines (starts, stops, settings, wake-ups, nudges); from any pane"),
        ("f", "filter to one agent's messages or one goal's thread; the same pick again, esc in the "
              "picker, or esc in Flow clears it"),
        ("/", "filter by the message's text"),
        (f"Team ({TEAM})", ""),
        ("j / k", "select the header (xt and the team: versions, today's usage), a harness line (its "
                  "windows and why one is unknown; ? marks one) or an agent; the detail pane shows it. "
                  "Agents under the +N more line need a taller terminal"),
        ("pgup/pgdn", "the first / the last row in view (home / end too)"),
        ("u", "start the selected stopped agent (existing role and harness)"),
        ("U", "start every stopped agent in the roster"),
        ("x", "stop the selected agent; it stays in the roster (asks y/n)"),
        ("X", "stop every running agent (asks y/n; the supervisor keeps running)"),
        ("R", "retire the selected agent: it leaves the roster (asks y/n; not the liaison or lead)"),
        ("f", "switch Herdr to the selected agent's workspace"),
        ("Anywhere", ""),
        ("s", "answer the question selected in Inbox; anywhere else: send a message to the liaison "
              "(in the Inbox the key line says which; enter: new line, ctrl+s: send)"),
        ("S", "always send a message to the liaison, even with a question selected"),
        ("r", "refresh now (it also refreshes every 2 s)"),
        ("h / ?", "this help"),
        ("q", "quit"),
    ]

    def compose(self) -> ComposeResult:
        box = Vertical(classes="popup help")
        box.border_title = "Keys"
        box.border_subtitle = "esc to close"
        text = Text()
        for key, what in self.KEYS:
            if not what:
                text.append(f"\n{key}\n" if text else f"{key}\n", style="bold")
            else:
                text.append(f"  {key:<11}", style="green")
                text.append(what + "\n")
        with box:
            yield Static(text)

    def action_close(self) -> None:
        self.dismiss(None)


class XtTui(App):
    CSS_PATH = "lazy.tcss"
    TITLE = "xt"
    # the Inbox first, not the first pane (Team): with the Inbox the start pane (card #130), focus
    # passing through Team would count as leaving it and mark its friction seen. Pop-ups: their input.
    AUTO_FOCUS = "#panel-1, Input"
    BINDINGS = [
        Binding("q", "quit", show=False),
        Binding("h,question_mark", "help", show=False),
        Binding("tab,l", "focus_next", show=False),
        Binding("shift+tab", "focus_previous", show=False),
        Binding("j", "cursor('down')", show=False),
        Binding("k", "cursor('up')", show=False),
        Binding("enter", "read", show=False),
        Binding("escape", "back", show=False),
        Binding("a", "decide(True)", show=False),
        Binding("d", "decide(False)", show=False),
        Binding("c", "clear_alert", show=False),
        Binding("s", "send", show=False),
        Binding("S", "send_liaison", show=False),
        Binding("f", "jump", show=False),
        Binding("r", "refresh", show=False),
        Binding("u", "start_agent", show=False),
        Binding("U", "start_all", show=False),
        Binding("x", "stop_agent", show=False),
        Binding("X", "stop_all", show=False),
        Binding("R", "retire_agent", show=False),
        Binding("slash", "filter", show=False),
        Binding("space", "fold", show=False),
        Binding("o", "open_only", show=False),
        Binding("v", "supervisor", show=False),
        Binding("t", "system", show=False),
        *[Binding(str(i), f"panel({i})", show=False) for i in range(TEAM, len(PANELS) + 1)],
        Binding(str(DETAIL), "detail", show=False),
    ]

    def __init__(self, source: Callable[[], Snapshot], actions=None):
        super().__init__(ansi_color=True)
        self.source = source
        self.actions = actions  # None in the demo
        self.last_panel = INBOX
        self.status = ""  # the last action's result, shown in the toast
        self.done_upto = 0  # newest message the Inbox's "done" rows were built from (card #125)
        self.inbox_looked = 0  # what the human saw while the Inbox had focus
        self.friction_viewed: set[int] = set()  # unread friction on screen while the Inbox had focus (#127)
        self.snapshot: Snapshot | None = None
        self.detail_view = None  # what Detail shows, and for which row (its thread window survives a refresh)
        self.detail_key: str | None = None

    def compose(self) -> ComposeResult:
        # three bands (card #162): Team and the Inbox side by side; Work or Flow, full width; Detail,
        # full width; the key line last
        with Horizontal(id="top"):
            yield TeamPane()
            yield Panel("Inbox", INBOX)
        with Vertical(id="middle"):
            work_pane, flow_pane = WorkPanel("Work", WORK), FlowPane("Flow", FLOW)
            work_pane.partner, flow_pane.partner = flow_pane, work_pane
            flow_pane.display = False
            yield work_pane
            yield flow_pane
        detail = DetailPane(id="detail", classes="panel")
        detail.border_title = pane_title(DETAIL, "Detail")
        with detail:
            yield DetailBody(id="detail-body")
        yield Toast()
        yield Static(id="hints")

    def on_mount(self) -> None:
        retitle(self.panel(WORK))
        self.refresh_data()
        self.relayout()
        self.panel(INBOX).focus()  # what the human depends on most (criterion 14 of #130)
        if self.actions is not None:
            self.set_interval(REFRESH_SECONDS, self.refresh_data)

    def on_resize(self) -> None:
        self.relayout()
        self.call_after_refresh(self.relayout)  # the screen has the new size only then

    def relayout(self) -> None:
        """Set the bands' heights for the terminal's (see band_heights) and the Team pane's width;
        the Team pane shows what fits and a `+N more` line."""
        if not self.query("#top"):
            return
        team_w = max(TEAM_MIN_WIDTH, min(self.team.need_width(), self.size.width // 2))
        natural = self.team.natural_at(team_w)
        top, middle, detail = band_heights(self.size.height, natural)
        limit = None if top >= natural else max(1, top - 2)
        for widget, h in ((self.query_one("#top"), top), (self.query_one("#middle"), middle),
                          (self.query_one("#detail"), detail)):
            if widget.styles.height is None or widget.styles.height.value != h:
                widget.styles.height = h
        if self.team.styles.width is None or self.team.styles.width.value != team_w:
            self.team.styles.width = team_w
        if limit != self.team.limit:
            self.team.limit = limit
            self.team.redraw()

    def show_middle(self, n: int) -> None:
        """2 shows Work in the middle band, 3 Flow (card #162); the other keeps its state, hidden."""
        work_pane, flow_pane = self.panel(WORK), self.panel(FLOW)
        work_pane.display, flow_pane.display = n == WORK, n == FLOW
        retitle(work_pane)

    # --- data -------------------------------------------------------------------------------

    def refresh_data(self) -> None:
        try:
            snap = self.source()
        except Exception as e:  # keep the TUI alive if one read fails; say so
            self.set_status(f"refresh failed: {e}")
            return
        self.snapshot = snap
        if isinstance(self.screen, SupervisorPopup):
            self.screen.show(snap.panels.get("Supervisor", []))
        for n in (INBOX, WORK):
            self.panel(n).set_rows(snap.panels.get(PANELS[n - 1], []))
        try:
            self.panel(FLOW).set_data(snap.flow)
        except Exception as e:  # a drawing bug must not take the other panes with it
            self.set_status(f"couldn't draw Flow: {e}")
        try:
            self.team.set_data(snap, self.source_now())
        except Exception as e:  # a layout bug must not take the other panes with it
            self.set_status(f"couldn't draw Team: {e}")
        self.done_upto = snap.done_upto
        self.panel(INBOX).set_counts(snap.inbox_title)
        self.panel(WORK).set_counts(snap.work_title)
        if self.last_panel == INBOX:
            self.inbox_looked = self.done_upto
            self.call_after_refresh(self.note_friction_in_view)
        self.render_hints()
        focused = self.focused if isinstance(self.focused, PANES) else self.panel(self.last_panel)
        self.show_detail(focused)

    def source_now(self):
        """The clock for reset times: the team's own (a test's fake one) in live mode."""
        try:
            return self.actions.ctx.ledger.clock()
        except Exception:
            return None

    @property
    def team(self) -> TeamPane:
        return self.query_one("#team", TeamPane)

    def panel(self, n: int):
        """Pane n (1-3), or the Team pane for TEAM (0)."""
        return self.team if n == TEAM else self.query_one(f"#panel-{n}")

    def show_detail(self, panel) -> None:
        """The selected row in Detail; a message's thread gets Detail's height, and keeps the window
        the human moved it to while the same row stays selected (card #131)."""
        row = panel.current
        body = self.query_one("#detail-body", Static)
        pane = self.query_one("#detail", VerticalScroll)
        try:
            view = row.detail() if row else Text("(nothing here)", style="bright_black")
        except Exception as e:
            view = Text(f"(couldn't build detail: {e})", style="red")
        key = row.key if row else None
        if isinstance(view, ThreadDetail) and key == self.detail_key and isinstance(self.detail_view, ThreadDetail):
            view.offset = self.detail_view.offset
        self.detail_view, self.detail_key = view, key
        body.update(view)
        pane.border_title = pane_title(DETAIL, "Detail", panel.title)

    def set_status(self, text: str) -> None:
        """The last action's result goes to the toast, never into the Team pane (card #128)."""
        self.status = text
        self.query_one(Toast).show(text)

    def focused_number(self) -> int:
        """The focused pane's key: DETAIL in Detail, else the last list pane."""
        return DETAIL if isinstance(self.focused, DetailPane) else self.last_panel

    def render_hints(self) -> None:
        """The bottom line (card #162): the focused pane's own keys, then S, / and v, which work
        everywhere. No keys for moving around; the help screen has every key."""
        n = self.focused_number()
        own = list(PANE_KEYS.get(n, []))
        if n == INBOX:  # s answers the selected question (card #102); else it is S's twin, left out
            send = self.send_hint()
            at = [k for k, _ in own].index("s")
            own[at:at + 1] = [send] if send else []
        width = max(20, self.size.width - 2)
        self.query_one("#hints", Static).update(Text(key_line(own + GLOBAL_KEYS, [], width), no_wrap=True,
                                                     overflow="ellipsis"))

    def send_hint(self) -> tuple[str, str] | None:
        """`s answer #N` while a question is selected in the Inbox, else None (s messages the liaison)."""
        try:
            row = self._selected("question")
        except Exception:  # before the panels exist
            row = None
        return ("s", f"answer #{row.data['id']}") if row else None

    # --- navigation -------------------------------------------------------------------------

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if isinstance(event.option_list, Panel) and self.is_running and self.screen_stack:
            event.option_list.update_subtitle()
            if event.option_list is self.focused:
                self.show_detail(event.option_list)
                self.render_hints()
                if self.last_panel == INBOX:
                    self.call_after_refresh(self.note_friction_in_view)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """enter on the Inbox's `(N older, seen)` row shows or hides the seen friction (card #127);
        enter on any other row of a list shows it, with its thread, in the detail pane (cards #129,
        #131)."""
        if isinstance(event.option_list, Panel):
            row = event.option_list.current
            if row and row.kind == "fold":
                event.option_list.toggle_fold()
                return
            self.show_detail(event.option_list)
            self.action_read()

    def on_descendant_focus(self, event) -> None:
        if not self.query("#detail-body"):
            return  # the screen is being taken down: focus moves as panes go, the human did nothing
        if isinstance(event.widget, PANES):
            n = TEAM if isinstance(event.widget, TeamPane) else int(event.widget.id.split("-")[1])
            if self.last_panel == INBOX and n != INBOX:
                self.mark_inbox_seen()
            elif n == INBOX:
                self.inbox_looked = self.done_upto
                self.call_after_refresh(self.note_friction_in_view)
            self.last_panel = n
            self.show_detail(event.widget)
            self.render_hints()
        elif isinstance(event.widget, DetailPane):
            self.render_hints()

    def note_friction_in_view(self) -> None:
        """Unread friction on screen while the human has the Inbox open counts as seen once they
        leave the Inbox or quit (card #127)."""
        if self.last_panel != INBOX or not self.screen_stack:
            return
        self.friction_viewed |= {r.data["id"] for r in self.panel(INBOX).in_view()
                                 if r.kind == "friction" and not r.data.get("seen")}

    def mark_inbox_seen(self) -> None:
        """Leaving the Inbox (or quitting) clears the done goals and the friction the human has now
        seen (cards #125, #127)."""
        if self.actions is None:
            return
        self.note_friction_in_view()
        try:
            if self.inbox_looked:
                self.actions.inbox_seen(self.inbox_looked)
            if self.friction_viewed:
                self.actions.friction_seen(sorted(self.friction_viewed))
                self.friction_viewed = set()
        except Exception as e:  # never let the marker break the TUI
            self.set_status(f"couldn't mark the Inbox seen: {e}")

    async def action_quit(self) -> None:
        if self.last_panel == INBOX:
            self.mark_inbox_seen()
        self.exit()

    def action_panel(self, n: int) -> None:
        if n in (WORK, FLOW):
            self.show_middle(n)
        self.panel(n).focus()

    def action_cursor(self, direction: str) -> None:
        w = self.focused
        if isinstance(w, OptionList):
            (w.action_cursor_down if direction == "down" else w.action_cursor_up)()
        elif isinstance(w, (TeamPane, FlowPane)):
            w.move(1 if direction == "down" else -1)
            self.show_detail(w)
        elif isinstance(w, DetailPane):
            self.scroll_detail(direction)
        elif isinstance(w, VerticalScroll):
            (w.scroll_down if direction == "down" else w.scroll_up)()

    def scroll_detail(self, direction: str) -> None:
        """j/k in Detail, or the wheel over it: a thread's hidden rows first (card #131) while its
        rows are in view, else the scroll. In the short bottom Detail (card #162) the scroll brings
        the thread into view first."""
        w = self.query_one("#detail", DetailPane)
        view = self.detail_view
        down = direction == "down"
        if isinstance(view, ThreadDetail):
            top, h = round(w.scroll_y), w.content_size.height
            in_view = top <= view.rows_at and view.rows_at + view.rows_n <= top + h
            at_edge = (w.scroll_y >= w.max_scroll_y) if down else (w.scroll_y <= 0)
            if (in_view or at_edge) and view.scroll(1 if down else -1):
                return self.query_one("#detail-body", Static).update(view)
        (w.scroll_down if down else w.scroll_up)(animate=False)

    def action_detail(self) -> None:
        """4: Detail, showing what the pane the human was in has selected (card #157)."""
        if isinstance(self.focused, PANES):
            self.show_detail(self.focused)
        self.query_one("#detail", DetailPane).focus()

    def action_read(self) -> None:
        if isinstance(self.focused, PANES):
            self.show_detail(self.focused)
            self.query_one("#detail", VerticalScroll).focus()

    def action_back(self) -> None:
        """esc: from Detail back to the panes; in Flow, clear its agent or goal filter."""
        if isinstance(self.focused, FlowPane) and self.focused.pick:
            self.set_flow_pick(None)
        elif not isinstance(self.focused, PANES):
            self.panel(self.last_panel).focus()

    def action_system(self) -> None:
        """t: show or hide Flow's system lines, from any pane (with Work on screen, the toast says so)."""
        pane = self.panel(FLOW)
        pane.toggle_system()
        self.set_status("Flow: system lines shown" if pane.show_system else "Flow: system lines hidden")
        if self.focused is pane:
            self.show_detail(pane)

    def set_flow_pick(self, pick) -> None:
        pane = self.panel(FLOW)
        pane.set_pick(pick)
        self.set_status(f"Flow: only {pane.pick_text()}" if pick else "Flow: filter cleared")
        if self.focused is pane:
            self.show_detail(pane)

    def flow_filter(self) -> None:
        """f in Flow: pick an agent or a goal; the active one again, or esc, clears it."""
        pane = self.panel(FLOW)

        def done(pick) -> None:
            if pick == "esc":
                if pane.pick:
                    self.set_flow_pick(None)
            elif pick is not None:
                self.set_flow_pick(None if pick == pane.pick else pick)

        self.push_screen(FlowPick(pane.picks(), pane.pick), done)

    def action_help(self) -> None:
        self.push_screen(Help())

    def action_supervisor(self) -> None:
        if not isinstance(self.screen, SupervisorPopup):
            self.push_screen(SupervisorPopup(self.snapshot.panels.get("Supervisor", []) if self.snapshot else []))

    def action_filter(self) -> None:
        panel = self.panel(self.last_panel)
        if isinstance(panel, TeamPane):
            self.set_status("Team has no filter; it shows every agent")
            return

        def done(text: str | None) -> None:
            if text is not None:
                panel.set_filter(text)
                panel.focus()
                self.set_status(f"{panel.title}: showing rows with “{panel.filter}”" if panel.filter
                                else f"{panel.title}: filter cleared")

        self.push_screen(Prompt(f"Filter {panel.title}", "enter apply · empty clears · esc cancel"), done)

    def action_refresh(self) -> None:
        self.refresh_data()

    def _work_focused(self, key: str, where: str = f"Work ({WORK})") -> WorkPanel | None:
        if isinstance(self.focused, WorkPanel):
            return self.focused
        self.set_status(f"{key} works in {where}")
        return None

    def action_fold(self) -> None:
        """space: fold in Work; in the Inbox, open or close the seen rows the selected row belongs to
        (card #157)."""
        panel = self.focused
        if isinstance(panel, Panel) and panel.number == INBOX:
            if panel.toggle_fold():
                self.show_detail(panel)
            else:
                self.set_status("space in the Inbox works on its folds: (N answered…), (N earlier, seen), "
                                "(N older, seen)")
            return
        panel = self._work_focused("space", f"the Inbox ({INBOX}) and Work ({WORK})")
        if panel:
            panel.toggle()
            self.show_detail(panel)

    def action_open_only(self) -> None:
        panel = self._work_focused("o")
        if panel:
            panel.toggle_open_only()
            self.show_detail(panel)
            self.set_status("Work: open work only" if panel.open_only else "Work: done work shown again")

    # --- actions (live mode only) -------------------------------------------------------------

    def _selected(self, kind: str) -> Row | None:
        row = self.panel(self.last_panel).current
        return row if row and row.kind == kind else None

    def _need_live(self) -> bool:
        if self.actions is None:
            self.set_status("demo mode: actions are disabled")
            return False
        return True

    def action_decide(self, approve: bool) -> None:
        row = self._selected("approval")
        if row is None:
            self.set_status(f"select a spawn approval in the Inbox ({INBOX}) first")
            return
        if not self._need_live():
            return
        rid = row.data["id"]
        verb = "Approve" if approve else "Deny"

        def go(ok: bool | None) -> None:
            if not ok:
                return
            doing = "approving" if approve else "denying"
            self.set_status(f"{doing} #{rid}… (starting an agent takes a few seconds)")
            self.run_worker(lambda: self._decide(rid, approve), thread=True, exclusive=False)

        self.push_screen(Confirm(f"{verb} #{rid}", row.text.plain), go)

    def _decide(self, rid: int, approve: bool) -> None:
        try:
            result = self.actions.decide(rid, approve)
        except Exception as e:
            result = f"#{rid} failed: {e}"
        self.call_from_thread(self.set_status, result)
        self.call_from_thread(self.refresh_data)

    def action_clear_alert(self) -> None:
        friction = self._selected("friction")
        if friction is not None and not friction.data.get("seen"):
            if self._need_live():  # c on unread friction: seen now (card #127)
                self.actions.friction_seen([friction.data["id"]])
                self.set_status(f"friction #{friction.data['id']} marked seen")
                self.refresh_data()
            return
        row = self._selected("alert")
        if row is None:
            self.set_status(f"select an alert or unread friction in the Inbox ({INBOX}) first")
            return
        if self._need_live():
            self.actions.clear(row.data["key"])
            self.set_status("alert cleared")
            self.refresh_data()

    def action_send(self) -> None:
        """s: answer the question selected in the Inbox, otherwise send a message to the liaison."""
        row = self._selected("question")
        self._compose(row.data if row else None)

    def action_send_liaison(self) -> None:
        """S: always a message to the liaison, whatever is selected (card #102)."""
        self._compose(None)

    def _compose(self, question: dict | None) -> None:
        if not self._need_live():
            return

        def done(text: str | None) -> None:
            if text and text.strip():
                try:
                    if question:
                        self.set_status(self.actions.answer(question["id"], text))
                    else:
                        self.set_status(self.actions.send_to_liaison(text))
                except Exception as e:
                    self.set_status(f"send failed: {e}")
                self.refresh_data()

        if question:
            from ..choices import options_of

            self.push_screen(Compose(f"Answer question #{question['id']} from {question['opener']}",
                                     question.get("text"), options_of(question.get("text") or "")), done)
        else:
            self.push_screen(Compose("Send to the liaison"), done)

    def _run_bg(self, label: str, fn) -> None:
        """Run a slow action (starting agents takes seconds) without freezing the screen."""
        self.set_status(label)

        def work() -> None:
            try:
                result = fn()
            except Exception as e:
                result = f"failed: {e}"
            self.call_from_thread(self.set_status, result)
            self.call_from_thread(self.refresh_data)

        self.run_worker(work, thread=True, exclusive=False)

    def action_start_agent(self) -> None:
        row = self._selected("agent")
        if row is None:
            self.set_status(PICK_AGENT)
            return
        if not self._need_live():
            return
        name = row.data["name"]
        if row.data.get("running"):
            self.set_status(f"{name} is already running")
            return
        if not row.data.get("active", True):
            self.set_status(f"{name} is retired")
            return
        self._run_bg(f"starting {name}… (a few seconds)", lambda: self.actions.start(name))

    def action_start_all(self) -> None:
        if not self._need_live():
            return
        names = [r.data["name"] for r in self.team.rows
                 if r.kind == "agent" and not r.data.get("running") and r.data.get("active", True)]
        if not names:
            self.set_status("every agent in the roster is already running")
            return

        def go(ok: bool | None) -> None:
            if ok:
                self._run_bg(f"starting {', '.join(names)}… (a few seconds each)",
                             lambda: "; ".join(self.actions.start(n) for n in names))

        self.push_screen(Confirm("Start all", f"Start {len(names)} stopped agents: {', '.join(names)}?"), go)

    def action_stop_agent(self) -> None:
        row = self._selected("agent")
        if row is None:
            self.set_status(PICK_AGENT)
            return
        if not self._need_live():
            return
        name = row.data["name"]
        if not row.data.get("running"):
            self.set_status(f"{name} isn't running")
            return

        def go(ok: bool | None) -> None:
            if ok:
                self._run_bg(f"stopping {name}…", lambda: self.actions.stop(name))

        self.push_screen(Confirm(f"Stop {name}", f"Stop {name}? Its workspace closes; it stays in the "
                                                 f"roster and `u` starts it again."), go)

    def action_stop_all(self) -> None:
        if not self._need_live():
            return
        names = [r.data["name"] for r in self.team.rows if r.kind == "agent" and r.data.get("running")]
        if not names:
            self.set_status("no agents are running")
            return

        def go(ok: bool | None) -> None:
            if ok:
                self._run_bg(f"stopping {', '.join(names)}…", lambda: "; ".join(self.actions.stop(n) for n in names))

        self.push_screen(Confirm("Stop all", f"Stop {len(names)} running agents: {', '.join(names)}? They stay in "
                                             f"the roster; U starts them again."), go)

    def action_retire_agent(self) -> None:
        row = self._selected("agent")
        if row is None:
            self.set_status(PICK_AGENT)
            return
        if not self._need_live():
            return
        name = row.data["name"]
        if not row.data.get("active", True):
            self.set_status(f"{name} is already retired")
            return
        if row.data.get("role") in ("liaison", "lead"):
            self.set_status(f"the {row.data['role']} can't be retired from the TUI; the team needs it")
            return

        def go(ok: bool | None) -> None:
            if ok:
                self._run_bg(f"retiring {name}…", lambda: self.actions.retire(name))

        self.push_screen(Confirm(f"Retire {name}", f"Retire {name}? Its workspace closes and it leaves the "
                                                   f"roster (marked retired in team.toml). Bringing it back "
                                                   f"takes a new spawn."), go)

    def action_jump(self) -> None:
        """f: in Flow, its filter (card #130); on an agent in Team, switch Herdr to it."""
        if isinstance(self.focused, FlowPane):
            return self.flow_filter()
        row = self._selected("agent")
        if row is None:
            self.set_status(PICK_AGENT)
            return
        if not self._need_live():
            return
        if not row.data.get("workspace"):
            self.set_status(f"{row.data['name']} isn't running")
            return
        try:
            self.actions.jump(row.data["workspace"])
            self.set_status(f"switched Herdr to {row.data['name']}'s workspace")
        except Exception as e:
            self.set_status(f"jump failed: {e}")


class LiveActions:
    """What the TUI's keys do, acting as the human (who is at a real terminal)."""

    def __init__(self, ctx):
        self.ctx = ctx

    def decide(self, rid: int, approve: bool) -> str:
        from ..spawn import decide

        return decide(self.ctx, rid, approve)

    def clear(self, key: str) -> None:
        from ..alerts import Alerts

        Alerts(self.ctx).resolve(key)

    def send_to_liaison(self, text: str) -> str:
        from ..dispatch import send
        from ..team import HUMAN

        liaison = self.ctx.team.lead_of_role("liaison")
        if liaison is None:
            raise RuntimeError("no liaison in team.toml")
        msg, status = send(self.ctx, HUMAN, liaison.name, "ask", text)
        return f"#{msg['id']} to {liaison.name}: {status}"

    def answer(self, qid: int, text: str) -> str:
        from ..choices import resolve
        from ..dispatch import send
        from ..team import HUMAN

        item = self.ctx.ledger.item(qid)
        if item is None or item["type"] != "ask":
            raise RuntimeError(f"#{qid} is no longer an open question")
        text, _ = resolve((self.ctx.ledger.message(qid) or {}).get("body", ""), text)
        msg, status = send(self.ctx, HUMAN, item["opener"], "report", text, qid)
        return f"#{msg['id']} answer to #{qid} → {item['opener']}: {status}"

    def jump(self, workspace_id: str) -> None:
        self.ctx.herdr.focus_workspace(workspace_id)

    def inbox_seen(self, upto: int) -> None:
        from ..goaldone import mark_seen

        mark_seen(self.ctx, upto)

    def friction_seen(self, ids: list[int]) -> None:
        from ..inbox import mark_friction_seen

        mark_friction_seen(self.ctx, ids)

    def start(self, name: str) -> str:
        from ..spawn import request_spawn
        from ..team import HUMAN

        self.ctx.reload_team()
        return request_spawn(self.ctx, HUMAN, name, None, None, None, None)

    def stop(self, name: str) -> str:
        from ..spawn import stop

        return stop(self.ctx, name)

    def retire(self, name: str) -> str:
        from ..spawn import retire
        from ..team import HUMAN

        return retire(self.ctx, HUMAN, name)


def run_live() -> None:
    from ..context import Ctx
    from .model import build

    ctx = Ctx.load()
    XtTui(lambda: build(ctx), LiveActions(ctx)).run()


# --- demo data (xt tui --demo) -----------------------------------------------------------------


def _t(*parts) -> Text:
    out = Text(no_wrap=True, overflow="ellipsis")
    for p in parts:
        out.append(p) if isinstance(p, str) else out.append(p[0], style=p[1])
    return out


def _row(row_key: str, text: Text, detail: str, kind: str = "", **data) -> Row:
    return Row(row_key, text, lambda d=detail: Text(d), kind, data)


def demo_snapshot() -> Snapshot:
    import datetime as dt

    now = dt.datetime.now().astimezone()
    return Snapshot(
        panels={
            "Work": [
                _row("goal:3", _t(("#3 ", "bright_black"), "weather forecasting team"),
                     "#3 weather forecasting team · open 2h\nbrief: goals/weather-team.md", "goal",
                     id=3, level=1, foldable=True, expanded=True, open=True,
                     tail=_t("  ", ("lead ", "bright_black"), "  ", ("1/2", "yellow"), "  ")),
                _row("task:41", _t(("✓ ", "green"), ("#41 ", "bright_black"), "carol  find station data"),
                     "#41 task lead→carol\nfind station data", "task", id=41, level=2, parent="goal:3"),
                _row("task:42", _t(("● ", "yellow"), ("#42 ", "bright_black"), "carol  ingest stations"),
                     "#42 task lead→carol\ningest station data", "task", id=42, level=2, parent="goal:3", open=True),
                _row("draft:quarterly-report", _t(("✎ ", "cyan"), "quarterly-report", ("  draft", "cyan")),
                     "draft · goals/drafts/quarterly-report.md", "draft", level=1, open=True),
                _row(work.DONE_FOLD, _t(("done (1)", "bright_black")), "1 done goal", "donefold",
                     level=1, foldable=True),
                _row("goal:5", _t(("#5 ", "bright_black"), "q3 close"), "#5 q3 close · done", "goal",
                     id=5, level=1, foldable=True, parent=work.DONE_FOLD,
                     tail=_t("  ", ("lead ", "bright_black"), "  ", ("0/0", "green"), (" ✓", "green"))),
            ],
            "Team": [
                _agent("liaison", "codex", "gpt-5.2", "idle", 58_000, 258_000, "liaison · codex · reports to human"),
                _agent("lead", "codex", "gpt-5.2", "working", 181_000, 258_000, "lead · codex · reports to liaison"),
                _agent("carol", "claude", "sonnet 5.5", "working", 93_000, 1_000_000, "carol · claude · worker"),
                _agent("pm", "claude", "opus 5.5", "idle", 47_000, 1_000_000, "pm · claude · product"),
                _agent("dave", "pi", "kimi", "blocked", 12_000, None,
                       "dave · pi · modeler · BLOCKED on an approval prompt in its pane"),
            ],
            "Inbox": [
                _row("hn", _t((INBOX_HEADINGS[0], "bold")), "", "heading"),
                _row("a9", _t(("⚑ ", "yellow"), "#9 spawn erin ", ("(evaluator, pi)", "bright_black")),
                     "Approval #9: lead asks to spawn erin\n\nrole brief: …", "approval", id=9),
                _row("al", _t(("⚠ ", "red"), "dave is blocked (usually an approval prompt)"),
                     "dave is blocked — f on dave in Team to jump there", "alert", key="blocked:dave"),
                _row("hw", _t((INBOX_HEADINGS[1], "bold")), "", "heading"),
                _row("m47", _t(("✉ ", "cyan"), "#47 liaison: forecast team: 4 of 7 tasks done"),
                     "#47 report liaison→human\nforecast team: 4 of 7 tasks done", "message", id=47),
                _row("hf", _t((INBOX_HEADINGS[2], "bold")), "", "heading"),
                _row("f51", _t(("✱ ", "magenta"), "#51 carol: the sandbox refused a plain curl"),
                     "#51 friction carol→human\nthe sandbox refused a plain curl", "friction", id=51),
                _row("fold", _t(("(4 older, seen) ▸", "bright_black")), "4 older friction reports you have seen",
                     "fold", n=4),
            ],
            "Supervisor": [
                _row("s2", _t(("14:36 ", "bright_black"), "woke scout (every 60m, 05:00-21:00)"),
                     "2026-09-27 14:36:02 woke scout (every 60m, 05:00-21:00)", "event"),
                _row("s1", _t(("14:31 ", "bright_black"), "delivered #161 to lead"),
                     "2026-09-27 14:31:36 delivered #161 to lead", "event"),
            ],
        },
        header=Text.assemble(("demo", "bold"), " · xt demo · 5 running · 1 goal open · ",
                             ("⚑ 2 needs you", "bold yellow"), " · ", ("✉ 1 new", "cyan")),
        spend="today 8.4M tokens · est. $2.46 (+1.1M unpriced)",
        harnesses=[teampane.Harness("claude", [("5h", 6.0, int(now.timestamp()) + 3 * 3600),
                                               ("7d", 10.0, int(now.timestamp()) + 4 * 86400)],
                                    detail=lambda: Text("CLAUDE · account windows\n5h  6% used · read 2 m ago\n"
                                                        "7d  10% used · read 2 m ago\n")),
                   teampane.Harness("codex", [("7d", 20.0, None)],
                                    detail=lambda: Text("CODEX · account windows\n7d  20% used\n")),
                   teampane.Harness("pi", cue=False,
                                    detail=lambda: Text("PI · account windows\nxt reads no account windows for pi\n"))],
        header_detail=lambda: Text("xt and the team\npublished 0.17.0 (checked 1 h ago) · installed 0.17.0 · "
                                   "running 0.17.0\n\n── usage today ──\nteam: 8.4M tokens, est. $2.46\n"),
        inbox_title="⚑ 2 · ✉ 1 · ✱ 1",
        work_title="1 open · 1 done",
        flow=_demo_flow(now),
    )


def _demo_flow(now) -> flow.Data:
    """A day and a half of a small team: one message of every glyph, the system lines `t` shows, a
    retired agent, and a message with no receiver."""
    import datetime as dt

    script = [  # minutes ago, from, to, type, body
        (1500, "liaison", "lead", "goal", "Weather forecasting team: stations, model, daily report"),
        (1495, "lead", "carol", "task", "Find station data for the region"),
        (1490, "xt", "human", "system", "started carol (claude, sonnet 5.5)"),
        (1440, "scout", "lead", "report", "Scouted three public station feeds"),
        (1430, "carol", "lead", "done", "Found 212 stations; list in data/stations.csv"),
        (95, "human", "liaison", "ask", "How far is the forecast team?"),
        (90, "liaison", "human", "report", "Forecast team: 4 of 7 tasks done"),
        (80, "lead", "carol", "task", "Ingest the station data"),
        (75, "xt", "dave", "wake", "scheduled wake-up (every 60m)"),
        (70, "lead", "dave", "task", "Fit the first forecast model"),
        (64, "dave", "human", "friction", "the sandbox refused a plain curl"),
        (60, "xt", "lead", "nudge", "#42 has been open for an hour"),
        (55, "xt", "human", "approval", "lead asks to spawn erin as evaluator on pi"),
        (50, "lead", "liaison", "ask", "Should the model cover the coast too?"),
        (45, "liaison", "lead", "report", "Yes: the coast too, same deadline"),
        (40, "xt", "human", "alert", "dave is blocked (usually an approval prompt)"),
        (35, "pm", "pm", "note", "decided: publish the report daily at 07:00"),
        (30, "carol", "lead", "report", "Ingest halfway: 120 of 212 stations"),
        (20, "lead", "pm", "task", "Write the daily report page"),
        (10, "liaison", "human", "ask", "The coast adds a day: accept the new date?"),
        (5, "pm", "", "note", "checkpoint: report page drafted"),
    ]
    msgs = [{"id": 30 + i, "ts": (now - dt.timedelta(minutes=ago)).isoformat(timespec="seconds"), "from": src,
             "to": dst, "type": kind, "body": body} for i, (ago, src, dst, kind, body) in enumerate(script)]
    roster = [("liaison", "liaison", True), ("lead", "lead", True), ("carol", "worker", True),
              ("pm", "product", True), ("dave", "modeler", True), ("scout", "scout", False)]
    detail = lambda m: Text(f"#{m['id']} {m['type']} {m['from']} → {m['to'] or '—'}\n{m['body']}\n")
    return flow.Data(msgs, roster, detail, now)


def _agent(name: str, harness: str, model: str, state: str, used: int, window: int | None, detail: str) -> Row:
    data = {"name": name, "harness": harness, "model": model, "state": state, "running": True,
            "dot": "●", "used": used, "window": window,
            "workspace": f"w-{name}", "active": True}
    return Row(name, teampane.cell(data, teampane.widths([data]), teampane.BAR_MAX), lambda: Text(detail),
               "agent", data)


def run_demo() -> None:
    XtTui(demo_snapshot).run()
