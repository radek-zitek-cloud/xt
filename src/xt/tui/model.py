"""What the TUI shows: the team's files and Herdr's live state, turned into panel rows.

Each row's detail is a function, so expensive parts (reading a pane, a role file) run only for
the row the human is looking at.
"""

import datetime as dt
import re
import textwrap
from dataclasses import dataclass, field
from typing import Callable

from rich.text import Text

from .. import permissions
from ..adapters import load_adapters
from ..context import Ctx
from ..dispatch import Queue
from ..jobs import Jobs
from ..paths import XtError
from ..team import HUMAN, harness_model, schedule_text
from . import teampane
from .teampane import Harness, shown_model

PANELS = ("Goals", "Tasks", "Inbox", "Log", "Supervisor")  # the numbered list panels, 1-5; Team has no number
STATUS_STYLE = {"idle": "green", "done": "green", "working": "yellow", "blocked": "red"}
TYPE_STYLE = {"goal": "magenta", "task": "magenta", "done": "green", "report": "cyan", "ask": "cyan",
              "alert": "red", "approval": "yellow", "nudge": "yellow", "note": "bright_black",
              "system": "bright_black"}
HISTORY_DAYS = 30
CONTINUED = "↳ "


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
    panels: dict[str, list[Row]]  # the list panels, and "Team": the agents the Team pane shows
    header: Text  # the Team pane's first line: team, xt version, what's running, what needs the human
    spend: str = ""  # on its right: today's tokens and estimated cost
    harnesses: list[Harness] = field(default_factory=list)  # the Team pane's blocks and their windows
    done_upto: int = 0  # the Inbox's done goals are seen up to here once the human has looked (#125)
    inbox_title: str = ""  # the Inbox's counts, `⚑ 1 · ✉ 2 · ✱ 1` (card #127)


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


def _msg_line(m: dict) -> Text:
    ref = f" ref:#{m['ref']}" if m.get("ref") is not None else ""
    return _t((f"#{m['id']} ", "bright_black"), (f"{m['type']} ", TYPE_STYLE.get(m["type"], "")),
              f"{m['from']}→{m['to']}{ref}")


