"""What the TUI shows: the team's files and Herdr's live state, turned into panel rows.

Each row's detail is a function, so expensive parts (reading a pane, a role file) run only for
the row the human is looking at.
"""

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Callable

from rich.text import Text

from ..alerts import Alerts
from ..context import Ctx
from ..dispatch import Queue
from ..jobs import Jobs
from ..paths import XtError
from ..spawn import Approvals
from ..team import HUMAN, schedule_text

PANELS = ("Goals", "Team", "Tasks", "Inbox", "Log", "Supervisor")
STATUS_STYLE = {"idle": "green", "done": "green", "working": "yellow", "blocked": "red"}
TYPE_STYLE = {"goal": "magenta", "task": "magenta", "done": "green", "report": "cyan", "ask": "cyan",
              "alert": "red", "approval": "yellow", "nudge": "yellow", "note": "bright_black",
              "system": "bright_black"}
HISTORY_DAYS = 30


@dataclass
class Row:
    key: str
    text: Text
    detail: Callable[[], Text]
    kind: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class Snapshot:
    panels: dict[str, list[Row]]
    summary: str


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
    approvals = Approvals(ctx).pending()
    alerts = Alerts(ctx).active()
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

        goal_rows.append(Row(f"goal:{g['id']}", _t((f"#{g['id']} ", "bright_black"), _first_line(g["body"], 60),
                                                    mark), detail, "goal", {"id": g["id"]}))

    # Team: roster with live state
    team_rows = []
    for a in ctx.team.agents():
        if a.kind == HUMAN:
            continue
        la = live.get(a.name)
        state = la.status if la else ("retired" if not a.active else "not running")
        dot = ("●", STATUS_STYLE.get(state, "bright_black")) if la else ("○", "bright_black")
        owned = [i for i in open_items.values() if i["owner"] == a.name]

        def detail(a=a, la=la, state=state, owned=owned):
            out = Text()
            out.append(f"{a.name}", style="bold")
            wakes = f" · woken {schedule_text(a)}" if a.wake_every else ""
            out.append(f" · {a.role} · {a.harness}{'/' + a.model if a.model else ''} · reports to {a.reports_to}{wakes} · ")
            out.append(state + "\n", style=STATUS_STYLE.get(state, "bright_black"))
            if la:
                out.append(f"workspace {la.workspace_id} · pane {la.pane_id}  (f: jump there)\n", style="bright_black")
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
                    tail = [ln for ln in screen.splitlines() if ln.strip()][-25:]
                    out.append("\n".join(tail) + "\n", style="bright_black")
                except XtError:
                    out.append("(couldn't read the pane)\n", style="bright_black")
            return out

        team_rows.append(Row(f"agent:{a.name}", _t(dot, f" {a.name:<11} ", (f"{a.harness or '':<7}", "bright_black"),
                                                   (f"{state}", STATUS_STYLE.get(state, "bright_black"))),
                             detail, "agent", {"name": a.name, "workspace": la.workspace_id if la else None,
                                               "running": la is not None, "active": a.active, "role": a.role}))

    # Tasks: open first, then the last few closed
    tasks = [m for m in msgs if m["type"] == "task"]
    open_tasks = [t for t in tasks if t["id"] in open_items]
    closed_tasks = [t for t in tasks if t["id"] not in open_items][-10:]
    task_rows = []
    for t in open_tasks + list(reversed(closed_tasks)):
        is_open = t["id"] in open_items
        age = _age(t["ts"], now)

        def detail(t=t, is_open=is_open):
            out = Text()
            out.append(f"#{t['id']} task · {t['from']} → {t['to']} · ", style="bright_black")
            out.append("open\n" if is_open else "done\n", style="yellow" if is_open else "green")
            out.append(_heading("thread"))
            for m in thread(t["id"]):
                out.append_text(_msg_block(m))
            return out

        task_rows.append(Row(f"task:{t['id']}", _t((f"#{t['id']} ", "bright_black"), f"{t['to']:<10} ",
                                                   _first_line(t["body"], 40),
                                                   (f"  {age}", "yellow") if is_open else ("  ✓", "green")),
                             detail, "task", {"id": t["id"]}))

    # Inbox: what needs the human; questions first, they're the only thing only the human can answer
    inbox_rows = []
    questions = [i for i in open_items.values() if i["type"] == "ask"]
    for q in questions:
        def qdetail(q=q):
            out = Text()
            out.append(f"Question #{q['id']} from {q['opener']} · waiting {_age(q['opened'], now)}\n", style="bold yellow")
            m = next((m for m in msgs if m["id"] == q["id"]), None)
            out.append((m["body"] if m else q["title"]) + "\n")
            out.append(f"\ns: answer (goes to {q['opener']}) · or answer in {q['opener']}'s pane\n", style="bright_black")
            if q.get("about") is not None:
                about = next((m for m in msgs if m["id"] == q["about"]), None)
                if about:
                    out.append(_heading(f"about #{q['about']}"))
                    out.append_text(_msg_block(about))
            return out

        inbox_rows.append(Row(f"question:{q['id']}", _t(("? ", "bold yellow"), f"#{q['id']} {q['opener']}: ",
                                                        _first_line(q["title"], 44),
                                                        (f"  {_age(q['opened'], now)}", "yellow")),
                              qdetail, "question", {"id": q["id"], "opener": q["opener"]}))
    for rid, r in sorted(approvals.items(), key=lambda kv: int(kv[0])):
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

            inbox_rows.append(Row(f"approval:{rid}", _t(("? ", "yellow"), f"#{rid} wake {r['name']} ",
                                                        (f"every {r['every']}", "bright_black")),
                                  sdetail, "approval", {"id": int(rid)}))
            continue

        def detail(rid=rid, r=r):
            out = Text()
            out.append(f"Approval #{rid}: {r['requester']} asks to spawn ", style="bold")
            out.append(f"{r['name']}", style="bold yellow")
            out.append(f"\nrole {r['role']} · harness {r['harness']}{'/' + r['model'] if r.get('model') else ''}"
                       f" · reports to {r['reports_to']}\n")
            out.append("a approve · d deny\n", style="bright_black")
            out.append(_heading(f"role brief: roles/{r['role']}.md"))
            out.append_text(_file_text(ctx, f"roles/{r['role']}.md"))
            return out

        inbox_rows.append(Row(f"approval:{rid}", _t(("? ", "yellow"), f"#{rid} spawn {r['name']} ",
                                                    (f"({r['role']}, {r['harness']})", "bright_black")),
                              detail, "approval", {"id": int(rid)}))
    for key, al in sorted(alerts.items(), key=lambda kv: kv[1].get("id", 0)):
        def detail(key=key, al=al):
            out = Text()
            out.append(f"Alert #{al.get('id')} · {al.get('ts', '')[:16]}\n", style="bold red")
            out.append(al["text"] + "\n")
            out.append(f"\n({key}) c: clear once dealt with\n", style="bright_black")
            return out

        inbox_rows.append(Row(f"alert:{key}", _t(("⚠ ", "red"), _first_line(al["text"], 60)), detail, "alert",
                              {"key": key}))
    to_human = [m for m in msgs if m["to"] == HUMAN and m["type"] not in ("system", "alert", "approval")
                and m["id"] not in open_items][-10:]
    for m in reversed(to_human):
        inbox_rows.append(Row(f"msg:{m['id']}", _t(("✉ ", "cyan"), f"#{m['id']} {m['from']}: ",
                                                   _first_line(m["body"], 50)),
                              lambda m=m: _msg_block(m), "message", {"id": m["id"]}))

    # Log: newest first
    log_rows = []
    for m in reversed(msgs[-60:]):
        log_rows.append(Row(f"log:{m['id']}", _t(_msg_line(m), ("  " + _first_line(m["body"], 40), "bright_black")),
                            lambda m=m: _msg_block(m), "message", {"id": m["id"]}))

    running = sum(1 for n in live if ctx.team.agent(n))
    summary = (f"{ctx.team.name} · {running} running · {len(open_items) - len(questions)} open · "
               f"{len(questions)} question{'s' if len(questions) != 1 else ''} · "
               f"{len(approvals)} approval{'s' if len(approvals) != 1 else ''} · {len(alerts)} alert"
               f"{'s' if len(alerts) != 1 else ''} · {len(queued)} queued · {len(jobs)} jobs")
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
        summary,
    )
