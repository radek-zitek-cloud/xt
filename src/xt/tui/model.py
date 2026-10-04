"""What the TUI shows: the team's files and Herdr's live state, turned into panel rows.

Each row's detail is a function, so expensive parts (reading a pane, a role file) run only for
the row the human is looking at.
"""

import datetime as dt
import json
import re
import textwrap
from dataclasses import dataclass, field
from typing import Callable

from rich.text import Text

from .. import permissions
from ..adapters import load_adapters
from ..context import Ctx
from ..dispatch import Queue
from ..lifecycle import Jobs
from ..paths import XtError
from ..alerts import FAILURES
from ..inbox import answer_text, fold_labels  # shared with `xt inbox --seen` (card #179)
from ..team import HUMAN, SYSTEM, harness_model, schedule_text
from . import flow, teampane
from .flow import Data as FlowData
from ..ledger import sender
from .teampane import Harness, shown_model
from .thread import ThreadDetail, thread_of

# the numbered panes, 1-3; Team is 0 and Detail 4 (card #157). Work (card #129) replaced Goals and
# Tasks, the Supervisor is a pop-up on `v` (card #131) and Flow replaced the Log (card #130).
PANELS = ("Inbox", "Work", "Flow")
# the Inbox's folds (cards #127, #157): their rows carry the fold's key in `under`
FRICTION_FOLD, EARLIER_FOLD, ANSWERED_FOLD = "fold:friction", "fold:earlier", "fold:answered"
INBOX_HEADINGS = ("NEEDS YOU", "NOTIFICATIONS", "FRICTION")  # the demo uses them too (card #177)
STATUS_STYLE = {"idle": "green", "done": "green", "working": "yellow", "blocked": "red"}
TYPE_STYLE = {"goal": "magenta", "task": "magenta", "done": "green", "report": "cyan", "ask": "cyan",
              "alert": "red", "approval": "yellow", "nudge": "yellow", "note": "bright_black",
              "system": "bright_black"}
HISTORY_DAYS = 30
CONTINUED = "↳ "
SEEN_KEYS = "clears from Notifications once you leave the Inbox · S: message the liaison"


def screen_lines(screen: str, keep: int = 25) -> list[tuple[str, int]]:
    """The pane's last lines as the terminal shows them: blank lines dropped, a line repeated
    several times in a row shown once with its count (card #98)."""
    out: list[tuple[str, int]] = []
    for ln in (ln.rstrip() for ln in screen.splitlines()):
        if not ln.strip():
            continue
        if out and out[-1][0] == ln:
            out[-1] = (ln, out[-1][1] + 1)
        else:
            out.append((ln, 1))
    return out[-keep:]


class ScreenPreview:
    """Captured pane lines laid out at the detail pane's width: each captured line starts a new
    line, and a line too long for the pane continues on indented lines marked ↳, so text is never
    re-wrapped into ambiguous fragments and nothing is cut off."""

    def __init__(self, lines: list[tuple[str, int]]):
        self.lines = lines

    @property
    def plain(self) -> str:
        return "".join(f"{ln}{f'  (×{n})' if n > 1 else ''}\n" for ln, n in self.lines)

    def rows(self, width: int) -> list[str]:
        out: list[str] = []
        for ln, n in self.lines:
            text = ln + (f"  (×{n})" if n > 1 else "")
            # terminal layout padding (right-aligned tips, status bars) would push text off the pane
            lead = text[: len(text) - len(text.lstrip())][:8]
            text = lead + re.sub(r" {4,}", "   ", text.lstrip())
            out += textwrap.wrap(text.lstrip(), width=max(width, 20), initial_indent=lead,
                                 subsequent_indent=lead + "  " + CONTINUED, break_on_hyphens=False) or [lead]
        return out

    def __rich_console__(self, console, options):
        for row in self.rows(options.max_width):
            yield Text(row, style="bright_black", no_wrap=True, overflow="crop")


class Detail:
    """An agent's detail: its text, then its screen preview laid out at the pane's width."""

    def __init__(self, text: Text, screen: ScreenPreview):
        self.text, self.screen = text, screen

    @property
    def plain(self) -> str:
        return self.text.plain + self.screen.plain

    def __rich_console__(self, console, options):
        yield self.text
        yield self.screen


@dataclass
class Row:
    key: str
    text: Text
    detail: Callable[[], Text]
    kind: str = ""
    data: dict = field(default_factory=dict)
    age: str = ""  # shown dim at the row's right edge (card #132)


@dataclass
class Snapshot:
    panels: dict[str, list[Row]]  # the list panels, "Team": the agents, "Supervisor": the pop-up's events
    header: Text  # the Team pane's first line: team, xt version, what's running, what needs the human
    spend: str = ""  # on its right: today's tokens and estimated cost
    harnesses: list[Harness] = field(default_factory=list)  # the Team pane's blocks and their windows
    done_upto: int = 0  # the Inbox's done goals are seen up to here once the human has looked (#125)
    inbox_title: str = ""  # the Inbox's counts, `⚑ 1 · ✉ 2 · ✱ 1` (card #127)
    work_title: str = ""  # the Work pane's counts, `1 open · 63 done` (card #129)
    flow: FlowData = field(default_factory=FlowData)  # what the Flow chart draws (card #130)
    header_detail: Callable[[], object] | None = None  # Detail for the Team header row (card #151)


def age_text(secs: float) -> str:
    """A row's relative age (card #132): whole units rounded down; under 10 s `now`, then seconds,
    minutes, hours, days up to 59, and whole weeks from 60 days."""
    s = max(0, int(secs))
    if s < 10:
        return "now"
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    days = s // 86400
    return f"{days}d" if days < 60 else f"{days // 7}w"


