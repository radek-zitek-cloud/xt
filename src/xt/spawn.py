"""Spawning and retiring agents, with human approval of spawns the lead requests."""

import json
import os
import re
import shlex
import time

from . import (
    __version__,
    brief,
    capstart,
    paneinput,
    permissions,
    skills,
    usage,
    versions,
)
from .adapters import codex_options_text, get_adapter, load_adapters
from .alerts import Alerts
from .approvals import Approvals
from .context import Ctx
from .dispatch import send
from .herdr import DELIVERABLE, HerdrError
from .lifecycle import Jobs, drop, set_expected, set_stopped
from .paths import XtError
from .team import HUMAN, SYSTEM, schedule_text

PRECEDENCE = """\
PRECEDENCE: for everything about this team — who you are, who you talk to, how you send and
receive messages, how you report, where you keep notes — the xt protocol below wins over any
other instructions you may have (global or project instruction files, memories, skills). For
everything else (how you do your actual work), your usual instructions still apply."""


START_NOW = "Start now:"  # the first prompt's last line: stays on screen when the first line has scrolled away


def notes_section(ctx: Ctx, name: str) -> str:
    """The agent's notes file, whole and byte for byte (trailing whitespace too, no newline
    translation), for its first prompt (card #197), between a heading and an end line; nothing when
    there's no file."""
    path = ctx.paths.members / name / "notes.md"
    try:
        raw = path.read_bytes()
        notes = raw.decode()
    except (OSError, UnicodeDecodeError):
        return ""
    budget = ctx.team.notes_budget(ctx.team.agent(name))  # card #198 (16,000 bytes unless team.toml says)
    over = (f"(This file is {len(raw)} bytes, over the notes budget of {budget} bytes: it is here whole, "
            f"but shorten it.)\n") if len(raw) > budget else ""
    return (f"===== your notes (members/{name}/notes.md, whole) =====\n{over}{notes}"
            f"{'' if notes.endswith(chr(10)) or not notes else chr(10)}===== end of your notes =====\n\n")


def first_prompt(ctx: Ctx, name: str) -> str:
    a = ctx.team.agent(name)
    role_file = ctx.paths.role_file(a.role)
    protocol = ctx.paths.protocol.read_text()
    role = role_file.read_text()
    xt = ctx.paths.xt_bin
    harness = load_adapters(ctx.paths).get(a.harness or "")
    note =f"{harness.first_prompt_note}\n\n" if harness and harness.first_prompt_note else ""  # card #180
    return f"""You are **{name}**, an agent in the xt team "{ctx.team.name}". Your role is **{a.role}**; \
you report to **{a.reports_to}**. The team's repo (your home, not your workspace) is {ctx.paths.root}. \
Run xt as `{xt}` (absolute path — don't rely on PATH). Always pass `--as {name}` when you use xt.

{PRECEDENCE}

===== protocol.md =====
{protocol}
===== roles/{a.role}.md =====
{role}
===== team skills (read a skill's file when you need it) =====
{skills.render(ctx.paths)}

===== your brief (`{xt} brief --as {name}`) =====
{brief.build(ctx, name)}

{notes_section(ctx, name)}{note}{START_NOW} follow your role's "on start" instructions. If you have nothing to do, say so briefly and stop."""


AGENT_ENV = "XT_AGENT"  # set in every agent's pane: marks its shells as an agent's, never the human's


