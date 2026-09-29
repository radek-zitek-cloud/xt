"""Per-turn usage (card #17 / #54): tokens per model call, recorded from each agent's session logs,
attributed to the goal the agent was working on, and priced as an estimate.

The supervisor calls `record(ctx)` about once a minute. For every active agent it reads the new
lines of its session logs (the main session found by `usage.find_session`, plus Codex's
automatic-reviewer sub-sessions, which count as auxiliary), turns each model call into one record,
and appends it to `.xt/usage/YYYY-MM-DD.jsonl` (the local day on which the turn completed). Where
it stopped reading each log is kept in `.xt/state/usage_offsets.json`. Records hold counters only.

Totals (`summary`) add records up per agent, per goal and per day. Estimated USD comes from
public list prices (`prices.toml`) or, for pi, from pi's own per-message cost; a turn with no price
stays unpriced and totals say so, instead of counting it as zero.
"""

import datetime as dt
import glob
import json
import os
import re
import time
import tomllib
from dataclasses import dataclass, field

from .adapters import load_adapters
from .context import Ctx
from .team import HUMAN
from . import usage

READ_LIMIT = 8 * 1024 * 1024  # per log per pass, so a huge backlog is read over a few passes
LOOKBACK_DAYS = 2  # usage: logs of the agent's earlier sessions too (a restart must not drop them)


def local_today() -> dt.date:
    return dt.date.today()


# --- parsing one log incrementally --------------------------------------------------------------


def _new_lines(path: str, offset: int) -> tuple[list[str], int]:
    size = os.path.getsize(path)
    if size < offset:  # the file was replaced: start again
        offset = 0
    with open(path, "rb") as fh:
        fh.seek(offset)
        data = fh.read(READ_LIMIT)
    end = data.rfind(b"\n")
    if end < 0:
        return [], offset
    return data[: end + 1].decode("utf-8", "replace").splitlines(), offset + end + 1


def _codex(lines, st, aux):
    out = []
    for ln in lines:
        if '"turn_context"' in ln:
            try:
                st["model"] = json.loads(ln)["payload"].get("model") or st.get("model")
            except (ValueError, KeyError, AttributeError):
                pass
            continue
        if '"token_count"' not in ln:
            continue
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        p = d.get("payload") or {}
        if p.get("rate_limits") and not aux:
            st["rate_limits"] = {"at": d.get("timestamp"), **p["rate_limits"]}
        info = p.get("info") or {}
        total = (info.get("total_token_usage") or {}).get("total_tokens")
        last = info.get("last_token_usage")
        if not last or total is None or total <= st.get("total", -1):
            continue  # a repeat of the previous count, not a new model call
        st["total"] = total
        inp, cached = int(last.get("input_tokens") or 0), int(last.get("cached_input_tokens") or 0)
        out.append({"ts": d.get("timestamp"), "model": st.get("model"), "input": inp - cached,
                    "cached_input": cached, "cache_write": int(last.get("cache_write_input_tokens") or 0),
                    "output": int(last.get("output_tokens") or 0),
                    "reasoning": int(last.get("reasoning_output_tokens") or 0)})
    return out


def _claude(lines, st, aux):
    out = []
    seen = st.setdefault("seen", [])
    for ln in lines:
        if '"usage"' not in ln:
            continue
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        msg = d.get("message")
        if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
            continue
        mid = msg.get("id") or d.get("uuid")
        if mid in seen:  # one API message is logged once per content block
            continue
        seen.append(mid)
        del seen[:-200]
        u = msg["usage"]
        cc = u.get("cache_creation") or {}
        w1h = int(cc.get("ephemeral_1h_input_tokens") or 0)
        out.append({"ts": d.get("timestamp"), "model": msg.get("model"), "input": int(u.get("input_tokens") or 0),
                    "cache_write": int(u.get("cache_creation_input_tokens") or 0), "cache_write_1h": w1h,
                    "cached_input": int(u.get("cache_read_input_tokens") or 0),
                    "output": int(u.get("output_tokens") or 0),
                    "aux": bool(d.get("isSidechain"))})
    return out


def _pi(lines, st, aux):
    out = []
    for ln in lines:
        if '"usage"' not in ln:
            continue
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        msg = d.get("message") if isinstance(d.get("message"), dict) else d
        u = msg.get("usage")
        if not isinstance(u, dict):
            continue
        cost = (u.get("cost") or {}).get("total")
        out.append({"ts": usage._iso(msg.get("timestamp") or d.get("timestamp")),
                    "model": f"{msg.get('provider', '')}/{msg.get('model', '')}",
                    "input": int(u.get("input") or 0), "cached_input": int(u.get("cacheRead") or 0),
                    "cache_write": int(u.get("cacheWrite") or 0), "output": int(u.get("output") or 0),
                    "harness_usd": float(cost) if cost is not None else None})
    return out


PARSERS = {"codex": _codex, "claude": _claude, "pi": _pi}


# --- which logs belong to an agent ----------------------------------------------------------------


