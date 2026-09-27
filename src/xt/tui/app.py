"""`xt tui`: the lazygit-style overview of a running team (and `--demo` on static data)."""

from typing import Callable

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from .model import PANELS, Row, Snapshot

REFRESH_SECONDS = 2.0
HINTS = "1-5 panels · j/k move · enter read · a/d approve/deny · c clear · s send · f jump · u/U start · x stop · h help · q quit"


class Panel(OptionList):
    def __init__(self, title: str, number: int):
        super().__init__(id=f"panel-{number}", classes="panel")
        self.title = title
        self.rows: list[Row] = []
        self.border_title = f"[{number}]─{title}"

    def set_rows(self, rows: list[Row]) -> None:
        """Replace rows, keeping the selection on the same item when it still exists."""
        keep = self.current.key if self.current else None
        self.rows = rows
        self.clear_options()
        self.add_options([Option(r.text) for r in rows])
        if rows:
            idx = next((i for i, r in enumerate(rows) if r.key == keep), None)
            self.highlighted = idx if idx is not None else 0
        self.update_subtitle()

    @property
    def current(self) -> Row | None:
        if self.highlighted is None or not (0 <= self.highlighted < len(self.rows)):
            return None
        return self.rows[self.highlighted]

    def update_subtitle(self) -> None:
        n = len(self.rows)
        self.border_subtitle = f"{(self.highlighted or 0) + 1 if n else 0} of {n}"


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


