"""Named operators and time-bound delegation (card #166).

An operator is an outside process acting for the human, such as the human's own coding-agent
session. It is never the human: `--as human` stays the human's terminal only (cards #62, #119).

- The human registers it once per operator session from their own terminal: `xt operator add NAME
  --pid PID`, where PID is the operator's long-lived process (its harness; `xt operator pid`, run by
  the operator, prints it). xt records the pid and its start time and writes a secret token to
  `.xt/operators/NAME.token`, readable only by the human's user.
- `--as NAME` is accepted only when both match: XT_OPERATOR_TOKEN holds the token, and the
  registered process (same pid, same start time) is this process or one of its ancestors. A token
  alone could be read by an agent under the same account; a process match alone could be any
  command the operator's harness runs. Either alone is refused.
- An operator sends reports to the liaison only, each marked as sent on the human's behalf, and
  never answers questions or approves anything.
- `xt delegate NAME --for 60m` (human only; at most 60 minutes, 30 by default) lets the operator run
  the delegable human-only commands until it expires or `xt delegate --revoke` ends it. Each one is
  recorded as "NAME, delegated by human until HH:MM". Expiry is checked when a command runs, from
  the stored end time: there is no timer.
- `xt delegate NAME --scope drive` (card #200) is a grant of another scope: the operator answers the
  human's questions, approves or denies hires and schedules, and gives goals to the liaison, each
  one message under its own name ending in DRIVE_MARK. Scopes don't combine: a new grant replaces
  the old one. When a drive grant ends (expired, noticed by the supervisor or the next command, or
  revoked), one ledger line says so.

Operators and grants live in the team's runtime state (`.xt/state/operators.json`, gitignored), not
in team.toml, so agents can't edit them through the roster. Per team: a new team needs a new
registration.
"""

import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets

from .context import Ctx
from .paths import Paths, XtError
from .team import HUMAN, SYSTEM, parse_interval

TOKEN_ENV = "XT_OPERATOR_TOKEN"
DELEGABLE = ("restart", "reset", "spawn", "up")
NEVER = "down, answers, approvals, version switches, registering operators and granting delegation"
MAX_GRANT = 3600
DEFAULT_GRANT = "30m"
MARK = "(sent by {name}, an operator, on the human's behalf)"  # the last line of an operator's message
DRIVE = "drive"  # card #200: the one scope besides the default commands
DRIVE_WHAT = "answers, approvals and goals"
# the last line of a drive action: starts with the record text the protocol names (card #172)
DRIVE_MARK = "({name}, delegated by human until {until}: an operator acting on the human's behalf)"


def _state(paths: Paths):
    return paths.state / "operators.json"


def load(paths: Paths) -> dict:
    try:
        return json.loads(_state(paths).read_text())
    except (OSError, ValueError):
        return {}


def _save(paths: Paths, d: dict) -> None:
    tmp = _state(paths).with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1))
    os.replace(tmp, _state(paths))


def names(paths: Paths) -> list[str]:
    return sorted(load(paths).get("operators", {}))


def is_operator(paths: Paths, name: str | None) -> bool:
    return bool(name) and name in load(paths).get("operators", {})


def token_path(paths: Paths, name: str):
    return paths.root / ".xt" / "operators" / f"{name}.token"


# --- processes ---------------------------------------------------------------------------------


def _stat(pid: int, proc: str = "/proc") -> tuple[int, str, str] | None:
    """(parent pid, start time in clock ticks, command name) of a process, or None."""
    try:
        raw = open(f"{proc}/{pid}/stat").read()
    except OSError:
        return None
    try:
        comm = raw[raw.index("(") + 1:raw.rindex(")")]
        fields = raw.rsplit(")", 1)[1].split()
        return int(fields[1]), fields[19], comm
    except (ValueError, IndexError):
        return None


def ancestors(proc: str = "/proc"):
    """(pid, start time, name) of this process and each ancestor, nearest first."""
    pid = os.getpid()
    while pid > 0:
        st = _stat(pid, proc)
        if st is None:
            return
        yield pid, st[1], st[2]
        if pid == 1:
            return
        pid = st[0]


HARNESSES = ("claude", "codex", "pi")


def harness_of(pid: int, proc: str = "/proc") -> str | None:
    """Which harness a process is (its program claude, codex or pi, as for the launch check), or
    None. pi runs under node, so its arguments count too."""
    from .launch import _harness, _names

    try:
        return _harness(_names(f"{proc}/{pid}"))
    except (OSError, ValueError):
        return None