def agent_logs(ctx: Ctx, adapter, name: str, since: float) -> list[tuple[str, bool]]:
    """(path, auxiliary) for every log of this agent modified since `since`: its sessions (the
    current one and earlier ones, e.g. before a restart) and, for Codex, the reviewer sub-sessions
    that carry its first prompt. Read positions keep each log from being counted twice."""
    marker = usage._marker_re(name, ctx.team.name)
    floor = since
    out = []
    for path in glob.glob(os.path.expanduser(adapter.sessions or "")):
        try:
            if os.path.getmtime(path) < floor:
                continue
            head = usage._head(path)
        except OSError:
            continue
        if marker.search(head):
            out.append((path, not usage._is_main_session(adapter.session_format, head)))
    return out


# --- goal attribution -------------------------------------------------------------------------------


def _goal_of(msg: dict, index: dict[int, dict], cache: dict[int, int | None]) -> int | None:
    """The goal a message belongs to: itself, its task's goal, or up its --ref chain."""
    chain, m, hops = [], msg, 0
    goal = None
    while m is not None and hops < 6:
        if m["id"] in cache:
            goal = cache[m["id"]]
            break
        chain.append(m["id"])
        if m["type"] == "goal":
            goal = m["id"]
            break
        if m["type"] == "task" and m.get("ref") is not None:
            goal = m["ref"]
            break
        m, hops = index.get(m.get("ref")) if m.get("ref") is not None else None, hops + 1
    for i in chain:
        cache[i] = goal
    return goal


def goal_timelines(ctx: Ctx) -> dict[str, list[tuple[str, int | None]]]:
    """Per agent, the goal of each message it sent or received, in time order. A turn belongs to
    the goal of the latest such message before it (work in between goals: none)."""
    msgs = list(ctx.ledger.messages(since_days=14))
    index = {m["id"]: m for m in msgs}
    cache: dict[int, int | None] = {}
    out: dict[str, list[tuple[str, int | None]]] = {}
    for m in msgs:
        if m["type"] in ("system", "alert", "approval", "note", "friction"):
            continue
        g = _goal_of(m, index, cache)
        for who in {m["from"], m["to"]}:
            if who != HUMAN:
                out.setdefault(who, []).append((m["ts"], g))
    return out


def _attribute(timeline: list[tuple[str, int | None]], ts: str | None) -> int | None:
    if not ts or not timeline:
        return None
    when = _parse(ts)
    goal = None
    for t, g in timeline:
        if _parse(t) > when:
            break
        goal = g
    return goal


def _parse(ts: str) -> dt.datetime:
    d = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    return d if d.tzinfo else d.astimezone()


# --- prices -------------------------------------------------------------------------------------------


def load_prices(ctx: Ctx) -> dict[str, dict]:
    try:
        return tomllib.loads(ctx.paths.prices.read_text()).get("models", {})
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def estimate(rec: dict, prices: dict[str, dict]) -> float | None:
    """Estimated USD for one turn, or None when there's no public price for its model."""
    if rec.get("harness_usd") is not None:
        return rec["harness_usd"]
    p = prices.get(rec.get("model") or "")
    if not p:
        return None
    per = 1_000_000
    usd = rec.get("input", 0) * p.get("input", 0) / per + rec.get("output", 0) * p.get("output", 0) / per
    if "cached_input" in p:
        usd += rec.get("cached_input", 0) * p["cached_input"] / per
    if "cache_read" in p:
        usd += rec.get("cached_input", 0) * p["cache_read"] / per
    w1h = rec.get("cache_write_1h", 0)
    w5m = rec.get("cache_write", 0) - w1h
    usd += w5m * p.get("cache_write_5m", p.get("input", 0)) / per + w1h * p.get("cache_write_1h", p.get("input", 0)) / per
    return round(usd, 6)


def tokens(rec: dict) -> int:
    return sum(int(rec.get(k) or 0) for k in ("input", "cached_input", "cache_write", "output"))


# --- recording ------------------------------------------------------------------------------------------


