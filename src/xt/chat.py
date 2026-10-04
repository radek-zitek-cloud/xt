"""`xt chat`: one conversation with the liaison in the terminal (card #184).

The conversation is a view over the ledger, shared with the TUI (Q1): the messages between the
human and the liaison, and the approvals waiting for the human, read from the log. Chat stores
nothing of its own: what it sends is an ordinary ledger message (the same as the TUI's `S`), an
answer goes through `cli.answer` (the same as `xt answer`), and a typed but unsent draft lives
only in the input box. It is never written anywhere; leaving with one asks first.

Toolkit: Textual, which xt already depends on for the TUI. It wraps text to the terminal's width
(the 80-column criterion), keeps the input line apart from messages that arrive while you type,
and can be driven headlessly in tests and acceptance (Textual's Pilot).

From 0.22.0 (card #199) the conversation also holds a registered operator's messages to the
liaison and its delegated actions, labelled "NAME (operator)", and the liaison's own messages to
the team show as dimmed one-liners: ctrl+t cycles them hidden / goals / all (goals by default),
↑/↓ pick one and enter (with an empty draft) expands it. Every line is a ledger message.
"""

import datetime as dt
import re

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Input, Static

from .choices import hint, question_of, summary
from .context import Ctx
from .operators import is_operator_message
from .paths import XtError
from .ledger import PANE_LABEL, is_pane
from .team import HUMAN, SYSTEM

HISTORY = 30  # messages shown when chat starts (spec: the last 30)
REFRESH_S = 2.0  # how often chat reads the ledger: a delivered message shows within this (spec: 10 s)
EXIT_WORDS = ("/exit", "/quit")
HEADER_S = 30.0  # how often the header re-checks whether pane input is recorded (card #193)
MODES = ("hidden", "goals", "all")  # the liaison's team activity lines (card #199)
DEFAULT_MODE = "goals"  # Radek, 2026-10-03
PAGE_OVERLAP = 2  # rows PageUp / PageDown keep from the page before (card #210)
# xt's own lines about delegation, shown in the conversation (card #200: the drive grant ended)
DELEGATION = re.compile(r"^(human delegated |human revoked the delegation |drive grant for |pane input to )")


def liaison_of(ctx: Ctx) -> str:
    a = ctx.team.lead_of_role("liaison")
    if a is None:
        raise XtError("no liaison in team.toml: chat talks to the liaison")
    return a.name


def is_operator(m: dict, operators: set[str] = frozenset()) -> bool:
    """A message an operator sent (card #166/#200), as recorded or by a registered name."""
    return m["from"] in operators or is_operator_message(m)


def kind_of(m: dict, liaison: str, operators: set[str] = frozenset()) -> str | None:
    """"chat" for a message of the conversation, "activity" for one of the liaison's messages to
    the team (a one-liner, card #199), None for anything else."""
    if m["type"] == "note":
        return None
    if {m["from"], m["to"]} == {HUMAN, liaison}:
        return "chat"
    if m["type"] == "approval" and m["from"] == SYSTEM and m["to"] == HUMAN:
        return "chat"
    if is_operator(m, operators) and (m["to"] in (liaison, HUMAN)):
        return "chat"
    if m["type"] == "system" and m["from"] == SYSTEM and m["to"] == HUMAN and DELEGATION.match(m["body"]):
        return "chat"
    if m["from"] == liaison and m["to"] not in (HUMAN, liaison, SYSTEM) and m["to"] not in operators:
        return "activity"
    return None


def in_conversation(m: dict, liaison: str, operators: set[str] = frozenset()) -> bool:
    """A message of the human's conversation with the liaison: between the two of them (notes
    excluded), an approval waiting for the human (#183), an operator's message (#199)."""
    return kind_of(m, liaison, operators) == "chat"


def conversation(msgs: list[dict], liaison: str, limit: int = HISTORY,
                 operators: set[str] = frozenset()) -> list[dict]:
    """The last `limit` messages of the conversation, oldest first, with the liaison's activity
    since the first of them."""
    chat = [m for m in msgs if kind_of(m, liaison, operators) == "chat"][-limit:]
    first = chat[0]["id"] if chat else 0
    return [m for m in msgs if m["id"] >= first and kind_of(m, liaison, operators)]