def do_spawn(ctx: Ctx, name: str) -> str:
    """Start an agent already in team.toml: new workspace, harness start, first prompt."""
    a = ctx.team.agent(name)
    if a is None or not a.active:
        raise XtError(f"{name!r} is not an active agent in team.toml")
    if not ctx.paths.role_file(a.role).exists():
        raise XtError(f"role file {ctx.paths.role_file(a.role)} doesn't exist — write it first")
    if name in ctx.herdr.agents():
        raise XtError(f"{name} is already running: spawn starts an agent that isn't running "
                      f"(`xt restart {name}` restarts a running one)")
    adapter = get_adapter(ctx.paths, a.harness)
    # card #186: refuses a `require` the harness can't enforce, or a legacy line that would loosen
    # the block, before anything runs; generates the harness's settings from [capabilities]
    plan = capstart.plan(ctx, a, adapter, load_adapters(ctx.paths))
    settings, skipped = plan.settings, plan.skipped
    args = adapter.start_args(a.model, plan.connectors, str(ctx.paths.root),
                              plan.settings_file, plan.options) + plan.args  # may refuse an opt-in
    pane, workspace = ctx.herdr.create_workspace(str(ctx.paths.root), f"{ctx.team.name}·{name}")
    # Before the harness starts, so it and every shell it opens inherit it (card #103).
    ctx.herdr.run_in_fresh_pane(pane, f"export {AGENT_ENV}={shlex.quote(name)}")
    answered: list[str] = []
    began = time.time()
    versions.mark_starting(ctx, name, ctx.ledger.clock())  # its first brief comes before the record (#177)
    if a.role == "liaison":
        paneinput.mark_start(ctx, name)  # card #193: its new session log is read from the start
    try:
        ctx.herdr.start_agent(name, adapter.herdr_kind, pane, args)
    except HerdrError as e:
        # Herdr refuses when the harness blocks at startup (e.g. claude's folder-trust question).
        # The agent is registered and blocked; answer the dialog and wait until it's ready.
        if e.code != "agent_not_ready" or not _ready_after_dialogs(ctx, name, adapter, pane, answered):
            ctx.herdr.close_workspace(workspace)
            raise
    except XtError:
        ctx.herdr.close_workspace(workspace)
        raise
    set_expected(ctx, name, True)
    set_stopped(ctx, name, False)
    Alerts(ctx).resolve(f"launch:{name}")  # xt started it, with its settings (card #165)
    Alerts(ctx).resolve(f"partprompt:{name}")  # a new start sends a new first prompt (card #167)
    Resends(ctx).drop(name)
    answered += answer_startup_dialogs(ctx, adapter, pane)
    for dialog in answered:
        ctx.ledger.append(SYSTEM, HUMAN, "system", f"answered {a.harness}'s '{dialog}' dialog for {name}")
    settled = wait_settled(ctx, adapter, pane)
    landed = send_first_prompt(ctx, name, pane, adapter, guarded(adapter, first_prompt(ctx, name)))
    note = "" if landed else " — FIRST PROMPT NOT CONFIRMED, see alert"
    if landed and adapter.check_prompt_in_log:
        note = check_prompt_in_log(ctx, name, adapter, began, settled)
    versions.record_agent_start(ctx, name, ctx.ledger.clock(), a.codex_options, capstart.record(plan))
    caps_line = (f"capabilities: {capstart.row(plan.caps, adapter, capstart.legacy_lines(a), name, 200, plan.was_loaded, plan.source)}"
                 + (f" (settings generated: .xt/state/settings/{name}.json)" if plan.generated else ""))
    ctx.ledger.append(SYSTEM, HUMAN, "system",
                      f"started {name} ({a.role}, {a.harness}) in workspace {workspace} with xt "
                      f"{versions.display(__version__)}{note}\n{caps_line}")  # card #186: one start, one note
    if a.codex_options:
        ctx.ledger.append(SYSTEM, HUMAN, "system", f"{name}: Codex options {codex_options_text(a.codex_options)}")
    if a.connectors:
        ctx.ledger.append(SYSTEM, HUMAN, "system",
                          f"{name}: account connectors opted in: {', '.join(a.connectors)}"
                          + (f" ({adapter.connectors_note})" if adapter.connectors_note else ""))
    elif adapter.connectors not in ("blocked", "none"):
        ctx.ledger.append(SYSTEM, HUMAN, "system",
                          f"{name}: the operator's account connectors are not blocked in {a.harness} "
                          f"({adapter.connectors_note or 'no restriction declared'})")
    if settings:
        ctx.ledger.append(SYSTEM, HUMAN, "system", permissions.start_note(name, settings))
    elif skipped:
        ctx.ledger.append(SYSTEM, HUMAN, "system", skipped)
    if adapter.desktop_tools not in ("blocked", "none"):
        ctx.ledger.append(SYSTEM, HUMAN, "system",
                          f"{name}: desktop and browser tools are not fully blocked in {a.harness} "
                          f"({adapter.desktop_tools_note or 'no restriction declared'}); agents must not use them")
    return workspace