def record(ctx: Ctx) -> int:
    """Read new turns from every active agent's session logs; returns how many were recorded."""
    adapters = load_adapters(ctx.paths)
    lookback = time.time() - LOOKBACK_DAYS * 86400
    offsets_path = ctx.paths.state / "usage_offsets.json"
    try:
        offsets = json.loads(offsets_path.read_text()) if offsets_path.exists() else {}
    except ValueError:
        offsets = {}
    allowance_path = ctx.paths.state / "allowance.json"
    try:
        allowance = json.loads(allowance_path.read_text()) if allowance_path.exists() else {}
    except ValueError:
        allowance = {}
    timelines = None
    prices = load_prices(ctx)
    new: list[dict] = []
    for a in ctx.team.agents():
        if a.kind == HUMAN or not a.active:
            continue
        adapter = adapters.get(a.harness or "")
        if adapter is None or adapter.session_format not in PARSERS:
            continue
        for path, aux in agent_logs(ctx, adapter, a.name, lookback):
            st = offsets.get(path, {"offset": 0})
            try:
                lines, st["offset"] = _new_lines(path, st.get("offset", 0))
            except OSError:
                continue
            offsets[path] = st
            if not lines:
                continue
            turns = PARSERS[adapter.session_format](lines, st, aux)
            if st.get("rate_limits"):
                allowance[adapter.name] = st.pop("rate_limits")
            if turns and timelines is None:
                timelines = goal_timelines(ctx)
            for t in turns:
                t.setdefault("aux", aux)
                t["aux"] = bool(t["aux"] or aux)
                t.update(agent=a.name, harness=adapter.name, goal=_attribute(timelines.get(a.name, []), t["ts"]))
                t["est_usd"] = estimate(t, prices)
                new.append(t)
    if new:
        ctx.paths.usage.mkdir(parents=True, exist_ok=True)
        by_day: dict[str, list[dict]] = {}
        for t in new:
            day = _parse(t["ts"]).astimezone().date().isoformat() if t.get("ts") else local_today().isoformat()
            by_day.setdefault(day, []).append(t)
        for day, recs in by_day.items():
            with open(ctx.paths.usage / f"{day}.jsonl", "a") as fh:
                for r in recs:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    offsets_path.write_text(json.dumps(offsets))
    allowance_path.write_text(json.dumps(allowance))
    return len(new)


# --- totals -------------------------------------------------------------------------------------------


@dataclass
class Totals:
    tokens: int = 0
    aux_tokens: int = 0
    usd: float = 0.0
    unpriced_tokens: int = 0
    turns: int = 0

    def add(self, rec: dict) -> None:
        n = tokens(rec)
        self.tokens += n
        self.turns += 1
        if rec.get("aux"):
            self.aux_tokens += n
        if rec.get("est_usd") is None:
            self.unpriced_tokens += n
        else:
            self.usd += rec["est_usd"]


def records(ctx: Ctx, days: list[str]) -> list[dict]:
    out = []
    for day in days:
        f = ctx.paths.usage / f"{day}.jsonl"
        if f.exists():
            for ln in f.read_text().splitlines():
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    continue
    return out


@dataclass
class Summary:
    team_today: Totals = field(default_factory=Totals)
    agents_today: dict[str, Totals] = field(default_factory=dict)


def today(ctx: Ctx) -> Summary:
    s = Summary()
    for r in records(ctx, [local_today().isoformat()]):
        s.team_today.add(r)
        s.agents_today.setdefault(r["agent"], Totals()).add(r)
    return s


def goal_totals(ctx: Ctx, goal_id: int, opened: str) -> Totals:
    t = Totals()
    start = _parse(opened).astimezone().date()
    days = [(start + dt.timedelta(days=i)).isoformat() for i in range((local_today() - start).days + 1)]
    for r in records(ctx, days[-60:]):
        if r.get("goal") == goal_id:
            t.add(r)
    return t


def fmt(t: Totals) -> str:
    """'1.2M tokens (80k auxiliary), est. $3.40' — the estimate says when part is unpriced."""
    if not t.turns:
        return "no usage recorded"
    aux = f" ({usage.short(t.aux_tokens)} auxiliary)" if t.aux_tokens else ""
    if t.unpriced_tokens == t.tokens:
        money = "est. unavailable (no public price)"
    else:
        money = f"est. ${t.usd:,.2f}" + (f" (+{usage.short(t.unpriced_tokens)} tokens unpriced)" if t.unpriced_tokens else "")
    return f"{usage.short(t.tokens)} tokens{aux}, {money}"


def fmt_short(t: Totals) -> str:
    if not t.turns:
        return "—"
    money = "?" if t.unpriced_tokens == t.tokens else f"${t.usd:,.2f}{'+' if t.unpriced_tokens else ''}"
    return f"{usage.short(t.tokens)}/est.{money}"


def allowance_lines(ctx: Ctx) -> list[str]:
    """Account-wide allowance per harness: Codex from its session logs, Claude Code from its status
    line (card #120) when the team has a Claude agent or a reading."""
    from . import planusage

    out = _codex_allowance(ctx)
    if (planusage.snapshot_path(ctx.paths.root).exists()
            or any(a.harness == "claude" and a.active for a in ctx.team.agents() if a.kind != HUMAN)):
        out.append(planusage.line(ctx.paths.root))
    return out


def _codex_allowance(ctx: Ctx) -> list[str]:
    try:
        d = json.loads((ctx.paths.state / "allowance.json").read_text())
    except (OSError, ValueError):
        return []
    out = []
    for harness, rl in sorted(d.items()):
        p = rl.get("primary") or {}
        if p.get("used_percent") is None:
            continue
        win = p.get("window_minutes")
        period = (f"{round(win / 1440)}d" if win and win >= 1440 else f"{round(win / 60)}h" if win else "window")
        reset = ""
        if p.get("resets_at"):
            reset = f", resets {dt.datetime.fromtimestamp(p['resets_at']).strftime('%a %H:%M')}"
        out.append(f"{harness} {p['used_percent']:.0f}% of {period}{reset} (account-wide)")
    return out