def _msg_block(m: dict) -> Text:
    ref = f" ref:#{m['ref']}" if m.get("ref") is not None else ""
    out = Text()
    out.append(f"#{m['id']} {m['ts'][:16].replace('T', ' ')} ", style="bright_black")
    out.append(m["type"], style=TYPE_STYLE.get(m["type"], "bold"))
    out.append(f"  {m['from']} → {m['to']}{ref}\n")
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

    def thread(item_id: int) -> list[dict]:
        return [m for m in msgs if m["id"] == item_id or m.get("ref") == item_id]

    # Goals: drafts the liaison is still shaping, then open goals, then recently closed
    goal_rows = []
    drafts = sorted(ctx.paths.drafts.glob("*.md")) if ctx.paths.drafts.exists() else []
    for d in drafts:
        rel = str(d.relative_to(ctx.paths.root))

        def ddetail(rel=rel):
            out = Text()
            out.append(f"draft · {rel} · not dispatched yet (the liaison shapes it with you)\n", style="bright_black")
            out.append_text(_file_text(ctx, rel))
            return out

        goal_rows.append(Row(f"draft:{d.stem}", _t(("✎ ", "cyan"), d.stem, ("  draft", "cyan")), ddetail, "draft",
                             {"path": rel}))
    goals = [m for m in msgs if m["type"] == "goal"]
    goals.sort(key=lambda g: (g["id"] not in open_items, -g["id"]))
    for g in goals:
        tasks = [m for m in msgs if m["type"] == "task" and m.get("ref") == g["id"]]
        done_tasks = sum(1 for t in tasks if t["id"] not in open_items)
        is_open = g["id"] in open_items
        mark = (f"  {done_tasks}/{len(tasks)}", "yellow") if is_open else ("  ✓", "green")

        def detail(g=g, tasks=tasks, is_open=is_open):
            out = Text()
            out.append(f"#{g['id']} goal · {g['from']} → {g['to']} · opened {_age(g['ts'], now)} ago · ",
                       style="bright_black")
            out.append("open\n" if is_open else "done\n", style="yellow" if is_open else "green")
            out.append(_first_line(g["body"], 200) + "\n", style="bold")
            from .. import turns as _turns

            out.append(f"usage: {_turns.fmt(_turns.goal_totals(ctx, g['id'], g['ts']))}\n")
            brief = re.search(r"Brief:\s*(\S+\.md)", g["body"])
            out.append(_heading("tasks"))
            for t in tasks:
                st = "open" if t["id"] in open_items else "done"
                out.append(f"#{t['id']} {st:<4} {t['to']:<11} {_first_line(t['body'], 90)}\n",
                           style="yellow" if st == "open" else "")
            if not tasks:
                out.append("(none yet)\n", style="bright_black")
            if brief:
                out.append(_heading(f"brief: {brief.group(1)}"))
                out.append_text(_file_text(ctx, brief.group(1)))
            return out

        ids = {g["id"], *(t["id"] for t in tasks)}
        newest = max((m["ts"] for m in msgs if m["id"] in ids or m.get("ref") in ids), default=g["ts"])
        goal_rows.append(Row(f"goal:{g['id']}", _t((f"#{g['id']} ", "bright_black"), _line(g["body"]), mark),
                             detail, "goal", {"id": g["id"]}, row_age(newest, now)))

    # Team: roster with live state and context
    from .. import turns, usage

    spend = turns.today(ctx)
    contexts = usage.readings(ctx, [a.name for a in ctx.team.agents() if a.kind != HUMAN and a.active])
    team_rows = []
    for a in ctx.team.agents():
        if a.kind == HUMAN:
            continue
        la = live.get(a.name)
        state = la.status if la else ("retired" if not a.active else "not running")
        dot = ("●", STATUS_STYLE.get(state, "bright_black")) if la else ("○", "bright_black")
        owned = [i for i in open_items.values() if i["owner"] == a.name]

        ctxr = contexts.get(a.name)

        def detail(a=a, la=la, state=state, owned=owned, ctxr=ctxr):
            out = Text()
            out.append(f"{a.name}", style="bold")
            wakes = f" · woken {schedule_text(a)}" if a.wake_every else ""
            out.append(f" · {a.role} · {harness_model(a.harness, a.model)} · reports to {a.reports_to}{wakes} · ")
            out.append(state + "\n", style=STATUS_STYLE.get(state, "bright_black"))
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
            if a.connectors:
                out.append(f"account connectors (opted in): {', '.join(a.connectors)}\n", style="yellow")
            settings_path = permissions.shown(ctx.team, a, load_adapters(ctx.paths).get(a.harness))
            if settings_path:
                out.append(f"settings file: {settings_path}\n")
            if la:
                from ..reset import suggestion

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
                "dot": dot[0], "dot_style": dot[1],
                "used": now_ctx.used if now_ctx else None, "window": now_ctx.window if now_ctx else None,
                "approximate": now_ctx.approximate if now_ctx else False}
        team_rows.append(Row(f"agent:{a.name}", teampane.cell(data, teampane.widths([data]), teampane.BAR_MAX),
                             detail, "agent", data))

    # Tasks: open first, then the last few closed
    tasks = [m for m in msgs if m["type"] == "task"]
    open_tasks = [t for t in tasks if t["id"] in open_items]
    closed_tasks = [t for t in tasks if t["id"] not in open_items][-10:]
    task_rows = []
    for t in open_tasks + list(reversed(closed_tasks)):
        is_open = t["id"] in open_items

        def detail(t=t, is_open=is_open):
            out = Text()
            out.append(f"#{t['id']} task · {t['from']} → {t['to']} · ", style="bright_black")
            out.append("open\n" if is_open else "done\n", style="yellow" if is_open else "green")
            out.append(_heading("thread"))
            for m in thread(t["id"]):
                out.append_text(_msg_block(m))
            return out

        task_rows.append(Row(f"task:{t['id']}", _t((f"#{t['id']} ", "bright_black"), f"{t['to']:<10} ",
                                                   _line(t["body"]),
                                                   ("  open", "yellow") if is_open else ("  ✓", "green")),
                             detail, "task", {"id": t["id"]}, row_age(t["ts"], now)))

    # Inbox: three groups, Needs you / New / Friction, empty groups hidden (card #127)
    from .. import inbox as _inbox
    from ..choices import options_of
    from ..goaldone import first_line

    box = _inbox.build(ctx, msgs, list(open_items.values()))
    by_id = {m["id"]: m for m in msgs}
    needs, new_rows, friction_rows = [], [], []
    for q in box.questions:
        def qdetail(q=q):
            out = Text()
            out.append(f"Question #{q['id']} from {q['opener']} · waiting {_age(q['opened'], now)}\n", style="bold yellow")
            m = by_id.get(q["id"])
            out.append((m["body"] if m else q["title"]) + "\n")
            out.append(f"\ns: answer (goes to {q['opener']}) · or answer in {q['opener']}'s pane\n", style="bright_black")
            if q.get("about") is not None:
                about = by_id.get(q["about"])
                if about:
                    out.append(_heading(f"about #{q['about']}"))
                    out.append_text(_msg_block(about))
            return out

        body = by_id[q["id"]]["body"] if q["id"] in by_id else q["title"]
        n_opts = len(options_of(body))
        needs.append(Row(f"question:{q['id']}", _t(("⚑ ", "bold yellow"), f"#{q['id']} {q['opener']}: ",
                                                   _line(q["title"]),
                                                   (f"  {n_opts} options", "yellow") if n_opts else ""),
                         qdetail, "question", {"id": q["id"], "opener": q["opener"], "text": body},
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
                out.append("each wake-up is a billed agent turn · a approve · d deny\n", style="bright_black")
                agent = ctx.team.agent(r["name"])
                if agent and agent.role:
                    out.append(_heading(f"its role: roles/{agent.role}.md"))
                    out.append_text(_file_text(ctx, f"roles/{agent.role}.md"))
                return out

            needs.append(Row(f"approval:{rid}", _t(("⚑ ", "yellow"), f"#{rid} wake {r['name']} ",
                                                   (f"every {r['every']}", "bright_black")),
                             sdetail, "approval", {"id": int(rid)}, row_age(ts, now)))
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
            out.append("a approve · d deny\n", style="bright_black")
            out.append(_heading(f"role brief: roles/{r['role']}.md"))
            out.append_text(_file_text(ctx, f"roles/{r['role']}.md"))
            return out

        needs.append(Row(f"approval:{rid}", _t(("⚑ ", "yellow"), f"#{rid} spawn {r['name']} ",
                                               (f"({r['role']}, {harness_model(r['harness'], r.get('model'))})",
                                                "bright_black")),
                         detail, "approval", {"id": int(rid)}, row_age(ts, now)))
    for key, al in box.alerts:
        def detail(key=key, al=al):
            out = Text()
            out.append(f"Alert #{al.get('id')} · {al.get('ts', '')[:16]}\n", style="bold red")
            out.append(al["text"] + "\n")
            out.append(f"\n({key}) c: clear once dealt with\n", style="bright_black")
            return out

        needs.append(Row(f"alert:{key}", _t(("⚠ ", "red"), _line(al["text"])), detail, "alert", {"key": key},
                         row_age(al.get("ts"), now)))
    for m, goal in box.new:  # since the human last looked (cards #125, #127)
        if goal is None:
            new_rows.append(Row(f"msg:{m['id']}", _t(("✉ ", "cyan"), f"#{m['id']} {m['from']}: ", _line(m["body"])),
                                lambda m=m: _msg_block(m), "message", {"id": m["id"]}, row_age(m["ts"], now)))
            continue

        def ddetail(goal=goal, done=m):
            out = Text()
            out.append(f"Goal #{goal['id']} done · {done['ts'][:16].replace('T', ' ')} by {done['from']}\n",
                       style="bold green")
            out.append(first_line(goal["body"], 200) + "\n", style="bold")
            out.append(_heading(f"closing summary: #{done['id']}"))
            out.append(done["body"] + "\n")
            out.append(f"\nthe whole thread: xt log --id {goal['id']} · clears from the Inbox once you "
                       "leave it\n", style="bright_black")
            return out

        new_rows.append(Row(f"done:{goal['id']}", _t(("✓ ", "green"), f"#{goal['id']} done: ", _line(goal["body"]),
                                                     (f"  #{m['id']}", "bright_black")),
                            ddetail, "done", {"id": goal["id"], "done": m["id"]}, row_age(m["ts"], now)))
    for m in box.unread:
        friction_rows.append(Row(f"friction:{m['id']}", _t(("✱ ", "magenta"), f"#{m['id']} {m['from']}: ",
                                                          _line(m["body"])),
                                 lambda m=m: _msg_block(m), "friction", {"id": m["id"], "seen": False},
                                 row_age(m["ts"], now)))
    if box.seen:
        friction_rows.append(Row("fold:friction", _t((f"({len(box.seen)} older, seen) ▸", "bright_black")),
                                 lambda n=len(box.seen): Text(f"{n} older friction reports you have seen, newest "
                                                              "first: enter shows or hides them\n",
                                                              style="bright_black"),
                                 "fold", {"n": len(box.seen)}))
        for m in box.seen:
            friction_rows.append(Row(f"friction:{m['id']}", _t(("✱ ", "bright_black"),
                                                              (f"#{m['id']} {m['from']}: {_line(m['body'])}",
                                                               "bright_black")),
                                     lambda m=m: _msg_block(m), "friction",
                                     {"id": m["id"], "seen": True, "folded": True}, row_age(m["ts"], now)))
    inbox_rows = []
    for heading, rows in (("NEEDS YOU", needs), ("NEW", new_rows), ("FRICTION", friction_rows)):
        if rows:
            inbox_rows.append(Row(f"heading:{heading}", Text(heading, style="bold"), lambda: Text(""), "heading"))
            inbox_rows += rows
    done_upto = box.upto

    # Log: newest first
    log_rows = []
    for m in reversed(msgs[-60:]):
        log_rows.append(Row(f"log:{m['id']}", _t(_msg_line(m), ("  " + _line(m["body"]), "bright_black")),
                            lambda m=m: _msg_block(m), "message", {"id": m["id"]}, row_age(m["ts"], now)))

    # the Team pane's header and harness blocks (card #128)
    from .. import versions

    try:
        vers = versions.current(ctx, live_names=set(live))
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
    harnesses = [Harness(n, windows.get(n, [])) for n in sorted({r.data["harness"] for r in team_rows} | set(windows))]
    # Supervisor: what xt watch did, newest first
    from ..watch import watch_log

    sup_rows = []
    for n, line in enumerate(reversed(watch_log(ctx, 200))):
        stamp, text = line[:19], line[20:]  # "YYYY-MM-DD HH:MM:SS text"
        style = "red" if text.startswith(("alert", "error")) or "failed" in text else ""
        sup_rows.append(Row(f"sup:{n}:{stamp}", _t((stamp[11:16] + " ", "bright_black"), (text, style)),
                            lambda line=line: Text(line + "\n"), "event", {}))

    return Snapshot(
        {"Goals": goal_rows, "Team": team_rows, "Tasks": task_rows, "Inbox": inbox_rows, "Log": log_rows,
         "Supervisor": sup_rows},
        header,
        spend_text(spend.team_today),
        harnesses,
        done_upto,
        box.title(),
    )


STUCK_AFTER = 60  # seconds: queued messages and jobs are normally handled within seconds


def version_text(vers) -> Text:
    """`xt 0.16.0 (latest)`, with a newer published release or a restart still needed in yellow."""
    from .. import __version__
    from ..versions import display, parse

    if vers is None:
        return Text(f"xt {display(__version__)}")
    out = Text(f"xt {display(vers.installed)}")
    if not vers.published:
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

