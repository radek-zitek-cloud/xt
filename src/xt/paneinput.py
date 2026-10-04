"""What the human types in the liaison's pane is recorded as a human-to-liaison message (card #193).

The record comes from the human's input, never from the agent's say-so. A hook can't prove that by
itself: it runs under the liaison's own harness, with the liaison's XT_AGENT, exactly like the
liaison's own tool calls. The harness's session log can: it is where the harness writes what was
typed in the pane, apart from tool calls and their results. So (lead's choice, xt #3135):

- The supervisor reads the liaison's current session log (the one `usage.session_for` finds, on
  every harness) from where it left off, and records each line the human typed as a message from
  the human to the liaison, logged and not delivered (the liaison already has it in its pane).
  Harness slash commands, `!` shell lines, the harness's own inserts (`<…>`) and what xt itself typed
  there (`[xt …` deliveries, `(xt: …` notes, first prompts) are left out. A multi-line paste is one
  entry in the log, so one message.
- On Claude Code, xt also installs a prompt-submit hook (`xt pane-input --hook`) in the liaison's
  settings. It queues the line and checks that the record can happen (the supervisor runs, the log
  is found); if not, the human sees a warning in the pane at once. A queued line that the log
  doesn't confirm within CONFIRM_WAIT is never recorded: the human gets an alert and a chat line.
  That's also what happens when an agent calls the command itself.
- `xt status` and the chat header say per harness whether pane input is recorded.

State: `.xt/state/pane_input.json` holds the read position per agent and the queued lines.
"""

import json
import os
import shlex
import time

from . import lifecycle, usage
from .adapters import load_adapters
from .alerts import Alerts
from .context import Ctx
from .ledger import PANE
from .paths import XtError
from .team import HUMAN, SYSTEM

HOOKED = ("claude",)  # harnesses xt installs a prompt hook in
CONFIRM_WAIT = 60  # seconds a hook's queued line waits for the session log to show it
XT_PREFIXES = ("[xt", "(xt:")  # what xt types into panes starts with one of these
FIRST_PROMPT = "an agent in the xt team"  # spawn.MARKER, in the first prompt's first line
SKIP_PREFIXES = ("/", "!", "<")  # slash commands, shell escapes, the harness's own inserts
SOURCE = PANE  # the `source` a recorded line carries in the ledger (ledger.is_pane)


def typed(text: str | None) -> bool:
    """Whether a user entry is something the human typed, worth recording."""
    t = (text or "").strip()
    if not t or t.startswith(SKIP_PREFIXES) or t.startswith(XT_PREFIXES):
        return False
    return FIRST_PROMPT not in t.split("\n", 1)[0]


def _text(content) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [c for c in content if isinstance(c, dict)]
        if any(c.get("type") in ("tool_result", "toolResult") for c in parts):
            return None  # a tool's result, not typed
        texts = [c.get("text") for c in parts if isinstance(c.get("text"), str)]
        return "\n".join(texts) if texts else None
    return None


def user_text(fmt: str | None, line: str) -> str | None:
    """The text of a user entry in a session log line (`fmt`: claude, codex or pi), else None."""
    try:
        d = json.loads(line)
    except ValueError:
        return None
    if not isinstance(d, dict):
        return None
    if fmt == "claude":
        if d.get("type") != "user" or d.get("isSidechain") or d.get("isMeta"):
            return None
        msg = d.get("message") or {}
        return _text(msg.get("content")) if msg.get("role", "user") == "user" else None
    if fmt == "codex":
        p = d.get("payload") or {}
        if d.get("type") != "response_item" or p.get("role") != "user" or p.get("type", "message") != "message":
            return None
        return _text(p.get("content"))
    if fmt == "pi":
        msg = d.get("message") or {}
        return _text(msg.get("content")) if d.get("type") == "message" and msg.get("role") == "user" else None
    return None


# --- state ---------------------------------------------------------------------------------------


def _path(ctx: Ctx):
    return ctx.paths.state / "pane_input.json"


def _load(ctx: Ctx) -> dict:
    try:
        return json.loads(_path(ctx).read_text())
    except (OSError, ValueError):
        return {}


def _save(ctx: Ctx, d: dict) -> None:
    tmp = _path(ctx).with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1))
    os.replace(tmp, _path(ctx))


# --- where the liaison's input is, and whether it can be recorded ----------------------------------


def liaison(ctx: Ctx):
    return ctx.team.lead_of_role("liaison")


def _adapter(ctx: Ctx, a):
    return load_adapters(ctx.paths).get(a.harness or "")