def agent_of(pid: int, proc: str = "/proc") -> str | None:
    """The XT_AGENT a process carries (a team agent's harness), or None."""
    try:
        env = open(f"{proc}/{pid}/environ", "rb").read()
    except OSError:
        return None
    return next((v[len(b"XT_AGENT="):].decode(errors="replace") for v in env.split(b"\0")
                 if v.startswith(b"XT_AGENT=")), None)


def harness_ancestor(proc: str = "/proc") -> tuple[int, str] | None:
    """The nearest harness process above this one: what the human registers (`xt operator pid`)."""
    for pid, _, _ in ancestors(proc):
        harness = harness_of(pid, proc) if pid != os.getpid() else None
        if harness:
            return pid, harness
    return None


# --- registering -------------------------------------------------------------------------------


def add(ctx: Ctx, name: str, pid: int) -> list[str]:
    """Register (or re-register) operator NAME as process PID. Human only; the caller checks."""
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", name):
        raise XtError(f"operator names are lowercase letters, digits, - and _ (starting with a letter): {name!r}")
    if name in (HUMAN, SYSTEM) or ctx.team.agent(name) is not None:
        raise XtError(f"{name!r} is already a name in this team; pick another for the operator")
    st = _stat(pid) if pid > 1 else None
    if st is None:
        raise XtError(f"no process {pid} here: the operator's process must be running (`xt operator pid` prints it)")
    # Only a harness process, and not a team agent's: a shell, the terminal or Herdr would have the
    # team's agents among its descendants, and they could read the token.
    if not harness_of(pid):
        raise XtError(f"process {pid} is {st[2]}, not a harness ({', '.join(HARNESSES)}): register the "
                      f"operator's harness process, which its `xt operator pid` prints")
    agent = agent_of(pid)
    if agent:
        raise XtError(f"process {pid} is team agent {agent} (XT_AGENT={agent}), not an outside operator")
    token = secrets.token_hex(32)
    path = token_path(ctx.paths, name)
    path.parent.mkdir(mode=0o700, exist_ok=True)
    os.chmod(path.parent, 0o700)
    if path.exists():
        path.unlink()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(token + "\n")
    with ctx.ledger.lock():
        d = load(ctx.paths)
        d.setdefault("operators", {})[name] = {
            "pid": pid, "start": st[1], "process": st[2],
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            "registered": ctx.ledger.clock().isoformat(timespec="seconds"),
        }
        d.setdefault("grants", {}).pop(name, None)  # a new session starts without a grant
        _save(ctx.paths, d)
    ctx.ledger.append(SYSTEM, HUMAN, "system",
                      f"human registered operator {name} (process {pid}, {st[2]}); it may send reports to the liaison")
    return [f"registered operator {name}: process {pid} ({st[2]})",
            f"token: {path} (readable by your user only)",
            f"the operator runs xt with {TOKEN_ENV} set to that file's content and --as {name}, "
            f"from a command its process {pid} started; re-register after each operator session"]


def remove(ctx: Ctx, name: str) -> str:
    with ctx.ledger.lock():
        d = load(ctx.paths)
        if name not in d.get("operators", {}):
            raise XtError(f"no operator named {name!r}")
        del d["operators"][name]
        d.get("grants", {}).pop(name, None)
        _save(ctx.paths, d)
    try:
        token_path(ctx.paths, name).unlink()
    except OSError:
        pass
    ctx.ledger.append(SYSTEM, HUMAN, "system", f"human removed operator {name}")
    return f"removed operator {name}"


def listing(ctx: Ctx) -> list[str]:
    d = load(ctx.paths)
    out = []
    for name, rec in sorted(d.get("operators", {}).items()):
        g = active_grant(ctx, name)
        out.append(f"{name}: process {rec['pid']} ({rec.get('process', '?')}), registered {rec['registered'][:16]}"
                   + (f"; {grant_text(name, g)}" if g else ""))
    return out or ["(no operators registered)"]


# --- recognising -------------------------------------------------------------------------------