RETRY_DELAY = 5.0
POLL = 1.0
DIALOG_QUIET_CHECKS = 4  # consecutive checks (POLL apart) without a known dialog = ready
LANDED_WAIT = 20  # seconds to wait for the first prompt's text to show up in the transcript
MARKER = "an agent in the xt team"  # the first prompt's first line


def _flat(text: str) -> str:
    """Screen text with line wrapping undone, so a phrase split across lines still matches."""
    return " ".join(text.split())


def answer_startup_dialogs(ctx: Ctx, adapter, pane: str) -> list[str]:
    """Answer dialogs the adapter declares (e.g. codex's folder trust) before any prompt is sent.

    Typing a prompt into such a dialog loses the prompt: codex's 'Trust this folder?' consumed the
    liaison's first prompt in both of the first two real runs (2026-09-26)."""
    if not adapter.startup_dialogs:
        return []
    answered: list[str] = []
    quiet = checks = 0
    while quiet < DIALOG_QUIET_CHECKS and checks < 40:
        checks += 1
        screen = _flat(ctx.herdr.read_pane(pane, lines=60))
        hit = next((d for d in adapter.startup_dialogs if any(_flat(m) in screen for m in d["match"])), None)
        if hit:
            ctx.herdr.send_keys(pane, *hit["keys"])
            answered.append(hit["name"])
            quiet = 0
            time.sleep(2 * POLL)
            continue
        quiet += 1
        time.sleep(POLL)
    return answered


READY_CHECKS = 30  # POLL-spaced checks for a blocked-at-startup agent to become ready


def _ready_after_dialogs(ctx: Ctx, name: str, adapter, pane: str, answered: list[str]) -> bool:
    answered += answer_startup_dialogs(ctx, adapter, pane)
    for _ in range(READY_CHECKS):
        if ctx.herdr.status(name) in ("idle", "done"):
            return True
        time.sleep(POLL)
    return False


def _landed(ctx: Ctx, pane: str) -> bool:
    """The prompt's first line (MARKER) or its last line (START_NOW) is on screen. A long prompt plus
    the agent's first output pushes the first line out of the read window: xt then resent the
    lead's whole first prompt although it had landed (card #115, 2026-09-29)."""
    deadline = time.monotonic() + LANDED_WAIT
    while True:
        screen = _flat(ctx.herdr.read_pane(pane, lines=400))
        if MARKER in screen or START_NOW in screen:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL)


SETTLE_CHECKS = 30  # most POLL-spaced checks wait_settled waits for a still screen


def wait_settled(ctx: Ctx, adapter, pane: str) -> bool:
    """Wait until the harness's screen has stayed the same for `adapter.ready_settle` checks: a
    harness still drawing its start-up screen doesn't take input yet, and a prompt typed then loses
    its first characters (pi, card #167). True when it settled (or nothing to wait for), False when
    it kept changing: xt types the prompt anyway and the log check reports what arrived."""
    if not adapter.ready_settle:
        return True
    last, still = None, 0
    for _ in range(SETTLE_CHECKS):
        screen = ctx.herdr.read_pane(pane, lines=60)
        still = still + 1 if screen == last and screen.strip() else 0
        if still >= adapter.ready_settle:
            return True
        last = screen
        time.sleep(POLL)
    return False


def guarded(adapter, text: str) -> str:
    """The prompt as typed: after the adapter's `first_prompt_prefix` line, if it has one (pi, card
    #167 rc5), so characters lost at the start come out of that line, not the prompt's opening."""
    return f"{adapter.first_prompt_prefix}\n{text}" if adapter.first_prompt_prefix else text


RESEND_NOTE = ("(xt: your first prompt reached you with its start missing. Here it is again, whole; it "
               "replaces the damaged one. Carry on from it, and don't redo what you've already done or "
               "reported.)")


def check_prompt_in_log(ctx: Ctx, name: str, adapter, since: float, settled: bool) -> str:
    """Whether the first prompt reached the harness whole, from its session log (card #167). A
    damaged one is resent whole, once, when the agent is next idle: the supervisor does it (see
    `run_resends`), so a start never waits on the agent's first turn. The result is a note for the
    start record."""
    deadline = time.monotonic() + LANDED_WAIT
    while True:
        found = usage.prompt_in_log(ctx, adapter, name, since)
        if found or time.monotonic() >= deadline:
            break
        time.sleep(POLL)
    if found == usage.WHOLE:
        return ""
    if found == usage.INCOMPLETE:
        Resends(ctx).add(name, since, settled)
        return (" — FIRST PROMPT ARRIVED DAMAGED (its opening missing): xt resends it whole once the agent "
                "is idle")
    return " — first prompt not checked: no session log showed it yet"