def session_log(ctx: Ctx, a) -> str | None:
    adapter = _adapter(ctx, a)
    if adapter is None or not adapter.session_format:
        return None
    return usage.session_for(ctx, adapter, a.name, usage.last_starts(ctx).get(a.name))


# The five states of the signal (card #193; #201 adds "isn't running" and "unknown").
RECORDED, LOG_ONLY, NOT_RUNNING, UNKNOWN, NOT_RECORDED = "recorded", "log only", "not running", "unknown", "not recorded"
HERDR_DOWN = "herdr server not reachable"
NO_LOG, NO_FORMAT = "no session log", "not on this harness"
WIDE_HEADER = 96  # the chat header adds the reason only above this width (card #202)
SNAPSHOT_FRESH = 30  # seconds the supervisor's saved live state stands in for Herdr (card #201, xt #3384)


def state(ctx: Ctx) -> tuple[str, str, str, str] | None:
    """(liaison name, harness, state, reason) for the liaison's pane input (cards #193, #201); None
    without any liaison. A stopped or retired liaison isn't running; a Herdr server that can't be
    reached leaves it unknown."""
    a = liaison(ctx) or next((x for x in ctx.team.agents() if x.role == "liaison"), None)
    if a is None:
        return None
    name, harness = a.name, a.harness or "?"
    if not a.active:
        return name, harness, NOT_RUNNING, "retired"
    adapter = _adapter(ctx, a)
    if adapter is None or not adapter.session_format:
        return name, harness, NOT_RECORDED, NO_FORMAT
    try:
        running = name in ctx.herdr.agents(max_snapshot_age=SNAPSHOT_FRESH)
    except XtError:  # Herdr down: unknown, unless the supervisor saved its live state just now
        return name, harness, UNKNOWN, HERDR_DOWN
    if not running:
        return name, harness, NOT_RUNNING, ""
    if session_log(ctx, a) is None:
        return name, harness, NOT_RECORDED, NO_LOG
    if harness in HOOKED:
        return name, harness, RECORDED, "prompt hook and session log"
    return name, harness, LOG_ONLY, "no warning in the pane"


def signal(ctx: Ctx) -> str | None:
    """One line for `xt status`: whether the liaison's pane input is recorded on its harness, in
    full (card #193; wording #203, states #201); None without a liaison."""
    s = state(ctx)
    if s is None:
        return None
    name, harness, kind, reason = s
    said = {RECORDED: f"pane input recorded ({reason})",
            LOG_ONLY: f"pane input recorded (session log only; {reason})",
            NOT_RUNNING: "pane input not recorded (the liaison isn't running)",  # ux on rc2, xt #3389
            UNKNOWN: f"pane input unknown ({reason})",
            NOT_RECORDED: f"pane input NOT recorded ({reason}): talk in xt chat"}[kind]
    return f"{name} ({harness}): {said}"


def header(s: tuple[str, str, str, str] | None, liaison_name: str, width: int) -> str:
    """The chat header for `state` `s` in `width` columns (cards #193, #202): one row. At most
    WIDE_HEADER columns the short form, above it with the reason, if it fits with 4 to spare."""
    if s is None:
        return f"xt chat with {liaison_name}"
    name, harness, kind, reason = s
    short = {RECORDED: "pane input recorded",
             LOG_ONLY: "pane input: session log only",
             NOT_RUNNING: "pane input: not running",  # the header names the liaison already (xt #3389)
             UNKNOWN: "pane input: unknown (herdr unreachable)",
             NOT_RECORDED: "pane input NOT recorded — type here"}[kind]
    wide = {RECORDED: f"pane input recorded ({reason})",
            LOG_ONLY: f"pane input: session log only ({reason})",
            NOT_RUNNING: short,
            UNKNOWN: f"pane input: unknown ({reason})",
            NOT_RECORDED: f"pane input NOT recorded ({reason}) — type here in chat"}[kind]
    head = f"xt chat with {name} ({harness}) · "
    if width > WIDE_HEADER and len(head + wide) <= width - 4:
        return head + wide
    return head + short


# --- the hook (Claude Code: UserPromptSubmit) -------------------------------------------------------


def hook_settings(ctx: Ctx, name: str, base: str | None) -> str:
    """A settings file for the liaison's Claude Code: its own permissions file (`base`, unchanged on
    disk) plus the prompt hook. Written under .xt/state/settings/; the path to pass."""
    data = json.loads((ctx.paths.root / base).read_text()) if base else {}
    hook = {"type": "command", "command": f"{shlex.quote(str(ctx.paths.xt_bin))} pane-input --hook"}
    hooks = data.setdefault("hooks", {})
    hooks.setdefault("UserPromptSubmit", []).append({"hooks": [hook]})
    out = ctx.paths.state / "settings" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1))
    return str(out)