def verify(paths: Paths, name: str, env=None, proc: str = "/proc") -> None:
    """Refuse unless this process is operator NAME: the token in XT_OPERATOR_TOKEN and the registered
    process among this process's ancestors (same pid and start time). Both are needed."""
    env = os.environ if env is None else env
    rec = load(paths).get("operators", {}).get(name)
    if rec is None:
        raise XtError(f"{name!r} is not a registered operator")
    token = (env.get(TOKEN_ENV) or "").strip()
    token_ok = bool(token) and hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), rec["token_sha256"])
    process_ok = any(pid == rec["pid"] and start == rec["start"] for pid, start, _ in ancestors(proc))
    if token_ok and process_ok:
        return
    missing = [w for w, ok in (("its token (" + TOKEN_ENV + ")", token_ok),
                               (f"the registered process {rec['pid']} among this command's ancestors", process_ok))
               if not ok]
    raise XtError(f"--as {name} refused: this isn't operator {name} (missing {' and '.join(missing)}). "
                  f"The human registers the operator's current session with `xt operator add {name} --pid PID`.")


def outgoing(ctx: Ctx, name: str, to: str, mtype: str, body: str) -> tuple[str, dict | None]:
    """Check an operator's message and mark it: reports to the liaison, and under a drive grant
    goals to the liaison too (card #200). (the marked body, the drive grant or None)"""
    liaison = ctx.team.lead_of_role("liaison")
    if liaison is None or to != liaison.name:
        raise XtError(f"operator {name} sends to the liaison only"
                      + (f" ({liaison.name})" if liaison else " (this team has none)"))
    if mtype == "goal":
        g = drive(ctx, name, "gives the liaison goals")
        return body.strip() + "\n" + drive_mark(name, g), g
    if mtype != "report":
        raise XtError(f"operator {name} sends reports (--type report) and, under a drive grant, goals "
                      f"(--type goal); it answers with `xt answer` under a drive grant, and never opens tasks")
    return body.strip() + "\n" + MARK.format(name=name), None


def _check_size(ctx: Ctx, body: str) -> None:
    limit = int(ctx.team.log_setting("message_max_kb")) * 1024
    if len(body.encode()) > limit:
        raise XtError(f"message is {len(body.encode())} bytes, over the {limit} limit — "
                      "write the payload to a file and send its path instead")


def send(ctx: Ctx, name: str, to: str, mtype: str, body: str, ref: int | None = None) -> tuple[dict, str]:
    """Log and queue an operator's report (or, under drive, goal) to the liaison under the
    operator's own name. The supervisor delivers it; the liaison gets no reply hint, since nobody in
    the team messages an operator."""
    from .dispatch import deliver_or_queue

    if not body.strip():
        raise XtError("empty message")
    body, g = outgoing(ctx, name, to, mtype, body)
    _check_size(ctx, body)
    msg = ctx.ledger.append(name, to, mtype, body, ref, data=delegated(g) if g else None)
    return msg, deliver_or_queue(ctx, msg)


def is_operator_message(m: dict) -> bool:
    """An operator's report, or one of its drive actions (card #200), as recorded."""
    body = str(m.get("body", ""))
    if isinstance(m.get("delegated"), dict):
        return True
    return m.get("type") == "report" and body.endswith(MARK.format(name=m.get("from")))


# --- delegation --------------------------------------------------------------------------------


def _local(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts).astimezone()


def grant(ctx: Ctx, name: str, length: str | None, only: list[str] | None, scope: str | None = None) -> str:
    """The human grants operator NAME the delegable commands, or with scope drive answers, approvals
    and goals (card #200), for a while. One grant per operator: a new one replaces the old."""
    if not is_operator(ctx.paths, name):
        raise XtError(f"no operator named {name!r}: register it first (`xt operator add {name} --pid PID`)")
    if scope not in (None, DRIVE):
        raise XtError(f"unknown scope {scope!r}: the one scope is {DRIVE} ({DRIVE_WHAT})")
    if scope and only:
        raise XtError(f"--only picks commands of the default grant; a {DRIVE} grant covers {DRIVE_WHAT} only")
    secs = parse_interval(length or DEFAULT_GRANT)
    if secs > MAX_GRANT:
        raise XtError(f"a grant lasts at most 60 minutes (asked for {length}); grant again when it ends")
    commands = [] if scope else list(DELEGABLE) if not only else [c.strip() for c in only if c.strip()]
    bad = [c for c in commands if c not in DELEGABLE]
    if bad:
        raise XtError(f"not delegable: {', '.join(bad)}. Delegable: {', '.join(DELEGABLE)}; never: {NEVER}")
    now = ctx.ledger.clock()
    until = now + dt.timedelta(seconds=secs)
    g = {"until": until.isoformat(timespec="seconds"), "commands": commands, "granted": now.isoformat(timespec="seconds")}
    if scope:
        g["scope"] = scope
    with ctx.ledger.lock():
        d = load(ctx.paths)
        d.setdefault("grants", {})[name] = g
        d.get("ended", {}).pop(name, None)
        _save(ctx.paths, d)
    what = f"{DRIVE} ({DRIVE_WHAT})" if scope else ", ".join(commands)
    text = f"human delegated {what} to operator {name} until {_local(until.isoformat()):%H:%M}"
    ctx.ledger.append(SYSTEM, HUMAN, "system", text)
    return text