def _partprompt(ctx: Ctx, name: str, harness: str, settled: bool) -> None:
    Alerts(ctx).raise_(
        f"partprompt:{name}",
        f"{name}'s first prompt reached {harness} without its opening, and so did xt's one resend "
        f"(the harness wasn't ready for input{'' if settled else '; its screen never settled'}). It has "
        f"its identity and protocol, but it worked from a prompt without its opening. "
        f"`xt stop {name}` and `xt spawn {name}` start it again.",
    )


RESEND_CHECK = 120  # seconds after the resend for the whole prompt to show up in the session log


class Resends:
    """First prompts to resend whole, once (card #167 rc5): `.xt/state/prompt_resends.json`,
    name -> {since, settled, sent (epoch seconds, once sent)}."""

    def __init__(self, ctx: Ctx):
        self.ctx = ctx
        self.path = ctx.paths.state / "prompt_resends.json"

    def load(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def _save(self, d: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=1))
        os.replace(tmp, self.path)

    def add(self, name: str, since: float, settled: bool) -> None:
        with self.ctx.ledger.lock():
            d = self.load()
            d[name] = {"since": since, "settled": settled}
            self._save(d)

    def drop(self, name: str) -> None:
        with self.ctx.ledger.lock():
            d = self.load()
            if d.pop(name, None) is not None:
                self._save(d)

    def update(self, name: str, **fields) -> None:
        with self.ctx.ledger.lock():
            d = self.load()
            if name in d:
                d[name].update(fields)
                self._save(d)


def run_resends(ctx: Ctx, live: dict, now: float | None = None) -> list[str]:
    """The supervisor's step for damaged first prompts (card #167 rc5): resend the whole prompt to
    an agent that is idle, once; then read its session log until the whole opening shows up, and
    raise the partprompt alert if it doesn't. Never waits."""
    resends = Resends(ctx)
    pending = resends.load()
    if not pending:
        return []
    now = now if now is not None else time.time()
    adapters = load_adapters(ctx.paths)
    out = []
    for name, rec in pending.items():
        a, agent = ctx.team.agent(name), live.get(name)
        adapter = adapters.get(a.harness) if a else None
        if agent is None or adapter is None:
            resends.drop(name)  # stopped, retired or gone: a new start sends a new prompt
            continue
        if "sent" not in rec:
            if agent.status not in DELIVERABLE:
                continue  # still working on the damaged prompt
            text = f"{RESEND_NOTE}\n{first_prompt(ctx, name)}"
            try:
                ctx.herdr.prompt(name, guarded(adapter, text), confirm=True)
            except XtError as e:
                resends.drop(name)
                _partprompt(ctx, name, adapter.name, rec.get("settled", True))
                out.append(f"resend of {name}'s first prompt failed: {e}")
                continue
            resends.update(name, sent=now)
            ctx.ledger.append(SYSTEM, HUMAN, "system",
                              f"resent {name}'s first prompt whole (it arrived with its opening missing)")
            out.append(f"resent {name}'s first prompt")
            continue
        if usage.prompt_in_log(ctx, adapter, name, rec["since"]) == usage.WHOLE:
            resends.drop(name)
            ctx.ledger.append(SYSTEM, HUMAN, "system", f"{name}'s resent first prompt arrived whole")
            out.append(f"{name}'s resent first prompt arrived whole")
        elif now - rec["sent"] >= RESEND_CHECK:
            resends.drop(name)
            _partprompt(ctx, name, adapter.name, rec.get("settled", True))
            out.append(f"alert: {name}'s resent first prompt arrived damaged too")
    return out