class Help(ModalScreen[None]):
    BINDINGS = [Binding("escape,q,h,question_mark", "close", show=False)]

    KEYS = [
        ("Move", ""),
        ("1-5", "jump to a panel: Goals, Team, Tasks, Inbox, Log"),
        ("tab / l", "next panel"),
        ("shift+tab", "previous panel"),
        ("j / k", "down / up (in the detail pane: scroll)"),
        ("enter", "read the detail pane"),
        ("esc", "back from the detail pane to the panels"),
        ("Inbox (4)", ""),
        ("a / d", "approve / deny the selected spawn (asks y/n)"),
        ("c", "clear the selected alert"),
        ("Team (2)", ""),
        ("u", "start the selected stopped agent (existing role and harness)"),
        ("U", "start every stopped agent in the roster"),
        ("x", "stop the selected agent; it stays in the roster (asks y/n)"),
        ("f", "switch Herdr to the selected agent's workspace"),
        ("Anywhere", ""),
        ("s", "send a message to the liaison"),
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
        Binding("f", "jump", show=False),
        Binding("r", "refresh", show=False),
        Binding("u", "start_agent", show=False),
        Binding("U", "start_all", show=False),
        Binding("x", "stop_agent", show=False),
        *[Binding(str(i), f"panel({i})", show=False) for i in range(1, 6)],
    ]

    def __init__(self, source: Callable[[], Snapshot], actions=None):
        super().__init__(ansi_color=True)
        self.source = source
        self.actions = actions  # None in the demo
        self.last_panel = 1
        self.summary = ""
        self.status = ""

    def compose(self) -> ComposeResult:
        yield Static(id="topbar")
        with Horizontal(id="main"):
            with Vertical(id="left"):
                for i, title in enumerate(PANELS, start=1):
                    yield Panel(title, i)
            detail = VerticalScroll(id="detail", classes="panel")
            detail.border_title = "Detail"
            with detail:
                yield Static(id="detail-body")
        yield Static(id="hints")

    def on_mount(self) -> None:
        self.refresh_data()
        self.query_one("#panel-1", Panel).focus()
        if self.actions is not None:
            self.set_interval(REFRESH_SECONDS, self.refresh_data)

    # --- data -------------------------------------------------------------------------------

    def refresh_data(self) -> None:
        try:
            snap = self.source()
        except Exception as e:  # keep the TUI alive if one read fails; say so
            self.set_status(f"refresh failed: {e}")
            return
        for i, title in enumerate(PANELS, start=1):
            self.query_one(f"#panel-{i}", Panel).set_rows(snap.panels.get(title, []))
        self.summary = snap.summary
        self.render_hints()
        focused = self.focused if isinstance(self.focused, Panel) else self.panel(self.last_panel)
        self.show_detail(focused)

    def panel(self, n: int) -> Panel:
        return self.query_one(f"#panel-{n}", Panel)

    def show_detail(self, panel: Panel) -> None:
        row = panel.current
        body = self.query_one("#detail-body", Static)
        try:
            body.update(row.detail() if row else Text("(nothing here)", style="bright_black"))
        except Exception as e:
            body.update(Text(f"(couldn't build detail: {e})", style="red"))
        self.query_one("#detail", VerticalScroll).border_title = f"Detail─{panel.title}"

    def set_status(self, text: str) -> None:
        self.status = text
        self.render_hints()

    def render_hints(self) -> None:
        """Team summary and the latest action's result go on top; the bottom line is keys only."""
        top = Text(no_wrap=True, overflow="ellipsis")
        top.append(self.summary or "xt", style="bold")
        if self.status:
            top.append("  │  ", style="bright_black")
            top.append(self.status, style="yellow")
        self.query_one("#topbar", Static).update(top)
        self.query_one("#hints", Static).update(Text(HINTS, no_wrap=True, overflow="ellipsis"))

    # --- navigation -------------------------------------------------------------------------

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if isinstance(event.option_list, Panel):
            event.option_list.update_subtitle()
            if event.option_list is self.focused:
                self.show_detail(event.option_list)

    def on_descendant_focus(self, event) -> None:
        if isinstance(event.widget, Panel):
            self.last_panel = int(event.widget.id.split("-")[1])
            self.show_detail(event.widget)

    def action_panel(self, n: int) -> None:
        self.panel(n).focus()

    def action_cursor(self, direction: str) -> None:
        w = self.focused
        if isinstance(w, OptionList):
            (w.action_cursor_down if direction == "down" else w.action_cursor_up)()
        elif isinstance(w, VerticalScroll):
            (w.scroll_down if direction == "down" else w.scroll_up)()

    def action_read(self) -> None:
        if isinstance(self.focused, Panel):
            self.query_one("#detail", VerticalScroll).focus()

    def action_back(self) -> None:
        if not isinstance(self.focused, Panel):
            self.panel(self.last_panel).focus()

    def action_help(self) -> None:
        self.push_screen(Help())

    def action_refresh(self) -> None:
        self.refresh_data()

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
            self.set_status("select a spawn approval in the Inbox (4) first")
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
        row = self._selected("alert")
        if row is None:
            self.set_status("select an alert in the Inbox (4) first")
            return
        if self._need_live():
            self.actions.clear(row.data["key"])
            self.set_status("alert cleared")
            self.refresh_data()

    def action_send(self) -> None:
        if not self._need_live():
            return

        def done(text: str | None) -> None:
            if text and text.strip():
                try:
                    self.set_status(self.actions.send_to_liaison(text))
                except Exception as e:
                    self.set_status(f"send failed: {e}")
                self.refresh_data()

        self.push_screen(Prompt("Send to the liaison", "enter send · esc cancel"), done)

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
            self.set_status("select an agent in Team (2) first")
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
        panel = self.panel(2)
        names = [r.data["name"] for r in panel.rows
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
            self.set_status("select an agent in Team (2) first")
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

    def action_jump(self) -> None:
        row = self._selected("agent")
        if row is None:
            self.set_status("select an agent in Team (2) first")
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

    def jump(self, workspace_id: str) -> None:
        self.ctx.herdr.focus_workspace(workspace_id)

    def start(self, name: str) -> str:
        from ..spawn import request_spawn
        from ..team import HUMAN

        self.ctx.reload_team()
        return request_spawn(self.ctx, HUMAN, name, None, None, None, None)

    def stop(self, name: str) -> str:
        from ..spawn import stop

        return stop(self.ctx, name)


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
    return Snapshot(
        panels={
            "Goals": [
                _row("g3", _t(("#3 ", "bright_black"), "weather forecasting team", ("  4/7", "yellow")),
                     "#3 weather forecasting team · open 2h\nbrief: goals/weather-team.md", "goal"),
                _row("g5", _t(("#5 ", "bright_black"), "q3 close", ("  ✓", "green")), "#5 q3 close · done", "goal"),
            ],
            "Team": [
                _row("liaison", _t(("● ", "green"), "liaison     ", ("codex  ", "bright_black"), ("idle", "green")),
                     "liaison · codex · reports to human", "agent", name="liaison", workspace="w2"),
                _row("lead", _t(("● ", "yellow"), "lead        ", ("codex  ", "bright_black"), ("working", "yellow")),
                     "lead · codex · reports to liaison", "agent", name="lead", workspace="w3"),
                _row("dave", _t(("● ", "red"), "dave        ", ("pi     ", "bright_black"), ("blocked", "red")),
                     "dave · pi · modeler · BLOCKED on an approval prompt in its pane", "agent", name="dave",
                     workspace="w5"),
            ],
            "Tasks": [
                _row("t42", _t(("#42 ", "bright_black"), "carol      ingest stations", ("  12m", "yellow")),
                     "#42 task lead→carol\ningest station data", "task"),
            ],
            "Inbox": [
                _row("a9", _t(("? ", "yellow"), "#9 spawn erin ", ("(evaluator, pi)", "bright_black")),
                     "Approval #9: lead asks to spawn erin\n\nrole brief: …", "approval", id=9),
                _row("al", _t(("⚠ ", "red"), "dave is blocked (usually an approval prompt)"),
                     "dave is blocked — f on dave in Team to jump there", "alert", key="blocked:dave"),
            ],
            "Log": [
                _row("m47", _t(("#47 ", "bright_black"), ("report ", "cyan"), "liaison→human"),
                     "#47 report liaison→human\nforecast team: 4 of 7 tasks done", "message"),
            ],
        },
        summary="demo · 3 running · 2 open · 1 approval · 1 alert · 0 queued · 0 jobs",
    )


def run_demo() -> None:
    XtTui(demo_snapshot).run()