def _ended_line(name: str, at: dt.datetime) -> str:
    return f"drive grant for {name} ended {_local(at.isoformat()):%H:%M}"


def revoke(ctx: Ctx, name: str | None) -> str:
    announce_ended(ctx)  # a drive grant that already ran out says so as expired, not revoked
    now = ctx.ledger.clock()
    with ctx.ledger.lock():
        d = load(ctx.paths)
        grants = d.get("grants", {})
        gone = [n for n in list(grants) if name in (None, n)]
        drives = []
        for n in gone:
            g = grants.pop(n)
            if g.get("scope") == DRIVE:
                drives.append(n)
                d.setdefault("ended", {})[n] = {"at": now.isoformat(timespec="seconds"), "how": "revoked"}
        _save(ctx.paths, d)
    if not gone:
        return "no active delegation" + (f" for {name}" if name else "")
    text = f"human revoked the delegation to {', '.join(gone)}"
    if drives:  # card #200: the one visible line that the drive grant ended
        text += ": " + "; ".join(_ended_line(n, now) for n in drives)
    ctx.ledger.append(SYSTEM, HUMAN, "system", text)
    return text


def announce_ended(ctx: Ctx) -> list[str]:
    """Drive grants that ran out: one ledger line each, once (card #200). The supervisor calls it
    every tick, and the drive check before it refuses, so the line comes even without a timer."""
    now = ctx.ledger.clock()
    lines = []
    with ctx.ledger.lock():
        d = load(ctx.paths)
        for n, g in list(d.get("grants", {}).items()):
            until = dt.datetime.fromisoformat(g["until"])
            if g.get("scope") == DRIVE and until <= now:
                del d["grants"][n]
                d.setdefault("ended", {})[n] = {"at": g["until"], "how": "expired"}
                lines.append(_ended_line(n, until))
        if lines:
            _save(ctx.paths, d)
    for line in lines:
        ctx.ledger.append(SYSTEM, HUMAN, "system", line)
    return lines


ENDED_SHOWN = 3600  # seconds `xt status` and the TUI header keep showing that a drive grant ended


def ended_grants(ctx: Ctx) -> list[str]:
    """Drive grants that ended within the last hour, for `xt status` and the TUI header."""
    now = ctx.ledger.clock()
    out = []
    for n, e in sorted(load(ctx.paths).get("ended", {}).items()):
        at = dt.datetime.fromisoformat(e["at"])
        if (now - at).total_seconds() <= ENDED_SHOWN:
            out.append(_ended_line(n, at) + f" ({e['how']})")
    return out


def active_grant(ctx: Ctx, name: str) -> dict | None:
    """The operator's grant while it lasts (checked against the stored end time, now)."""
    g = load(ctx.paths).get("grants", {}).get(name)
    if not g or dt.datetime.fromisoformat(g["until"]) <= ctx.ledger.clock():
        return None
    return g


def scope_text(g: dict) -> str:
    """What a grant covers, in a few words: `drive` or the commands."""
    return DRIVE if g.get("scope") == DRIVE else ", ".join(g["commands"])


def grant_text(name: str, g: dict) -> str:
    return f"delegated to {name} until {_local(g['until']):%H:%M}: {scope_text(g)}"


def active_grants(ctx: Ctx) -> list[str]:
    """One line per active grant, then drive grants that ended lately, for `xt status` and the TUI
    header."""
    return [grant_text(n, g) for n in names(ctx.paths) if (g := active_grant(ctx, n))] + ended_grants(ctx)


def _active(g: dict) -> str:
    return f"grant active: {scope_text(g)} until {_local(g['until']):%H:%M}"