def row_age(ts: str | None, now: dt.datetime) -> str:
    return age_text((now - dt.datetime.fromisoformat(ts)).total_seconds()) if ts else ""


def fit(text: Text, age: str, width: int) -> Text:
    """One row at the pane's width in terminal cells: the text cut with `…` only when it doesn't fit,
    the age dim at the right edge, never over the text (card #132)."""
    line = text.copy()
    line.no_wrap, line.end = True, ""
    if width <= 0:
        return line
    if age and width < len(age) + 3:
        age = ""  # too narrow for both: the text wins
    room = width - (len(age) + 1 if age else 0)
    if line.cell_len > room:
        line.truncate(room, overflow="ellipsis")
    if age:
        line.append(" " * (width - len(age) - line.cell_len))
        line.append(age, style="bright_black")
    return line


def _t(*parts) -> Text:
    out = Text(no_wrap=True, overflow="ellipsis")
    for p in parts:
        if isinstance(p, Text):
            out.append_text(p)
        elif isinstance(p, str):
            out.append(p)
        else:
            out.append(p[0], style=p[1])
    return out


def _age(ts: str, now: dt.datetime) -> str:
    secs = max(0, int((now - dt.datetime.fromisoformat(ts)).total_seconds()))
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


def _first_line(s: str, width: int = 70) -> str:
    line = s.strip().splitlines()[0] if s.strip() else ""
    return line if len(line) <= width else line[: width - 1] + "…"


def _line(s: str) -> str:
    """A list row's first line, uncut: the pane cuts it at its own width (card #132)."""
    return s.strip().splitlines()[0] if s.strip() else ""


def _msg_block(m: dict) -> Text:
    ref = f" ref:#{m['ref']}" if m.get("ref") is not None else ""
    out = Text()
    out.append(f"#{m['id']} {m['ts'][:16].replace('T', ' ')} ", style="bright_black")
    out.append(m["type"], style=TYPE_STYLE.get(m["type"], "bold"))
    out.append(f"  {sender(m)} → {m['to']}{ref}\n")  # pane input: unverified (card #193)
    out.append(m["body"].rstrip() + "\n")
    return out


def _file_text(ctx: Ctx, rel: str, max_lines: int = 60) -> Text:
    path = ctx.paths.root / rel
    if not path.is_file():
        return Text(f"({rel} not found)\n", style="bright_black")
    lines = path.read_text(errors="replace").splitlines()
    more = f"\n… {len(lines) - max_lines} more lines in {rel}\n" if len(lines) > max_lines else "\n"
    return Text("\n".join(lines[:max_lines]) + more)


def _heading(s: str) -> Text:
    return Text(f"\n── {s} ──\n", style="bold")


def approval_data(rid: str, r: dict, ts: str | None) -> dict:
    """An approval row's data: a closed question with the request as its narrative (card #183)."""
    from ..approvals import approval_what

    caps = f"\n{r['caps_note']}" if r.get("caps_note") else ""  # card #186: the `s` dialog shows it too
    return {"id": int(rid), "ts": ts, "question": {"kind": "closed"},
            "text": f"{r['requester']} asks to {approval_what(r)}.{caps}\n\nAnswer yes (approve) or no (deny)."}


