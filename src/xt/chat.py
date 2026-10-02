"""`xt chat`: one conversation with the liaison in the terminal (card #184).

The conversation is a view over the ledger, shared with the TUI (Q1): the messages between the
human and the liaison, and the approvals waiting for the human, read from the log. Chat stores
nothing of its own: what it sends is an ordinary ledger message (the same as the TUI's `S`), an
answer goes through `cli.answer` (the same as `xt answer`), and a typed but unsent draft lives
only in the input box. It is never written anywhere; leaving with one asks first.

Toolkit: Textual, which xt already depends on for the TUI. It wraps text to the terminal's width
(the 80-column criterion), keeps the input line apart from messages that arrive while you type,
and can be driven headlessly in tests and acceptance (Textual's Pilot).
"""

import datetime as dt

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Input, Static

from .choices import hint, question_of, summary
from .context import Ctx
from .paths import XtError
from .team import HUMAN, SYSTEM

HISTORY = 30  # messages shown when chat starts (spec: the last 30)
REFRESH_S = 2.0  # how often chat reads the ledger: a delivered message shows within this (spec: 10 s)
EXIT_WORDS = ("/exit", "/quit")


def liaison_of(ctx: Ctx) -> str:
    a = ctx.team.lead_of_role("liaison")
    if a is None:
        raise XtError("no liaison in team.toml: chat talks to the liaison")
    return a.name


def in_conversation(m: dict, liaison: str) -> bool:
    """A message of the human's conversation with the liaison: between the two of them (notes
    excluded), or an approval waiting for the human (#183)."""
    if m["type"] == "note":
        return False
    if {m["from"], m["to"]} == {HUMAN, liaison}:
        return True
    return m["type"] == "approval" and m["from"] == SYSTEM and m["to"] == HUMAN


def conversation(msgs: list[dict], liaison: str, limit: int = HISTORY) -> list[dict]:
    """The last `limit` messages of the conversation, oldest first."""
    return [m for m in msgs if in_conversation(m, liaison)][-limit:]


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


def render(m: dict, open_ids: set[int], answers: dict[int, dict]) -> Text:
    """One message as chat shows it: time, who, the text (wrapped by the widget), and for a question
    its type and whether it waits for you or what you answered."""
    who = "you" if m["from"] == HUMAN else "xt" if m["from"] == SYSTEM else m["from"]
    out = Text()
    out.append(f"{_time(m['ts'])} ", style="bright_black")
    out.append(who, style="bold cyan" if who == "you" else "bold yellow" if who == "xt" else "bold")
    out.append(f"  #{m['id']}", style="bright_black")
    if m["type"] in ("ask", "approval") and m["to"] == HUMAN:
        kind = summary(question_of(m)) or "open question"
        out.append(f"  ⚑ {kind}", style="yellow")
    out.append("\n" + m["body"].rstrip())
    if m["id"] in open_ids:
        out.append("\n⚑ waits for your answer: tab picks it", style="bold yellow")
    elif m["id"] in answers:
        a = answers[m["id"]]
        out.append(f"\n✓ answered #{a['id']}: {a['body'].splitlines()[0] if a['body'] else ''}", style="green")
    return out


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
    #history { height: 1fr; scrollbar-size-vertical: 1; }
    .msg { margin: 0 0 1 0; }
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
    ]

    def __init__(self, ctx: Ctx, refresh_s: float = REFRESH_S):
        super().__init__()
        self.ctx = ctx
        self.refresh_s = refresh_s
        self.liaison = liaison_of(ctx)
        self.last_id = 0
        self.waiting: list[dict] = []
        self.target: dict | None = None  # None: a message to the liaison; else the question answered
        self.warned = False  # leaving with a draft asks once
        self.shown: dict[int, Static] = {}

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="history")
        yield Static(id="question")
        with Horizontal(id="line"):
            yield Static(id="target")
            yield Input(id="draft", placeholder="type a message and press enter")
        yield Static(id="status")

    def on_mount(self) -> None:
        self.title = f"xt chat with {self.liaison}"
        msgs = list(self.ctx.ledger.messages())
        self.last_id = msgs[-1]["id"] if msgs else 0
        self.load(conversation(msgs, self.liaison), msgs)
        self.query_one("#draft", Input).focus()
        self.set_interval(self.refresh_s, self.refresh_messages)

    # --- the conversation ------------------------------------------------------------------------

    def _answers(self, msgs: list[dict]) -> dict[int, dict]:
        """{question id: the human's first reply to it} among `msgs`."""
        out: dict[int, dict] = {}
        for m in msgs:
            if m["from"] == HUMAN and m.get("ref") is not None:
                out.setdefault(m["ref"], m)
        return out

    def load(self, shown: list[dict], msgs: list[dict]) -> None:
        """Show `shown` (oldest first) below what's there, then the questions waiting."""
        self.waiting = pending(self.ctx)
        open_ids = {p["id"] for p in self.waiting}
        answers = self._answers(msgs)
        history = self.query_one("#history", VerticalScroll)
        for m in shown:
            w = Static(render(m, open_ids, answers), classes="msg")
            self.shown[m["id"]] = w
            history.mount(w)
        for qid, w in self.shown.items():  # a question answered meanwhile (here, in the TUI, …)
            if qid in answers or qid not in open_ids:
                m = self.ctx.ledger.message(qid)
                if m and m["type"] in ("ask", "approval"):
                    w.update(render(m, open_ids, answers))
        if self.target and self.target["id"] not in open_ids:
            self.target = None
        self.update_line()
        history.scroll_end(animate=False)

    def refresh_messages(self) -> None:
        """Read what's new in the ledger and show it (every REFRESH_S)."""
        msgs = list(self.ctx.ledger.messages(since_days=1))
        new = [m for m in msgs if m["id"] > self.last_id]
        if new:
            self.last_id = new[-1]["id"]
        self.load([m for m in new if in_conversation(m, self.liaison)], msgs)

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
            keys = ["enter send"]
            if self.waiting:
                n = len(self.waiting)
                keys.append(f"tab answer ({n} waiting)" if not self.target else "tab next · esc message the liaison")
            keys.append("ctrl+d leave")
            status = " · ".join(keys)
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
        self.target = None
        self.update_line()

    def on_input_changed(self, event: Input.Changed) -> None:
        self.warned = False

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        if text.lower() in EXIT_WORDS:
            event.input.value = ""
            self.exit(0)
            return
        try:
            result = self.answer(text) if self.target else self.send(text)
        except XtError as e:  # the draft stays in the box: fix it and press enter again
            self.update_line(f"not sent: {e}")
            return
        event.input.value = ""
        self.target = None
        self.refresh_messages()
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