def shows(m: dict, mode: str) -> bool:
    """Whether a one-liner shows in `mode`: goals only, or everything the liaison sent the team."""
    return mode == "all" or (mode == "goals" and m["type"] == "goal")


def pending(ctx: Ctx) -> list[dict]:
    """What waits for the human's answer, oldest first: open questions to the human and pending
    approvals, each as {"id", "kind", "question", "text"}."""
    from .spawn import Approvals

    out = []
    for item in ctx.ledger.open_items():
        if item["type"] == "ask" and item["owner"] == HUMAN:
            m = ctx.ledger.message(item["id"]) or {"body": item["title"]}
            out.append({"id": item["id"], "kind": "question", "from": item["opener"],
                        "question": question_of(m), "text": m["body"]})
    for rid in Approvals(ctx).pending():
        m = ctx.ledger.message(int(rid)) or {"body": f"approval #{rid}"}
        out.append({"id": int(rid), "kind": "approval", "from": "xt",
                    "question": {"kind": "closed"}, "text": m["body"]})
    return sorted(out, key=lambda p: p["id"])


def _time(ts: str) -> str:
    try:
        return dt.datetime.fromisoformat(ts).strftime("%H:%M")
    except (TypeError, ValueError):
        return "--:--"


HINT_SPARE = 4  # columns the hint and the header leave free (cards #202, #206)
FULL_WORDS = 100  # the hint uses its full words only above this width (card #206)
SHORT_FIRST = ("↑↓", "tab", "ctrl+t", "esc", "enter", "pgup/pgdn", "ctrl+d")  # which key takes short words first
# then which takes its shortest: `scroll` goes, then `tab answer (N)` becomes `tab (N)`, then a picked
# line's `collapse` becomes `close`; enter keeps its verb and ctrl+d its `leave` (xt #3389)
SHORTEST_FIRST = ("pgup/pgdn", "tab", "enter")


def hint_keys(waiting: int, answering: bool, picked: str | None, mode: str, pickable: bool = True,
              target: int | None = None) -> list[tuple[str, tuple[str, str, str]]]:
    """The keys the hint names in this state, each with its words in three tiers (full, short,
    shortest), in order (card #206; the inventory its test asserts):

    - plain: enter send, (↑↓ pick when a line can be picked), ctrl+t MODE, pgup/pgdn, ctrl+d leave
    - questions waiting: the same with `tab answer (N)` after enter
    - answering: enter send #N, esc back, ctrl+t, pgup/pgdn, ctrl+d leave
    - a one-liner picked: enter expand, ↑↓ pick, esc back, ctrl+t, pgup/pgdn, ctrl+d leave
    - hidden mode: as plain, never pick (card #204)
    """
    pick = ("↑↓", ("pick a line", "pick", "pick"))
    if answering:
        n = f"#{target}" if target is not None else ""
        keys = [("enter", (f"send {n}".strip(), f"send {n}".strip(), f"send {n}".strip())),
                ("esc", ("message the liaison", "back", "back"))]
    elif picked:
        word = "expand" if picked == "picked" else "collapse"
        keys = [("enter", (word, word, "expand" if picked == "picked" else "close")), pick,
                ("esc", ("back", "back", "back"))]
    else:
        keys = [("enter", ("send", "send", "send"))]  # never a bare enter (ux on rc2, xt #3389)
        if waiting:
            keys.append(("tab", (f"answer ({waiting} waiting)", f"answer ({waiting})", f"({waiting})")))
        if pickable and mode != "hidden":
            keys.append(pick)
    return keys + [("ctrl+t", (f"team activity ({mode})", mode, mode)),
                   ("pgup/pgdn", ("scroll", "scroll", "")),
                   ("ctrl+d", ("leave", "leave", "leave"))]