def send_first_prompt(ctx: Ctx, name: str, pane: str, adapter, text: str) -> bool:
    """Deliver the first prompt and confirm it really landed in the conversation.

    Two checks, both needed: herdr must see the agent start working on it (catches a prompt that
    was typed but never submitted), and the prompt's text must appear on the agent's screen
    (catches a prompt swallowed by a startup dialog, where the harness's own startup looked like
    'working'). Retry once; if it still doesn't land, alert the human instead of carrying on."""
    assert MARKER in text and START_NOW in text
    for attempt in (1, 2):
        try:
            ctx.herdr.prompt(name, text, confirm=True)
        except HerdrError as e:
            if e.code not in ("agent_prompt_stalled", "timeout"):
                raise
            time.sleep(RETRY_DELAY)
        if _landed(ctx, pane):
            return True
        answer_startup_dialogs(ctx, adapter, pane)
    Alerts(ctx).raise_(
        f"noprompt:{name}",
        f"{name} started but its first prompt (identity, role, protocol) never showed up in its "
        f"conversation. It would act without knowing who it is. Look at its pane (a dialog xt doesn't "
        f"know?), then `xt stop {name}` and `xt spawn {name}`.",
    )
    return False


def spawn_settings(ctx: Ctx, name: str, harness: str, own: str | None) -> str:
    """What the spawned agent's settings will be, in one sentence for the approval (card #122).

    `own` is the `permissions` line the entry will have (from `--permissions`, or kept from an
    existing entry). Checked with the #117 preflight here, so a bad file refuses the request before
    any approval is asked for; do_spawn checks it again at the start."""
    adapter = get_adapter(ctx.paths, harness)
    if own and not adapter.settings_flag:
        raise XtError(f"{name}: harness {adapter.name} takes no settings file, so it takes no "
                      f"permissions file (asked for: {own}); use claude for that agent or leave it out")
    rel = own or (ctx.team.default_permissions if adapter.settings_flag else None)
    if rel:
        s = permissions.preflight(ctx.paths.root, rel)
        return f"Settings: {s.rel} (permissions.defaultMode {s.mode or 'not set'})."
    if adapter.settings_flag:
        return (f"WARNING: {name} would start without a permissions file, so the operator's own "
                f"{adapter.name} defaults apply (--permissions FILE gives it one).")
    if ctx.team.default_permissions:
        return f"Team default permissions file {ctx.team.default_permissions} not applied ({adapter.name} takes no settings file)."
    return ""


def request_spawn(
    ctx: Ctx, requester: str, name: str, harness: str | None, model: str | None,
    role: str | None, reports_to: str | None, permissions_file: str | None = None,
) -> str:
    existing = ctx.team.agent(name)
    if existing and existing.kind == HUMAN:
        raise XtError("can't spawn the human")
    if existing is None and not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", name):
        raise XtError(f"agent names are lowercase letters, digits, - and _ (starting with a letter): {name!r}")
    if existing and not (harness or role):
        harness, role, model = existing.harness, existing.role, model or existing.model
        reports_to = reports_to or existing.reports_to
    if not (harness and role):
        raise XtError("new agents need --harness and --role")
    reports_to = reports_to or requester
    if requester != HUMAN:
        r = ctx.team.agent(requester)
        if r is None or not r.active:
            raise XtError(f"{requester!r} is not an active member")
        if r.role == "liaison":
            raise XtError(
                "the liaison doesn't spawn agents: write what the human wants into a goal "
                "(`xt goal new` / `xt goal dispatch`) and the lead will design and staff the team"
            )
        if reports_to != requester and ctx.team.agent(reports_to) and ctx.team.agent(reports_to).reports_to != requester:
            raise XtError("you can spawn agents only into your own part of the hierarchy")
    if ctx.team.agent(reports_to) is None:
        raise XtError(f"reports_to {reports_to!r} is not in the team")
    get_adapter(ctx.paths, harness)
    if not ctx.paths.role_file(role).exists():
        raise XtError(f"roles/{role}.md doesn't exist — write the role brief first")
    active = [a for a in ctx.team.agents() if a.active and a.kind != HUMAN]
    if not existing and len(active) >= int(ctx.team.policy("max_agents")) and requester != HUMAN:
        raise XtError(f"team is at max_agents ({len(active)}); ask the human to raise it first")

    own = permissions_file or (existing.permissions if existing else None)
    note = spawn_settings(ctx, name, harness, own)  # refuses a bad file before anything else
    # card #186: refuses a `require` the harness can't enforce before an approval is asked for
    caps_note = capstart.request_sentence(ctx, name, get_adapter(ctx.paths, harness), load_adapters(ctx.paths), own)
    req = {"requester": requester, "name": name, "harness": harness, "model": model,
           "role": role, "reports_to": reports_to, "caps_note": caps_note}
    if permissions_file:
        req["permissions"] = permissions_file
    if note:
        req["settings_note"] = note
    if requester != HUMAN and ctx.team.policy("spawn_approval"):
        rid = Approvals(ctx).add(req)
        return f"approval #{rid} requested from the human; you'll get a message when it's decided"
    if requester != HUMAN:
        jid = Jobs(ctx).add("spawn", req, requester)
        return f"spawn job #{jid} queued; the supervisor starts {name} within seconds and messages you"
    return execute_spawn(ctx, req)


