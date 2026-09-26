"""`xt tui`: lazygit-style overview. This first version is a look-and-feel spike on demo data."""

from dataclasses import dataclass, field

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option


@dataclass
class Row:
    text: Text
    detail: str


@dataclass
class Model:
    panels: dict[str, list[Row]] = field(default_factory=dict)


def _t(*parts: tuple[str, str] | str) -> Text:
    out = Text(no_wrap=True, overflow="ellipsis")
    for p in parts:
        if isinstance(p, str):
            out.append(p)
        else:
            out.append(p[0], style=p[1])
    return out


def demo_model() -> Model:
    return Model(
        panels={
            "Goals": [
                Row(_t(("#3 ", "bright_black"), "weather forecasting team", ("  4/7", "green")),
                    "#3 weather forecasting team · open 2h\nbrief: goals/weather-team.md\n\n"
                    "tasks:\n  #41 ✓ ingest station data (carol)\n  #42 ● build baseline model (dave)\n"
                    "  #43 ● evaluation harness (erin)"),
                Row(_t(("#5 ", "bright_black"), "q3 close", ("  draft", "yellow")),
                    "draft: goals/drafts/q3-close.md\nbeing shaped with the liaison"),
            ],
            "Team": [
                Row(_t(("● ", "green"), "liaison  ", ("codex ", "bright_black"), ("idle", "green")),
                    "liaison · codex · reports to human\nlast: #47 report to human (2m)"),
                Row(_t(("● ", "yellow"), "lead     ", ("codex ", "bright_black"), ("working", "yellow")),
                    "lead · codex · reports to liaison\nopen: #3 goal"),
                Row(_t(("● ", "yellow"), "carol    ", ("claude", "bright_black"), (" working", "yellow")),
                    "carol · claude · data-ingest · reports to lead\nopen: #42"),
                Row(_t(("◐ ", "red"), "dave     ", ("pi    ", "bright_black"), ("blocked", "red")),
                    "dave · pi · modeler · reports to lead\nBLOCKED — approval prompt in its pane (f to focus)"),
            ],
            "Tasks": [
                Row(_t(("#42 ", "bright_black"), "carol  ingest stations", ("  12m", "bright_black")),
                    "#42 task lead→carol (goal #3)\ningest station data from /data/stations into parquet"),
                Row(_t(("#43 ", "bright_black"), "dave   baseline model", ("  3m", "bright_black")),
                    "#43 task lead→dave (goal #3)\ntrain a persistence + climatology baseline"),
            ],
            "Inbox": [
                Row(_t(("⚠ ", "red"), "dave blocked: approval prompt"), "dave is blocked — f to jump to its pane"),
                Row(_t(("? ", "yellow"), "spawn 'erin' (evaluator, pi)"), "lead asks to spawn erin\na approve · d deny"),
            ],
            "Log": [
                Row(_t(("#47 ", "bright_black"), ("report ", "cyan"), "liaison→human"), "#47 report liaison→human\nforecast team: 4 of 7 tasks done"),
                Row(_t(("#46 ", "bright_black"), ("done ", "green"), "carol→lead ref:#41"), "#46 done carol→lead\nstations ingested: /data/out/stations.parquet"),
                Row(_t(("#45 ", "bright_black"), ("task ", "magenta"), "lead→dave ref:#3"), "#45 task lead→dave\nbaseline model"),
            ],
        }
    )


class Panel(OptionList):
    def __init__(self, title: str, number: int, rows: list[Row]):
        super().__init__(*[Option(r.text) for r in rows], id=f"panel-{number}", classes="panel")
        self.rows = rows
        self.border_title = f"[{number}]─{title}"
        self._update_subtitle()

    def _update_subtitle(self) -> None:
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


class Help(ModalScreen[None]):
    BINDINGS = [Binding("escape,q,question_mark", "close", show=False)]

    def compose(self) -> ComposeResult:
        box = Vertical(classes="popup")
        box.border_title = "Keybindings"
        box.border_subtitle = "esc to close"
        with box:
            yield Static(
                "1-5       jump to panel\n"
                "tab h/l   next/previous panel\n"
                "j/k       move\n"
                "enter     open in detail\n"
                "s         send a message (to the liaison)\n"
                "f         focus the agent's pane in Herdr\n"
                "a / d     approve / deny a spawn\n"
                "/         filter\n"
                "q         quit"
            )

    def action_close(self) -> None:
        self.dismiss(None)


class XtTui(App):
    CSS_PATH = "lazy.tcss"
    TITLE = "xt"
    BINDINGS = [
        Binding("q", "quit", show=False),
        Binding("question_mark", "help", show=False),
        Binding("tab,l", "focus_next", show=False),
        Binding("shift+tab,h", "focus_previous", show=False),
        Binding("j", "cursor('down')", show=False),
        Binding("k", "cursor('up')", show=False),
        Binding("s", "send", show=False),
        *[Binding(str(i), f"panel({i})", show=False) for i in range(1, 6)],
    ]

    def __init__(self, model: Model):
        super().__init__(ansi_color=True)
        self.model = model

    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            with Vertical(id="left"):
                for i, (title, rows) in enumerate(self.model.panels.items(), start=1):
                    yield Panel(title, i, rows)
            detail = VerticalScroll(id="detail", classes="panel")
            detail.border_title = "Detail"
            with detail:
                yield Static(id="detail-body")
        yield Static(
            "1-5 panels · j/k move · enter open · s send · f focus pane · a approve · ? help · q quit",
            id="hints",
        )

    def on_mount(self) -> None:
        self.query_one("#panel-1", Panel).focus()
        self._show(self.query_one("#panel-1", Panel))

    def _show(self, panel: Panel) -> None:
        idx = panel.highlighted or 0
        body = panel.rows[idx].detail if panel.rows else ""
        self.query_one("#detail-body", Static).update(body)
        self.query_one("#detail", VerticalScroll).border_title = f"Detail─{panel.border_title.split('─', 1)[1]}"

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if isinstance(event.option_list, Panel):
            event.option_list._update_subtitle()
            self._show(event.option_list)

    def on_descendant_focus(self, event) -> None:
        if isinstance(event.widget, Panel):
            self._show(event.widget)

    def action_panel(self, n: int) -> None:
        self.query_one(f"#panel-{n}", Panel).focus()

    def action_cursor(self, direction: str) -> None:
        w = self.focused
        if isinstance(w, OptionList):
            (w.action_cursor_down if direction == "down" else w.action_cursor_up)()

    def action_help(self) -> None:
        self.push_screen(Help())

    def action_send(self) -> None:
        def done(text: str | None) -> None:
            if text:
                self.query_one("#hints", Static).update(f"(demo) would send to liaison: {text}")

        self.push_screen(Prompt("Send to liaison", "enter send · esc cancel"), done)


def run_demo() -> None:
    XtTui(demo_model()).run()