def build(ctx: Ctx) -> Snapshot:
    ctx.reload_team()
    now = ctx.ledger.clock()
    msgs = list(ctx.ledger.messages(since_days=HISTORY_DAYS))
    open_items = {i["id"]: i for i in ctx.ledger.open_items()}
    try:
        live = ctx.herdr.agents()
    except XtError:
        live = {}
    queued, jobs = Queue(ctx).pending(), Jobs(ctx).pending()

    def thread(m: dict, head: Text, keys: str, more: Text | None = None) -> ThreadDetail:
        """Detail for a message: its head, then its thread, the goal's usage and the keys (#131)."""
        from .. import turns as _turns

        th = thread_of(m, msgs)
        root = th[0] if th[0]["type"] == "goal" else None
        usage = (f"usage (goal #{root['id']}): {_turns.fmt(_turns.goal_totals(ctx, root['id'], root['ts']))}"
                 if root else "usage: counted per goal; this thread has none")
        return ThreadDetail(head, th, m["id"], usage, keys, more, now, TYPE_STYLE)

    work_rows, work_title = _work(ctx, msgs, open_items, live, now, thread)

    # Team: roster with live state and context
    from .. import turns, usage

    spend = turns.today(ctx)
    contexts = usage.readings(ctx, [a.name for a in ctx.team.agents() if a.kind != HUMAN and a.active])
    from .. import launch

    unlaunched = launch.flagged(ctx)  # the supervisor's, status's or up's alert (card #165)
    team_rows = []
    for a in ctx.team.agents():
        if a.kind == HUMAN:
            continue
        la = live.get(a.name)
        state = la.status if la else ("retired" if not a.active else "not running")
        owned = [i for i in open_items.values() if i["owner"] == a.name]

        ctxr = contexts.get(a.name)

        def detail(a=a, la=la, state=state, owned=owned, ctxr=ctxr):
            out = Text()
            out.append(f"{a.name}", style="bold")
            wakes = f" · woken {schedule_text(a)}" if a.wake_every else ""
            out.append(f" · {a.role} · {harness_model(a.harness, a.model)} · reports to {a.reports_to}{wakes} · ")
            out.append(state + "\n", style=STATUS_STYLE.get(state, "bright_black"))
            if la and a.name in unlaunched:
                out.append(launch.warning(a.name) + "\n", style="bold red")
            if la:
                out.append(f"workspace {la.workspace_id} · pane {la.pane_id}  (f: jump there)\n", style="bright_black")
            if ctxr is not None and la:
                out.append(usage.describe(ctxr, now) + "\n", style="" if ctxr.known else "bright_black")
            elif ctxr is not None and ctxr.known:  # stopped: history, not a current reading
                out.append(f"last session: {usage.describe(ctxr, now)} (not running; a start begins a fresh "
                           f"session)\n", style="bright_black")
            from ..watch import next_wake

            nxt = next_wake(ctx, a) if a.active and a.wake_every else None
            if nxt:
                out.append(f"next wake-up: {dt.datetime.fromtimestamp(nxt):%a %d %b %H:%M}\n")
            mine_today = spend.agents_today.get(a.name)
            out.append(f"usage today: {turns.fmt(mine_today) if mine_today else 'none recorded'}\n")
            from .. import capstart
            from ..launch import codex_options_line

            # card #186: a started agent's caps row, in full words, holds the old settings, Codex and
            # connector lines (ux on rc6); one never started has no row, so it keeps them
            caps = capstart.detail_row(ctx, a, load_adapters(ctx.paths).get(a.harness))
            opts = codex_options_line(ctx, a, la is not None)  # card #169
            if caps:
                out.append(caps + "\n")
                if "(running with" in opts:  # a changed option still says what the agent runs with
                    out.append(opts + "\n", style="yellow")
            else:
                if a.connectors:
                    out.append(f"account connectors (opted in): {', '.join(a.connectors)}\n", style="yellow")
                settings_path = permissions.shown(ctx.team, a, load_adapters(ctx.paths).get(a.harness))
                if settings_path:
                    out.append(f"settings file: {settings_path}\n")
                if opts:
                    out.append(opts + "\n", style="yellow" if "network on" in opts else "")
            from ..lifecycle import queued, queued_text, suggestion

            entry = queued(ctx).get(a.name)
            if entry:  # card #134
                out.append(queued_text(entry) + f"  (cancel: xt reset {a.name} --cancel)\n", style="yellow")
            elif la:
                tip = suggestion(a.name, ctxr, dt.datetime.now(dt.timezone.utc).astimezone())
                if tip:
                    out.append(tip + "\n", style="yellow")
            out.append(_heading(f"open work ({len(owned)})"))
            for i in owned:
                out.append(f"#{i['id']} {i['type']} {_age(i['opened'], now)}  {i['title']}\n")
            if not owned:
                out.append("(none)\n", style="bright_black")
            mine = [m for m in msgs if a.name in (m["from"], m["to"])][-6:]
            out.append(_heading("recent messages"))
            for m in mine:
                out.append_text(_msg_block(m))
            if la:
                out.append(_heading("screen (last lines)"))
                try:
                    screen = ctx.herdr.read_pane(la.pane_id, lines=40)
                except XtError:
                    out.append("(couldn't read the pane)\n", style="bright_black")
                else:
                    return Detail(out, ScreenPreview(screen_lines(screen)))
            return out

        now_ctx = ctxr if la is not None and ctxr is not None and ctxr.known else None  # a stopped agent has none
        data = {"name": a.name, "workspace": la.workspace_id if la else None, "running": la is not None,
                "active": a.active, "role": a.role, "harness": a.harness or "?",
                "model": shown_model(a.model, ctxr.model if ctxr else None),
                "state": la.status if la else ("retired" if not a.active else "stopped"),
                "dot": "●" if la else "○",  # its colour follows the state (teampane.dot_style)
                "unlaunched": la is not None and a.name in unlaunched,  # card #165: a red ! instead
                "used": now_ctx.used if now_ctx else None, "window": now_ctx.window if now_ctx else None,
                "approximate": now_ctx.approximate if now_ctx else False}
        team_rows.append(Row(f"agent:{a.name}", teampane.cell(data, teampane.widths([data]), teampane.BAR_MAX),
                             detail, "agent", data))

    # Inbox: three groups, Needs you / New / Friction, empty groups hidden (card #127)
    from .. import inbox as _inbox
    from ..choices import hint, question_of, summary
    from ..goaldone import first_line

    box = _inbox.build(ctx, msgs, list(open_items.values()))
    by_id = {m["id"]: m for m in msgs}
    needs, new_rows, friction_rows = [], [], []
    for q in box.questions:
        def qdetail(q=q):
            out = Text()
            out.append(f"Question #{q['id']} from {q['opener']} · waiting {_age(q['opened'], now)}\n", style="bold yellow")
            m = by_id.get(q["id"]) or {"id": q["id"], "ts": q["opened"], "type": "ask", "from": q["opener"],
                                       "to": HUMAN, "body": q["title"]}
            out.append(m["body"] + "\n")
            more = None
            if q.get("about") is not None and by_id.get(q["about"]):
                more = _heading(f"about #{q['about']}")
                more.append_text(_msg_block(by_id[q["about"]]))
            typed = question_of(m)["kind"] != "open"  # say what the answer may be (#182)
            return thread(m, out, f"s: answer (goes to {q['opener']})"
                                  + (f" · {hint(question_of(m))}" if typed else "")
                                  + f" · S: message the liaison instead · or answer in {q['opener']}'s pane", more)

        body = by_id[q["id"]]["body"] if q["id"] in by_id else q["title"]
        question = question_of(by_id.get(q["id"]) or {"body": body})  # its declared type (#182)
        kind = summary(question)
        needs.append(Row(f"question:{q['id']}", _t(("⚑ ", "bold yellow"), f"#{q['id']} {q['opener']}: ",
                                                   _line(q["title"]),
                                                   (f"  {kind}", "yellow") if kind else ""),
                         qdetail, "question", {"id": q["id"], "opener": q["opener"], "text": body, "ts": q["opened"],
                                               "question": question},
                         row_age(q["opened"], now)))
    for rid, r in box.approvals:
        ts = by_id[int(rid)]["ts"] if int(rid) in by_id else None
        if r.get("kind") == "schedule":
            def sdetail(rid=rid, r=r):
                out = Text()
                out.append(f"Approval #{rid}: {r['requester']} asks to wake ", style="bold")
                out.append(r["name"], style="bold yellow")
                out.append(f" every {r['every']} when idle\n")
                if r.get("message"):
                    out.append(f"on each wake-up: {r['message']}\n")
                out.append("each wake-up is a billed agent turn · s: answer yes or no · a approve · d deny\n",
                           style="bright_black")
                agent = ctx.team.agent(r["name"])
                if agent and agent.role:
                    out.append(_heading(f"its role: roles/{agent.role}.md"))
                    out.append_text(_file_text(ctx, f"roles/{agent.role}.md"))
                return out

            needs.append(Row(f"approval:{rid}", _t(("⚑ ", "yellow"), f"#{rid} wake {r['name']} ",
                                                   (f"every {r['every']}", "bright_black"), ("  yes/no", "yellow")),
                             sdetail, "approval", approval_data(rid, r, ts), row_age(ts, now)))
            continue

        def detail(rid=rid, r=r):
            out = Text()
            out.append(f"Approval #{rid}: {r['requester']} asks to spawn ", style="bold")
            out.append(f"{r['name']}", style="bold yellow")
            out.append(f"\nrole {r['role']} · {harness_model(r['harness'], r.get('model'))}"
                       f" · reports to {r['reports_to']}\n")
            if r.get("settings_note"):
                out.append(r["settings_note"] + "\n",
                           style="bold red" if r["settings_note"].startswith("WARNING") else "")
            if r.get("caps_note"):  # card #186: what will be enforced, at decision time (ux on rc6)
                out.append(r["caps_note"] + "\n", style="bold")
            out.append("s: answer yes or no · a approve · d deny\n", style="bright_black")
            out.append(_heading(f"role brief: roles/{r['role']}.md"))
            out.append_text(_file_text(ctx, f"roles/{r['role']}.md"))
            return out

        needs.append(Row(f"approval:{rid}", _t(("⚑ ", "yellow"), f"#{rid} spawn {r['name']} ",
                                               (f"({r['role']}, {harness_model(r['harness'], r.get('model'))})",
                                                "bright_black"), ("  yes/no", "yellow")),
                         detail, "approval", approval_data(rid, r, ts), row_age(ts, now)))
    for key, al in box.alerts:
        def detail(key=key, al=al):
            out = Text()
            out.append(f"Alert #{al.get('id')} · {al.get('ts', '')[:16].replace('T', ' ')}\n", style="bold red")
            out.append(al["text"] + "\n")
            if int(al.get("count", 1)) > 1:
                out.append(f"{al['count']} times since it was raised, the last at "
                           f"{str(al.get('last', ''))[:16].replace('T', ' ')}\n", style="yellow")
            if key in FAILURES.values():
                out.append("the supervisor's log has the detail: v opens it\n", style="bright_black")
            m = by_id.get(al.get("id")) or {"id": al.get("id") or 0, "ts": al.get("ts") or now.isoformat(),
                                             "type": "alert", "from": SYSTEM, "to": HUMAN, "body": al["text"]}
            return thread(m, out, f"c: clear once dealt with ({key})")

        # a repeating supervisor failure shows its count first, where the row's cut never reaches it;
        # its age is that of the last failure (card #131)
        n = int(al.get("count", 1))
        needs.append(Row(f"alert:{key}", _t(("⚠ ", "red"), (f"×{n} ", "yellow") if n > 1 else "", _line(al["text"])),
                         detail, "alert", {"key": key, "ts": al.get("last") or al.get("ts")},
                         row_age(al.get("last") or al.get("ts"), now)))
    needs.sort(key=lambda r: r.data.get("ts") or "", reverse=True)  # newest on top (card #162)
    if box.answered:  # the human's decisions stay in view for a week (card #157)
        n = len(box.answered)
        needs.append(Row(ANSWERED_FOLD, _t((f"{fold_labels(box)['answered']} ▸", "bright_black")),
                         lambda n=n: Text(f"{n} questions you answered in the last {_inbox.EARLIER_DAYS} days, "
                                          "newest first: enter or space shows or hides them\n", style="bright_black"),
                         "fold", {"n": n}))
        for q, a in box.answered:
            def adetail(q=q, a=a):
                out = Text()
                out.append(f"Question #{q['id']} from {q['from']} · answered {a['ts'][:16].replace('T', ' ')}\n",
                           style="bold")
                out.append(q["body"] + "\n")
                out.append_text(_heading(f"your answer: #{a['id']}"))
                out.append(a["body"] + "\n")
                return thread(a, out, "answered already · S: message the liaison")

            needs.append(Row(f"answered:{q['id']}", _t(("✓ ", "bright_black"),
                                                       (f"#{q['id']} {_line(first_line(q['body'], 60))} → "
                                                        f"{_line(answer_text(a['body']))}", "bright_black")),
                             adetail, "answered", {"id": q["id"], "answer": a["id"], "folded": True,
                                                   "under": ANSWERED_FOLD}, row_age(a["ts"], now)))

    def new_row(m: dict, goal: dict | None, seen: bool) -> Row:
        """A Notifications row: a report to the human, or a goal of theirs that closed. Unread ones
        are bold (card #162); seen ones (card #157) are dim and folded under `(N earlier, seen)`."""
        keys = "seen already" if seen else SEEN_KEYS
        data = {"folded": True, "under": EARLIER_FOLD} if seen else {}
        dim = "bright_black" if seen else "bold"
        if goal is None:
            return Row(f"msg:{m['id']}", _t(("✉ ", "bright_black" if seen else "cyan"),
                                            (f"#{m['id']} {m['from']}: ", dim), (_line(m["body"]), dim)),
                       lambda m=m: thread(m, _msg_block(m), keys), "message", {"id": m["id"], **data},
                       row_age(m["ts"], now))

        def ddetail(goal=goal, done=m):
            out = Text()
            out.append(f"Goal #{goal['id']} done · {done['ts'][:16].replace('T', ' ')} by {done['from']}\n",
                       style="bold green")
            out.append(first_line(goal["body"], 200) + "\n", style="bold")
            out.append(_heading(f"closing summary: #{done['id']}"))
            out.append(done["body"] + "\n")
            return thread(done, out, keys)

        return Row(f"done:{goal['id']}", _t(("✓ ", "bright_black" if seen else "green"),
                                            (f"#{goal['id']} done: ", dim), (_line(goal["body"]), dim),
                                            (f"  #{m['id']}", "bright_black")),
                   ddetail, "done", {"id": goal["id"], "done": m["id"], **data}, row_age(m["ts"], now))

    new_rows = [new_row(m, goal, False) for m, goal in box.new]  # since the human last looked (#125, #127)
    if box.earlier:
        n = len(box.earlier)
        new_rows.append(Row(EARLIER_FOLD, _t((f"{fold_labels(box)['earlier']} ▸", "bright_black")),
                            lambda n=n: Text(f"{n} items from New you have seen in the last {_inbox.EARLIER_DAYS} days, "
                                             "newest first: enter or space shows or hides them\n",
                                             style="bright_black"),
                            "fold", {"n": n}))
        new_rows += [new_row(m, goal, True) for m, goal in box.earlier]
    for m in box.unread:
        friction_rows.append(Row(f"friction:{m['id']}", _t(("✱ ", "magenta"), f"#{m['id']} {m['from']}: ",
                                                          _line(m["body"])),
                                 lambda m=m: thread(m, _msg_block(m), "c: mark it seen now · seen once you leave "
                                                                      "the Inbox with it on screen"),
                                 "friction", {"id": m["id"], "seen": False},
                                 row_age(m["ts"], now)))
    if box.seen:
        friction_rows.append(Row(FRICTION_FOLD, _t((f"{fold_labels(box)['friction']} ▸", "bright_black")),
                                 lambda n=len(box.seen): Text(f"{n} older friction reports you have seen, newest "
                                                              "first: enter or space shows or hides them\n",
                                                              style="bright_black"),
                                 "fold", {"n": len(box.seen)}))
        for m in box.seen:
            friction_rows.append(Row(f"friction:{m['id']}", _t(("✱ ", "bright_black"),
                                                              (f"#{m['id']} {m['from']}: {_line(m['body'])}",
                                                               "bright_black")),
                                     lambda m=m: thread(m, _msg_block(m), "seen already"), "friction",
                                     {"id": m["id"], "seen": True, "folded": True, "under": FRICTION_FOLD},
                                     row_age(m["ts"], now)))
    inbox_rows = []
    for heading, rows in zip(INBOX_HEADINGS, (needs, new_rows, friction_rows)):
        if rows:
            inbox_rows.append(Row(f"heading:{heading}", Text(heading, style="bold"), lambda: Text(""), "heading"))
            inbox_rows += rows
    done_upto = box.upto

    # Flow (card #130, in place of the Log): every message read, oldest first; the pane filters,
    # lays out and draws only the rows in view
    from .. import operators

    roster = [(a.name, a.role, a.active) for a in ctx.team.agents() if a.kind != HUMAN]
    roster += [(n, "operator", True) for n in operators.names(ctx.paths)]  # its own lane (card #166)
    flow_data = flow.Data(msgs, roster,
                          lambda m: thread(m, _msg_block(m), "Flow is read-only · S: message the liaison"), now)

    # the Team pane's header and harness blocks (card #128)
    from .. import versions

    try:
        vers = versions.current(ctx, live_names=set(live), now=now)
    except Exception:  # never let a version read break the TUI
        vers = None
    running = sum(1 for n in live if ctx.team.agent(n))
    goals_open = sum(1 for i in open_items.values() if i["type"] == "goal")
    needs_n, new_n, _ = box.counts
    header = team_header(ctx, vers, running, goals_open, needs_n, new_n, queued, jobs, msgs, now)
    try:
        windows = turns.allowance_windows(ctx)
    except Exception:  # a bad reading must never take the pane with it
        windows = {}
    harnesses = []
    for n in sorted({r.data["harness"] for r in team_rows} | set(windows)):
        try:
            facts = window_facts(ctx, n, now)
        except Exception:  # only data: a bad file never takes the pane with it
            facts = []
        members = [r.data for r in team_rows if r.data["harness"] == n]
        harnesses.append(Harness(n, windows.get(n, []), cue=any(w is None for _, w, _ in facts),
                                 detail=lambda n=n, facts=facts, members=members:
                                 harness_detail(n, facts, members, spend, now)))

    def header_detail(vers=vers):
        return team_detail(vers, spend, now)
    # Supervisor: what xt watch did, newest first (the `v` pop-up, card #131)
    from ..watch import watch_log

    sup_rows = []
    for n, line in enumerate(reversed(watch_log(ctx, 200))):
        stamp, text = line[:19], line[20:]  # "YYYY-MM-DD HH:MM:SS text"
        style = "red" if text.startswith(("alert", "error")) or "failed" in text else ""
        sup_rows.append(Row(f"sup:{n}:{stamp}", _t((stamp[11:16] + " ", "bright_black"), (text, style)),
                            lambda line=line: Text(line + "\n"), "event", {}))

    return Snapshot(
        {"Inbox": inbox_rows, "Work": work_rows, "Team": team_rows, "Supervisor": sup_rows},
        header,
        spend_text(spend.team_today),
        harnesses,
        done_upto,
        box.title(),
        work_title,
        flow_data,
        header_detail,
    )