def mark_start(ctx: Ctx, name: str) -> None:
    """The liaison is starting (do_spawn: spawn, restart, reset): its new session log is read from
    its first line, so a line typed before the supervisor's first scan isn't lost (rc5, QA #3159).
    Only a liaison xt never marked starts at the end of its log, so old history isn't recorded."""
    with ctx.ledger.lock():
        d = _load(ctx)
        d.setdefault("cursor", {})[name] = {"log": None, "offset": 0}
        _save(ctx, d)


def queue(ctx: Ctx, name: str, text: str) -> None:
    """Queue a line the hook saw: recorded only when the session log shows it was typed."""
    with ctx.ledger.lock():
        d = _load(ctx)
        d.setdefault("queued", []).append({"agent": name, "text": text, "at": time.time()})  # as submitted
        _save(ctx, d)


def hook(ctx: Ctx, name: str | None, text: str | None) -> str | None:
    """The hook's work: None when nothing needs saying, else the warning for the pane."""
    a = ctx.team.agent(name) if name else None
    if a is None or a.role != "liaison" or not typed(text):
        return None  # not the liaison's pane, or a line that isn't recorded anyway
    queue(ctx, a.name, text)
    if not lifecycle.recently_ticked(ctx):
        raise XtError("the supervisor isn't running, so nothing reads the pane input")
    if session_log(ctx, a) is None:
        raise XtError("xt can't find this session's log")
    return None


def warning(why: str) -> str:
    """The hook's output: a message Claude Code shows the human (it doesn't block the prompt)."""
    return json.dumps({"systemMessage": f"xt: this line is NOT recorded in the team's log ({why}). "
                                        f"The liaison still gets it; to have it on record, say it in xt chat."})


# --- the supervisor --------------------------------------------------------------------------------


def _new_lines(path: str, offset: int) -> tuple[list[str], int]:
    """Complete lines written after `offset`, and the offset after them."""
    with open(path, "rb") as fh:
        fh.seek(offset)
        data = fh.read()
    end = data.rfind(b"\n")
    if end < 0:
        return [], offset
    return data[:end].decode("utf-8", "replace").split("\n"), offset + end + 1


def scan(ctx: Ctx, now: float | None = None) -> list[str]:
    """Record what the human typed in the liaison's pane since the last scan, then refuse queued
    lines the log never showed. The supervisor's lines to say."""
    now = time.time() if now is None else now
    out: list[str] = []
    a = liaison(ctx)
    if a is None:
        return out
    path = session_log(ctx, a)
    adapter = _adapter(ctx, a)
    recorded: list[str] = []
    with ctx.ledger.lock():
        d = _load(ctx)
        cursor = d.setdefault("cursor", {})
        rec = cursor.get(a.name)
        if path:
            if rec is None:  # never marked (a liaison started before this xt): from now on, no old history
                rec = {"log": path, "offset": os.path.getsize(path)}
            elif rec["log"] != path:  # a session xt started (mark_start) or a new one: all of it
                rec = {"log": path, "offset": 0}
            try:
                lines, rec["offset"] = _new_lines(path, rec["offset"])
            except OSError:
                lines = []
            cursor[a.name] = rec
            for line in lines:
                text = user_text(adapter.session_format, line)
                if typed(text):
                    recorded.append(text)  # the line as submitted, spaces and all (rc5, QA #3159)
        queued = d.get("queued", [])
        for text in recorded:  # a queued line the log shows is confirmed
            hit = next((q for q in queued if q["agent"] == a.name and q["text"] == text), None)
            if hit:
                queued.remove(hit)
        stale = [q for q in queued if now - q["at"] >= CONFIRM_WAIT]
        d["queued"] = [q for q in queued if q not in stale]
        _save(ctx, d)
    for text in recorded:
        m = ctx.ledger.append(HUMAN, a.name, "ask", text, data={"source": SOURCE})  # logged, not delivered
        out.append(f"recorded #{m['id']}: the human typed in {a.name}'s pane")
    for q in stale:
        out.append(refuse(ctx, q))
    return out


def refuse(ctx: Ctx, q: dict) -> str:
    """A queued line the session log never showed: not recorded. An alert and a line in chat."""
    short = " ".join(q["text"].split())[:80]
    line = (f"pane input to {q['agent']} NOT recorded: the line wasn't found as typed in its session log "
            f"(\"{short}\")")
    ctx.ledger.append(SYSTEM, HUMAN, "system", line)
    Alerts(ctx).raise_or_count(f"pane-input:{q['agent']}",
                               f"{line}. If you typed it, say it again in xt chat; if you didn't, an agent "
                               f"tried to record words as yours.")
    return line