def allowed(ctx: Ctx, name: str, command: str) -> dict:
    """The grant under which operator NAME may run a delegable command now; refuses otherwise.
    Nothing is recorded yet: `record` says what happened once the command has run (rc4)."""
    if command not in DELEGABLE:
        raise XtError(f"`xt {command}` is never delegated (never: {NEVER}); only the human runs it")
    g = active_grant(ctx, name)
    if g is None:
        raise XtError(f"operator {name} has no active delegation: only the human runs `xt {command}` "
                      f"(the human grants one with `xt delegate {name} --for 30m`)")
    if command not in g["commands"]:
        if g.get("scope") == DRIVE:  # card #200: the refusal names the active grant
            raise XtError(f"{_active(g)}; {command} not included (scopes don't combine: the human grants "
                          f"`xt delegate {name}` for commands, which replaces the {DRIVE} grant)")
        raise XtError(f"operator {name}'s delegation covers {', '.join(g['commands'])}, not {command}")
    return g


def drive(ctx: Ctx, name: str, action: str) -> dict:
    """The drive grant under which operator NAME may act for the human now (card #200); refuses
    with what's active instead, or that the grant ended. `action` completes "only the human …"."""
    announce_ended(ctx)
    g = active_grant(ctx, name)
    if g is not None and g.get("scope") == DRIVE:
        return g
    if g is not None:
        raise XtError(f"{_active(g)}; {DRIVE_WHAT} not included: the human grants them with "
                      f"`xt delegate {name} --scope {DRIVE}`, which replaces this grant")
    e = load(ctx.paths).get("ended", {}).get(name)
    if e:
        raise XtError(f"operator {name}'s {DRIVE} grant ended {_local(e['at']):%H:%M} ({e['how']}): "
                      f"only the human {action} now")
    raise XtError(f"operator {name} has no {DRIVE} grant: only the human {action} (the human grants one "
                  f"with `xt delegate {name} --for 30m --scope {DRIVE}`)")


def until_text(g: dict) -> str:
    return f"{_local(g['until']):%H:%M}"


def drive_mark(name: str, g: dict) -> str:
    return DRIVE_MARK.format(name=name, until=until_text(g))


def delegated(g: dict) -> dict:
    """The data a drive action carries: who delegated it and until when (card #200)."""
    return {"delegated": {"by": HUMAN, "until": g["until"]}}


def act(ctx: Ctx, name: str, g: dict, to: str, mtype: str, text: str, ref: int | None,
        data: dict | None = None) -> tuple[dict, str]:
    """Record one drive action as a message under the operator's own name, marked, and deliver it
    (the supervisor does, as for any operator message). It never reads as sent by `human`."""
    from .dispatch import deliver_or_queue

    body = text.strip() + "\n" + drive_mark(name, g)
    _check_size(ctx, body)
    msg = ctx.ledger.append(name, to, mtype, body, ref, data={**(data or {}), **delegated(g)})
    return msg, deliver_or_queue(ctx, msg)


def _drive_answer(ctx: Ctx, qid: int) -> tuple[str, str] | None:
    """(`NAME (operator, delegated by you until HH:MM)`, the answer) when an operator's drive action
    answered question or approval `qid` (card #200); else None."""
    for m in ctx.ledger.messages():
        d = m.get("delegated")
        if m.get("ref") == qid and isinstance(d, dict) and isinstance(m.get("answer"), dict):
            who = f"{m['from']} (operator, delegated by you until {_local(d['until']):%H:%M})"
            return who, m["body"].rsplit("\n", 1)[0]
    return None


def answered_by(ctx: Ctx, qid: int) -> str | None:
    """`answered by NAME (operator, delegated by you until HH:MM): ANSWER`, or None (card #200)."""
    found = _drive_answer(ctx, qid)
    return f"answered by {found[0]}: {found[1]}" if found else None


def already_answered(ctx: Ctx, qid: int) -> str | None:
    """The refusal of the human's later answer to a question an operator answered, read once
    (card #203): `#5 already answered by op (operator, …): "yes" — nothing sent.`; or None."""
    found = _drive_answer(ctx, qid)
    return f'#{qid} already answered by {found[0]}: "{found[1]}" — nothing sent.' if found else None


def record(ctx: Ctx, name: str, g: dict, what: str, failed: str | None = None) -> None:
    """The log line for a delegated command, written after it ran: as it ran, or as failed."""
    line = f"{name}, delegated by human until {_local(g['until']):%H:%M}: xt {what}"
    if failed:
        line += f" (failed: {' '.join(failed.split())})"
    ctx.ledger.append(SYSTEM, HUMAN, "system", line)