def execute_spawn(ctx: Ctx, req: dict) -> str:
    ctx.team.upsert_agent(req["name"], req["role"], req["harness"], req.get("model"), req["reports_to"],
                          permissions=req.get("permissions"))
    ctx.team.save()
    ctx.reload_team()
    ws = do_spawn(ctx, req["name"])
    return f"spawned {req['name']} in workspace {ws}"


def decide(ctx: Ctx, req_id: int, approve: bool, by: str | None = None) -> str:
    """Carry out the answer to approval `req_id`. `by` names who decided when it isn't the human
    (an operator under a drive grant, card #200), for the requester's message."""
    req = Approvals(ctx).pop(req_id)
    if req.get("kind") == "schedule":
        if approve:
            ctx.team.set_schedule(req["name"], req["every"], req.get("message"), req.get("between"), req.get("at"))
            ctx.team.save()
            ctx.reload_team()
            result = f"{req['name']} is now woken {schedule_text(ctx.team.agent(req['name']))} when idle"
        else:
            result = f"schedule for {req['name']} denied"
    elif approve:
        result = execute_spawn(ctx, req)
    else:
        result = f"spawn of {req['name']} denied"
    if req["requester"] != HUMAN:
        send(ctx, SYSTEM, req["requester"], "system",
             f"{by or 'Human'} {'approved' if approve else 'denied'} approval #{req_id}: {result}")
    return result


def retire(ctx: Ctx, requester: str, name: str) -> str:
    a = ctx.team.agent(name)
    if a is None or a.kind == HUMAN:
        raise XtError(f"no agent named {name!r}")
    r = ctx.team.agent(requester)
    if requester != HUMAN and r is not None and r.role == "liaison":
        raise XtError("the liaison doesn't retire agents; ask the human")
    if requester != HUMAN and a.reports_to != requester:
        raise XtError(f"only {a.reports_to} or the human can retire {name}")
    if requester != HUMAN:
        jid = Jobs(ctx).add("retire", {"name": name}, requester)
        return f"retire job #{jid} queued; the supervisor closes {name} within seconds and messages you"
    return retire_now(ctx, requester, name)


def retire_now(ctx: Ctx, requester: str, name: str) -> str:
    """Close the agent's workspace and mark it retired (the human, or the supervisor for a job)."""
    live = ctx.herdr.agents().get(name)
    set_expected(ctx, name, False)
    set_stopped(ctx, name, False)
    drop(ctx, name, f"{name} was retired")  # card #134
    if live:
        ctx.herdr.close_workspace(live.workspace_id)
    ctx.team.set_status(name, "retired")
    ctx.team.save()
    ctx.reload_team()
    ctx.ledger.append(SYSTEM, HUMAN, "system", f"{requester} retired {name}")
    return f"retired {name}" + (" (workspace closed)" if live else "")


def stop(ctx: Ctx, name: str) -> str:
    """Close an agent's workspace without changing the roster (it can be started again)."""
    live = ctx.herdr.agents().get(name)
    set_expected(ctx, name, False)
    set_stopped(ctx, name, True)
    drop(ctx, name, f"{name} was stopped")  # card #134
    if not live:
        return f"{name} isn't running"
    ctx.herdr.close_workspace(live.workspace_id)
    ctx.ledger.append(SYSTEM, HUMAN, "system", f"stopped {name}")
    return f"stopped {name}"