def hint_line(width: int, waiting: int, answering: bool, picked: str | None, mode: str,
              pickable: bool = True, target: int | None = None) -> str:
    """The keys under the input line in one row of `width` with HINT_SPARE columns to spare
    (cards #199, #206): the longest tier that fits (full words only above FULL_WORDS columns),
    every key named in each. Below 80 columns, where nothing is promised, the shortest tier is cut
    at the end. `picked`: None, "picked" or "expanded" (a one-liner chosen with ↑/↓); `pickable`:
    a one-liner is shown to pick (card #204); `target`: the question being answered."""
    keys = hint_keys(waiting, answering, picked, mode, pickable, target)

    def line(tier: dict[str, int]) -> str:
        return " · ".join(f"{k} {w[tier.get(k, 1)]}".strip() for k, w in keys)

    # Shorter words come in one key at a time, the least needed first, so the line keeps as many
    # words as fit: full words (above FULL_WORDS only), then short, then shortest.
    tier = {k: 0 for k, _ in keys} if width > FULL_WORDS else {}
    tiers = [line(tier)]
    for k in SHORT_FIRST:
        tier = {**tier, k: 1}
        tiers.append(line(tier))
    for k in SHORTEST_FIRST:
        tier = {**tier, k: 2}
        tiers.append(line(tier))
    fits = [t for t in tiers if Text(t).cell_len <= width - HINT_SPARE]
    best = fits[0] if fits else tiers[-1]
    return best if Text(best).cell_len <= width else best[:max(width - 1, 0)] + "…"


OPERATOR_PREFIX = "» "  # with "(operator)", tells an operator's lines from yours without colour (#199)


def render(m: dict, open_ids: set[int], answers: dict[int, dict], operators: set[str] = frozenset()) -> Text:
    """One message as chat shows it: time, who, the text (wrapped by the widget), and for a question
    its type and whether it waits for you or what you answered."""
    out = Text()
    out.append(f"{_time(m['ts'])} ", style="bright_black")
    if is_operator(m, operators):
        out.append(f"{OPERATOR_PREFIX}{m['from']} (operator)", style="bold magenta")
    else:
        who = "you" if m["from"] == HUMAN else "xt" if m["from"] == SYSTEM else m["from"]
        out.append(who, style="bold cyan" if who == "you" else "bold yellow" if who == "xt" else "bold")
        if is_pane(m):  # card #193: what was typed in the pane, not proven to be you
            out.append(f" ({PANE_LABEL})", style="yellow")
    out.append(f"  #{m['id']}", style="bright_black")
    if m["type"] in ("ask", "approval") and m["to"] == HUMAN:
        kind = summary(question_of(m)) or "open question"
        out.append(f"  ⚑ {kind}", style="yellow")
    out.append("\n" + m["body"].rstrip())
    if m["id"] in open_ids:
        out.append("\n⚑ waits for your answer: tab picks it", style="bold yellow")
    elif m["id"] in answers:
        a = answers[m["id"]]
        by = f" by {a['from']} (operator)" if a["from"] != HUMAN else ""
        out.append(f"\n✓ answered{by} #{a['id']}: {a['body'].splitlines()[0] if a['body'] else ''}", style="green")
    return out


def one_liner(m: dict, expanded: bool = False, selected: bool = False) -> Text:
    """One of the liaison's messages to the team, dimmed: `HH:MM to lead: goal #3020 Patch release`,
    cut to one row with an ellipsis, or with its full text when expanded (card #199)."""
    body = m["body"].strip()
    first = body.splitlines()[0] if body else ""
    head = f"{'›' if selected else ' '} {_time(m['ts'])} to {m['to']}: {m['type']} #{m['id']}"
    style = "bold" if selected else "dim"
    # one row with an ellipsis comes from the widget's CSS (.activity); expanded wraps
    return Text(f"{head}\n{body}" if expanded else f"{head} {first}", style=style)


def question_box(p: dict) -> Text:
    """The question being answered, in full: its text with every option, wrapped by the widget."""
    out = Text()
    label = "Approval" if p["kind"] == "approval" else "Question"
    out.append(f"{label} #{p['id']} from {p['from']} · {hint(p['question'])}\n", style="bold yellow")
    out.append(p["text"].rstrip())
    return out