# --- the Team pane's header and harness rows (card #151) --------------------------------------------

CLAUDE_SOURCE = "the statusLine snapshot (.xt/state/claude_plan.json), account-wide"
CODEX_SOURCE = "its session logs (.xt/state/allowance.json), account-wide"


def _span(secs: float) -> str:
    """`3 h 10 m`, `12 m`, `under a minute`."""
    m = max(0, int(secs // 60))
    return "under a minute" if m < 1 else f"{m} m" if m < 60 else f"{m // 60} h {m % 60:02d} m"


def _ago(secs: float) -> str:
    return "just now" if secs < 60 else f"{_span(secs)} ago"


def _reset(resets_at, now: dt.datetime) -> str:
    return teampane.reset_text(resets_at, now) or "reset time unknown"


def window_facts(ctx: Ctx, harness: str, now: dt.datetime) -> list[tuple[str, dict | None, str]]:
    """A harness's account windows as (label, reading, text): the reading (used, resets_at, age,
    source) when there is a current one, else None and why not with what to do. Only what xt already
    reads: Claude Code's statusLine snapshot, a harness's rate limits from its session logs."""
    from .. import planusage

    t = now.timestamp()
    if harness == "claude":
        path = planusage.snapshot_path(ctx.paths.root)
        snap = planusage._load(path) if path.exists() else None
        out = []
        for key, label in planusage.WINDOWS:
            if snap is None or key not in snap:
                out.append((label, None, "no reading yet: no Claude agent with the statusLine configured has "
                                         "taken a turn (see the user guide, Memory and recovery)"))
                continue
            w, why = planusage.usable(snap.get(key), t)
            if w is not None:
                out.append((label, {"used": w["used_percentage"], "resets_at": w["resets_at"],
                                    "age": f"read {_ago(t - w["observed_at"])}", "source": CLAUDE_SOURCE}, ""))
            elif why == "window reset, no reading since":
                out.append((label, None, "the window reset and no Claude agent has taken a turn since; the next "
                                         "turn brings a reading"))
            elif why.startswith("unknown (last reading"):
                seen = planusage.window(snap.get(key), observed=True)
                out.append((label, None, f"the last reading is {_span(t - seen['observed_at'])} old and stays "
                                         "stale until a Claude agent takes a turn"))
            else:
                out.append((label, None, "the reading can't be used (malformed or from the future); the next "
                                         "Claude turn replaces it"))
        return out
    try:
        path = ctx.paths.state / "allowance.json"
        rl = json.loads(path.read_text()).get(harness)
        age = _ago(t - path.stat().st_mtime)
    except (OSError, ValueError, AttributeError):
        rl, age = None, ""
    out = []
    for key in ("primary", "secondary"):
        p = rl.get(key) if isinstance(rl, dict) else None
        if isinstance(p, dict) and isinstance(p.get("used_percent"), (int, float)):
            win = p.get("window_minutes")
            label = f"{round(win / 1440)}d" if win and win >= 1440 else f"{round(win / 60)}h" if win else "window"
            out.append((label, {"used": float(p["used_percent"]), "resets_at": p.get("resets_at"),
                                "age": f"recorded {age}", "source": CODEX_SOURCE.replace("its", f"{harness}'s")}, ""))
    if not out and harness == "codex":
        out.append(("window", None, "no reading yet: no Codex session log has reported its rate limits; the "
                                    "next Codex turn brings one"))
    return out


def harness_detail(name: str, facts: list, members: list[dict], spend, now: dt.datetime) -> Text:
    """Detail for a harness line (card #151): each window with its reading or why there is none,
    then the harness's agents with model and today's tokens."""
    from .. import turns

    out = Text()
    out.append(f"{name.upper()} · account windows\n", style="bold")
    for label, w, why in facts:
        if w is None:
            out.append(f"{label:<4}", style="bold")
            out.append(f"no current reading: {why}\n", style="yellow")
            continue
        out.append(f"{label:<4}", style="bold")
        out.append(f"{w['used']:.0f}% used · {_reset(w['resets_at'], now)} · {w['age']}")
        out.append(f" · from {w['source']}\n", style="bright_black")
    if not facts:
        out.append(f"xt reads no account windows for {name}\n", style="bright_black")
    out.append_text(_heading(f"agents on {name} ({len(members)}), today's usage"))
    width = max((len(a["name"]) for a in members), default=4)
    model = max((len(a["model"]) for a in members), default=7)
    for a in members:
        mine = spend.agents_today.get(a["name"])
        out.append(f"{a['name']:<{width}}  ", style="bold" if a.get("running") else "")
        out.append(f"{a['model']:<{model}}  ", style="bright_black")
        out.append(f"{turns.fmt(mine) if mine else 'no usage recorded'}\n")
    if not members:
        out.append("(none)\n", style="bright_black")
    return out


def team_detail(vers, spend, now: dt.datetime) -> Text:
    """Detail for the Team header (card #151): "xt and the team": the versions and what `xt status`
    notes about them, the published version's note, and today's usage split by agent."""
    from .. import turns

    out = Text()
    out.append("xt and the team\n", style="bold")
    if vers is None:
        out.append("versions: couldn't be read\n", style="yellow")
    else:
        head, *notes = vers.line().split("\n")
        out.append(head.removeprefix("xt versions: ") + "\n")
        for n in notes:
            out.append(n.strip() + "\n", style="yellow")
        out.append("check the published version now: xt version check\n", style="bright_black")
        out.append_text(_heading("running"))
        out.append(vers.detail() + "\n")
    out.append_text(_heading("usage today"))
    out.append(f"team: {turns.fmt(spend.team_today)}\n")
    for name, t in sorted(spend.agents_today.items(), key=lambda kv: -kv[1].tokens):
        out.append(f"  {name}: {turns.fmt(t)}\n")
    return out


def _work(ctx: Ctx, msgs: list[dict], open_items: dict, live: dict, now, thread) -> tuple[list[Row], str]:
    """The Work outline's rows (card #129), every one of them: the pane folds and filters. Open goals
    with their tasks, then the liaison's drafts, then the `done (N)` fold with the done goals, then
    `no goal` with the tasks that reach no goal. Also the pane's title, `N open · M done`."""
    from . import work

    out = work.outline(msgs, open_items, {n for n, a in live.items() if a.status == "blocked"})
    goals = out.open + out.done
    ow = min(12, max((len(m["to"]) for m in [g.msg for g in goals] + [t.msg for g in goals for t in g.tasks]
                      + [t.msg for g in goals for t in g.follow_ups] + [t.msg for t in out.orphans]), default=4))
    count = lambda tasks: f"{sum(1 for t in tasks if t.state != work.OPEN)}/{len(tasks)}"
    cw = max((len(count(g.tasks)) for g in goals), default=3)
    if out.orphans:
        cw = max(cw, len(count(out.orphans)))

    def tail(owner: str, tasks, is_open: bool) -> dict:
        """The goal row's right-hand columns: owner and `done/total`, and the count alone for a
        narrow pane."""
        n = _t("  ", (count(tasks).rjust(cw), "yellow" if is_open else "green"), "  " if is_open else (" ✓", "green"))
        return {"tail": _t("  ", (owner[:ow].ljust(ow), "bright_black"), n), "count": n}

    def task_rows(tasks, parent: str) -> list[Row]:
        rows = []
        for t in reversed(tasks):  # newest on top (card #162)
            m, is_open = t.msg, t.msg["id"] in open_items

            def detail(m=m, t=t, is_open=is_open):
                o = Text()
                o.append(f"#{m['id']} task · {m['from']} → {m['to']} · opened {_age(m['ts'], now)} ago · ",
                         style="bright_black")
                o.append("open\n" if is_open else "done\n", style="yellow" if is_open else "green")
                if t.state == work.FAILED:
                    o.append(f"{m['to']} is blocked\n" if is_open else "closed as failed or blocked\n", style="red")
                o.append(m["body"].rstrip() + "\n")
                return thread(m, o, "space: fold its goal · o: open work only · S: message the liaison")

            rows.append(Row(f"task:{m['id']}", _t((t.state + " ", work.GLYPH_STYLE[t.state]),
                                                  (f"#{m['id']} ", "bright_black"), m["to"][:ow].ljust(ow) + "  ",
                                                  _line(m["body"])),
                            detail, "task", {"id": m["id"], "level": 2, "parent": parent, "open": is_open},
                            row_age(m["ts"], now)))
        return rows

    def goal_rows(g, parent: str | None) -> list[Row]:
        m = g.msg

        def detail(g=g, m=m):
            o = Text()
            o.append(f"#{m['id']} goal · {m['from']} → {m['to']} · opened {_age(m['ts'], now)} ago · ",
                     style="bright_black")
            o.append("open" if g.open else "done", style="yellow" if g.open else "green")
            o.append(f" · tasks {count(g.tasks)} done\n", style="bright_black")
            o.append(_first_line(m["body"], 200) + "\n", style="bold")
            brief = re.search(r"Brief:\s*(\S+\.md)", m["body"])
            more = None
            if brief:  # below the keys: the reference text, read by scrolling Detail
                more = _heading(f"brief: {brief.group(1)}")
                more.append_text(_file_text(ctx, brief.group(1)))
            return thread(m, o, "space: fold · o: open work only · S: message the liaison", more)

        key = f"goal:{m['id']}"
        follow_open = any(t.msg["id"] in open_items for t in g.follow_ups)  # card #185
        row = Row(key, _t((f"#{m['id']} ", "bright_black"), _line(m["body"])), detail, "goal",
                  {"id": m["id"], "level": 1, "foldable": True, "expanded": g.open or follow_open,
                   "parent": parent, "open": g.open or follow_open, **tail(m["to"], g.tasks, g.open)},
                  row_age(g.newest, now))
        return [row] + task_rows(g.tasks, key) + follow_up_rows(g, key)

    def follow_up_rows(g, parent: str) -> list[Row]:
        """Card #185: tasks the lead opened after the goal closed, below its own tasks, newest on top,
        labelled `↳ follow-up` (`↳ f/u` where the row is short of room)."""
        rows = []
        for t in reversed(g.follow_ups):
            m, is_open = t.msg, t.msg["id"] in open_items

            def detail(m=m, is_open=is_open):
                o = Text()
                o.append(f"#{m['id']} task · follow-up to closed goal #{g.msg['id']} · {m['from']} → {m['to']} · "
                         f"opened {_age(m['ts'], now)} ago · ", style="bright_black")
                o.append("open\n" if is_open else "done\n", style="yellow" if is_open else "green")
                o.append(m["body"].rstrip() + "\n")
                return thread(m, o, "space: fold its goal · o: open work only · S: message the liaison")

            def text(label: str, m=m, t=t) -> Text:
                return _t((t.state + " ", work.GLYPH_STYLE[t.state]), (f"↳ {label} ", "cyan"),
                          (f"#{m['id']} ", "bright_black"), m["to"][:ow].ljust(ow) + "  ", _line(m["body"]))

            rows.append(Row(f"task:{m['id']}", text("follow-up"), detail, "task",
                            {"id": m["id"], "level": 2, "parent": parent, "open": is_open,
                             "short": text("f/u")}, row_age(m["ts"], now)))
        return rows

    rows = [r for g in out.open for r in goal_rows(g, None)]
    drafts = sorted(ctx.paths.drafts.glob("*.md")) if ctx.paths.drafts.exists() else []
    for d in drafts:  # the liaison is still shaping these with the human
        rel = str(d.relative_to(ctx.paths.root))

        def ddetail(rel=rel):
            o = Text()
            o.append(f"draft · {rel} · not dispatched yet (the liaison shapes it with you)\n", style="bright_black")
            o.append_text(_file_text(ctx, rel))
            return o

        rows.append(Row(f"draft:{d.stem}", _t(("✎ ", "cyan"), d.stem, ("  draft", "cyan")), ddetail, "draft",
                        {"path": rel, "level": 1, "open": True}))
    if out.done:
        n = len(out.done)
        follow = sum(1 for g in out.done for t in g.follow_ups if t.msg["id"] in open_items)  # card #185
        rows.append(Row(work.DONE_FOLD, _t((f"done ({n})", "bright_black"),
                                           (f" · {follow} follow-up{'s' if follow != 1 else ''} open", "cyan")
                                           if follow else ""),
                        lambda: Text(f"{n} done goals, newest first: space shows or hides them\n",
                                     style="bright_black"),
                        "donefold", {"level": 1, "foldable": True, "expanded": bool(follow), "open": bool(follow)}))
        rows += [r for g in out.done for r in goal_rows(g, work.DONE_FOLD)]
    if out.orphans:
        orphans = out.orphans
        has_open = any(t.msg["id"] in open_items for t in orphans)
        rows.append(Row(work.NO_GOAL, _t(("no goal", "bold")),
                        lambda: Text("Tasks whose ref chain reaches no goal: no ref, a ref to a message that "
                                     f"isn't under a goal, or one older than the {HISTORY_DAYS} days the TUI "
                                     "reads.\n", style="bright_black"),
                        "nogoal", {"level": 1, "foldable": True, "expanded": has_open, "open": has_open,
                                   **tail("", orphans, has_open)},
                        row_age(max(t.msg["ts"] for t in orphans), now)))
        rows += task_rows(orphans, work.NO_GOAL)
    return rows, f"{len(out.open)} open · {len(out.done)} done"


STUCK_AFTER = 60  # seconds: queued messages and jobs are normally handled within seconds


def version_text(vers) -> Text:
    """`xt 0.16.0 (latest)`, with a newer published release or a restart still needed in yellow."""
    from .. import __version__
    from ..versions import display, parse

    if vers is None:
        return Text(f"xt {display(__version__)}")
    out = Text(f"xt {display(vers.installed)}")
    if vers.pending:  # never an older published version than the installed final (card #133)
        out.append(" (published ≥ installed, check pending)", style="bright_black")
    elif not vers.published:
        out.append(" (published ?)", style="bright_black")
    elif vers.upgrade_available:
        out.append(f" ({display(vers.published)} published)", style="yellow")
    elif parse(vers.published) == parse(vers.installed):
        out.append(" (latest)", style="bright_black")
    else:
        out.append(f" (published {display(vers.published)})", style="bright_black")
    if vers.restart_needed:
        out.append(f" · running {vers.running_label}: restart to update", style="yellow")
    elif vers.running_label not in (display(vers.installed), "nothing running"):
        out.append(f" · running {vers.running_label}", style="bright_black")
    return out


def team_header(ctx, vers, running: int, goals_open: int, needs: int, new: int,
                queued: list, jobs: list, msgs: list, now) -> Text:
    """The Team pane's header (card #128): the team and xt's version, what's running, open goals,
    and what needs the human and what's new (the Inbox title's first two counts). What needs the
    human stands out; routine zeros aren't shown."""
    out = Text(no_wrap=True, overflow="ellipsis")
    out.append(ctx.team.name, style="bold")
    out.append(" · ")
    out.append_text(version_text(vers))
    out.append(f" · {running} running")
    if goals_open:
        out.append(f" · {goals_open} goal{'s' if goals_open != 1 else ''} open")
    if needs:
        out.append(" · ")
        out.append(f"⚑ {needs} needs you", style="bold yellow")
    if new:
        out.append(" · ")
        out.append(f"✉ {new} new", style="cyan")
    if not needs and not new:
        out.append(" · nothing waiting for you", style="green")
    plural = lambda n, w: f"{n} {w}{'s' if n != 1 else ''}"
    ts = {m["id"]: m["ts"] for m in msgs}
    stuck_q = sum(1 for i in queued
                  if i["id"] in ts and (now - dt.datetime.fromisoformat(ts[i["id"]])).total_seconds() > STUCK_AFTER)
    stuck_j = sum(1 for j in jobs if j.get("added") and now.timestamp() - j["added"] > STUCK_AFTER)
    if stuck_q:
        out.append(f" · {stuck_q} queued over a minute", style="yellow")
    if stuck_j:
        out.append(f" · {plural(stuck_j, 'job')} waiting over a minute", style="yellow")
    from .. import operators

    for line in operators.active_grants(ctx):  # card #166
        out.append(f" · {line}", style="bold magenta")
    return out


def spend_text(team_today) -> str:
    """The header's right side: today's tokens and the estimate, with any unpriced part."""
    from .. import usage

    if not team_today.turns:
        return "today: no usage recorded yet"
    money = ("est. unavailable" if team_today.unpriced_tokens == team_today.tokens
             else f"est. ${team_today.usd:,.2f}")
    unpriced = (f" (+{usage.short(team_today.unpriced_tokens)} unpriced)"
                if team_today.unpriced_tokens and team_today.unpriced_tokens != team_today.tokens else "")
    return f"today {usage.short(team_today.tokens)} tokens · {money}{unpriced}"