class ChatApp(App):
    """The chat: the conversation above, the question being answered (if any), the input line."""

    CSS = """
    Screen { background: ansi_default; }
    #header { height: auto; color: ansi_bright_black; }
    #history { height: 1fr; scrollbar-size-vertical: 1; }
    #newmark { display: none; height: 1; color: ansi_yellow; text-style: bold; }
    #newmark.shown { display: block; }
    .msg { margin: 0 0 1 0; }
    .activity { margin: 0 0 1 0; text-wrap: nowrap; text-overflow: ellipsis; }
    .activity.expanded { text-wrap: wrap; }
    #question { display: none; height: auto; max-height: 70%; border: solid ansi_yellow; padding: 0 1; }
    #question.shown { display: block; }
    #line { height: 1; }
    #target { width: auto; color: ansi_cyan; text-style: bold; }
    #draft { border: none; padding: 0; height: 1; background: ansi_default; }
    #status { height: auto; color: ansi_bright_black; }
    """

    BINDINGS = [
        Binding("ctrl+d", "leave", show=False, priority=True),
        Binding("ctrl+q", "leave", show=False, priority=True),
        Binding("ctrl+c", "leave", show=False, priority=True),
        Binding("tab", "next_target", show=False, priority=True),
        Binding("escape", "to_liaison", show=False, priority=True),
        # card #199: the draft has the focus, so a plain `t` types; ctrl+t cycles the team activity
        Binding("ctrl+t", "cycle_activity", show=False, priority=True),
        Binding("up", "select(-1)", show=False, priority=True),
        Binding("down", "select(1)", show=False, priority=True),
        # card #210: the history scrolls while the draft keeps the focus (the input doesn't use the
        # page keys; Home and End leave it, ctrl+a and ctrl+e still move its cursor). No g/G: chat is
        # oldest at the top, Flow newest, so the same letters would mean the opposite.
        Binding("pageup", "page(-1)", show=False, priority=True),
        Binding("pagedown", "page(1)", show=False, priority=True),
        Binding("home", "history_home", show=False, priority=True),
        Binding("end", "history_end", show=False, priority=True),
    ]

    def __init__(self, ctx: Ctx, refresh_s: float = REFRESH_S):
        super().__init__()
        from .operators import names

        self.ctx = ctx
        self.refresh_s = refresh_s
        self.liaison = liaison_of(ctx)
        self.operators = set(names(ctx.paths))
        self.last_id = 0
        self.waiting: list[dict] = []
        self.target: dict | None = None  # None: a message to the liaison; else the question answered
        self.warned = False  # leaving with a draft asks once
        self.shown: dict[int, Static] = {}  # conversation messages by id
        self.activity: dict[int, tuple[Static, dict]] = {}  # the liaison's one-liners by id (#199)
        self.mode = DEFAULT_MODE
        self.selected: int | None = None  # the one-liner ↑/↓ picked
        self.expanded: set[int] = set()
        self.pane: tuple[str, str, str, str] | None = None  # the pane-input state (paneinput), read every HEADER_S
        self.unseen = 0  # lines that arrived while the view was scrolled up (card #210)
        self._width = 0  # set by each resize
        self.stick = True  # the view is at the end and follows new lines (card #210)

    def compose(self) -> ComposeResult:
        yield Static(id="header")
        yield VerticalScroll(id="history")
        yield Static(id="newmark")
        yield Static(id="question")
        with Horizontal(id="line"):
            yield Static(id="target")
            yield Input(id="draft", placeholder="type a message and press enter")
        yield Static(id="status")

    def on_mount(self) -> None:
        self.title = f"xt chat with {self.liaison}"
        msgs = list(self.ctx.ledger.messages())
        self.last_id = msgs[-1]["id"] if msgs else 0
        self.load(conversation(msgs, self.liaison, operators=self.operators), msgs, follow=True)
        self.query_one("#draft", Input).focus()
        history = self.query_one("#history", VerticalScroll)
        self.watch(history, "scroll_y", self._scrolled, init=False)
        self.watch(history, "virtual_size", self._grown, init=False)
        self.set_interval(self.refresh_s, self.refresh_messages)
        self.update_header()
        self.set_interval(HEADER_S, self.update_header)

    def update_header(self) -> None:
        """Who you talk to, and whether what you type in the liaison's pane is recorded (card #193),
        read again every HEADER_S; drawn to the width by `paint_header` (cards #201, #202)."""
        from .paneinput import state

        try:
            self.pane = state(self.ctx)
        except Exception:  # a header line must never stop the chat
            self.pane = None
        self.paint_header()

    @property
    def width(self) -> int:
        """The terminal's width; the newest a resize said (card #206: it may arrive before `size`)."""
        return self._width or self.size.width

    def paint_header(self) -> None:
        from .paneinput import header

        self.query_one("#header", Static).update(header(self.pane, self.liaison, self.width))

    def on_resize(self, event) -> None:
        self._width = event.size.width
        self.paint_header()
        self.update_line()

    # --- the conversation ------------------------------------------------------------------------

    def _answers(self, msgs: list[dict]) -> dict[int, dict]:
        """{question id: the first reply to it from the human, or from an operator under drive}."""
        out: dict[int, dict] = {}
        for m in msgs:
            by_operator = isinstance(m.get("delegated"), dict) and "answer" in m  # card #200
            if (m["from"] == HUMAN or by_operator) and m.get("ref") is not None and not is_pane(m):
                out.setdefault(m["ref"], m)
        return out

    def load(self, shown: list[dict], msgs: list[dict], follow: bool = False) -> None:
        """Show `shown` (oldest first) below what's there, then the questions waiting. The view
        follows new lines only when it was at the end (or `follow`): an arriving line never moves
        what the human scrolled up to read (card #199)."""
        self.waiting = pending(self.ctx)
        open_ids = {p["id"] for p in self.waiting}
        answers = self._answers(msgs)
        history = self.query_one("#history", VerticalScroll)
        at_end = follow or self.stick
        for m in shown:
            if kind_of(m, self.liaison, self.operators) == "activity":
                w = Static(one_liner(m), classes="activity")
                w.display = shows(m, self.mode)
                self.activity[m["id"]] = (w, m)
            else:
                w = Static(render(m, open_ids, answers, self.operators), classes="msg")
                self.shown[m["id"]] = w
            w.msg_id = m["id"]  # every line is a ledger message (card #199, criterion 4)
            history.mount(w)
            if not at_end and w.display:  # card #210: counted for the marker
                self.unseen += 1
        for qid, w in self.shown.items():  # a question answered meanwhile (here, in the TUI, …)
            if qid in answers or qid not in open_ids:
                m = self.ctx.ledger.message(qid)
                if m and m["type"] in ("ask", "approval"):
                    w.update(render(m, open_ids, answers, self.operators))
        if self.target and self.target["id"] not in open_ids:
            self.target = None
        self.update_line()
        if at_end:
            self.unseen = 0
            self.stick = True
            history.scroll_end(animate=False)
        self.paint_mark()

    # --- scrolling the history (card #210) -------------------------------------------------------

    def _at_end(self) -> bool:
        history = self.query_one("#history", VerticalScroll)
        return history.scroll_y >= history.max_scroll_y - 1

    def _scrolled(self, _y: float) -> None:
        self.stick = self._at_end()
        if self.unseen and self.stick:
            self.unseen = 0
            self.paint_mark()

    def _grown(self, _size) -> None:
        """New lines got their height: a view that was at the end stays there."""
        if self.stick:
            self.query_one("#history", VerticalScroll).scroll_end(animate=False)

    def paint_mark(self) -> None:
        """One line under the history while lines that arrived wait below the view: `↓ N new (End)`."""
        mark = self.query_one("#newmark", Static)
        mark.update(f"↓ {self.unseen} new (End)")
        mark.set_class(bool(self.unseen), "shown")

    def action_page(self, step: int) -> None:
        """PageUp / PageDown: the history by a page, two rows kept from the page before."""
        history = self.query_one("#history", VerticalScroll)
        page = max(1, history.scrollable_content_region.height - PAGE_OVERLAP)
        history.scroll_to(y=history.scroll_y + step * page, animate=False)

    def action_history_home(self) -> None:
        self.query_one("#history", VerticalScroll).scroll_home(animate=False)

    def action_history_end(self) -> None:
        self.query_one("#history", VerticalScroll).scroll_end(animate=False)

    def refresh_messages(self, follow: bool = False) -> None:
        """Read what's new in the ledger and show it (every REFRESH_S)."""
        msgs = list(self.ctx.ledger.messages(since_days=1))
        new = [m for m in msgs if m["id"] > self.last_id]
        if new:
            self.last_id = new[-1]["id"]
        self.load([m for m in new if kind_of(m, self.liaison, self.operators)], msgs, follow)

    # --- the liaison's team activity (card #199) ---------------------------------------------------

    def _visible(self) -> list[int]:
        return [i for i, (_, m) in self.activity.items() if shows(m, self.mode)]

    def _paint(self, mid: int) -> None:
        w, m = self.activity[mid]
        w.set_class(mid in self.expanded, "expanded")
        w.update(one_liner(m, mid in self.expanded, mid == self.selected))

    def action_cycle_activity(self) -> None:
        """ctrl+t: the one-liners hidden → goals → all → hidden."""
        self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
        for w, m in self.activity.values():
            w.display = shows(m, self.mode)
        if self.selected is not None and self.selected not in self._visible():
            old, self.selected = self.selected, None
            self._paint(old)
        self.update_line()

    def action_select(self, step: int) -> None:
        """↑/↓: pick the previous or next one-liner shown; past either end, none."""
        ids = self._visible()
        if not ids:
            self.update_line(f"no team activity lines shown (ctrl+t: {self._next_mode()})")
            return
        old = self.selected
        if old not in ids:
            self.selected = ids[-1] if step < 0 else ids[0]
        else:
            at = ids.index(old) + step
            self.selected = ids[at] if 0 <= at < len(ids) else None
        for mid in {old, self.selected} - {None}:
            self._paint(mid)
        if self.selected is not None:
            self.query_one("#history", VerticalScroll).scroll_to_widget(self.activity[self.selected][0], animate=False)
        self.update_line()

    def toggle_selected(self) -> None:
        """enter on an empty draft: expand or collapse the one-liner picked."""
        self.expanded ^= {self.selected}
        self._paint(self.selected)

    def _next_mode(self) -> str:
        return MODES[(MODES.index(self.mode) + 1) % len(MODES)]

    # --- the input line --------------------------------------------------------------------------

    def update_line(self, status: str | None = None) -> None:
        box = self.query_one("#question", Static)
        if self.target:
            box.update(question_box(self.target))
            box.add_class("shown")
            label = f"answer #{self.target['id']} › "
        else:
            box.remove_class("shown")
            label = f"{self.liaison} › "
        self.query_one("#target", Static).update(label)
        if status is None:
            picked = None if self.selected is None else "expanded" if self.selected in self.expanded else "picked"
            status = hint_line(self.width, len(self.waiting), bool(self.target), picked, self.mode,
                               bool(self._visible()), self.target["id"] if self.target else None)
        self.query_one("#status", Static).update(status)

    def action_next_target(self) -> None:
        """tab: the next question waiting for an answer, then back to the liaison."""
        if not self.waiting:
            self.update_line("nothing waits for your answer")
            return
        ids = [p["id"] for p in self.waiting]
        at = ids.index(self.target["id"]) + 1 if self.target and self.target["id"] in ids else 0
        self.target = self.waiting[at] if at < len(ids) else None
        self.update_line()

    def action_to_liaison(self) -> None:
        """esc: back from an answer to messaging the liaison, or from a picked one-liner to the
        draft (card #206: the hint's `esc back`)."""
        if self.target is None and self.selected is not None:
            old, self.selected = self.selected, None
            self._paint(old)
        self.target = None
        self.update_line()

    def on_input_changed(self, event: Input.Changed) -> None:
        self.warned = False
        if event.value and self.selected is not None:  # typing goes back to the draft
            old, self.selected = self.selected, None
            self._paint(old)
            self.update_line()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            if self.selected is not None:
                self.toggle_selected()
                self.update_line()
            return
        if text.lower() in EXIT_WORDS:
            event.input.value = ""
            self.exit(0)
            return
        try:
            result = self.answer(text) if self.target else self.send(text)
        except XtError as e:  # the draft stays in the box: fix it and press enter again
            from .cli import AlreadyAnswered

            self.update_line(str(e) if isinstance(e, AlreadyAnswered) else f"not sent: {e}")  # #203
            return
        event.input.value = ""
        self.target = None
        self.refresh_messages(follow=True)
        self.update_line(result)

    def send(self, text: str) -> str:
        from .dispatch import send

        msg, status = send(self.ctx, HUMAN, self.liaison, "ask", text)  # as the TUI's S sends it
        return f"#{msg['id']} to {self.liaison}: {status}"

    def answer(self, text: str) -> str:
        """The answer to the question picked with tab, through the one answer path (`xt answer`):
        checked against its type, a number recorded as the option's full text."""
        from .cli import answer

        return answer(self.ctx, HUMAN, self.target["id"], text)

    def action_leave(self) -> None:
        """ctrl+d (or /exit): leave; with an unsent draft, ask once first. The draft is never saved."""
        draft = self.query_one("#draft", Input).value
        if draft.strip() and not self.warned:
            self.warned = True
            self.update_line("your draft isn't sent and isn't saved anywhere: ctrl+d again leaves and "
                             "discards it; enter sends it")
            return
        self.exit(0)


def run(ctx: Ctx) -> None:
    ChatApp(ctx).run()
