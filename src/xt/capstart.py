"""Card #186: an agent's start under the capability model, and its compact row.

`plan` turns the agent's effective capabilities (capabilities.effective) into what its harness
starts with: the generated Claude settings (the legacy file merged on top as extras, which may only
restrict), the Codex sandbox options, pi's skill flags. It refuses before anything runs: a `require`d
capability the harness can only keep advisory, or a legacy line that would loosen the block. An agent
without a [capabilities] block (its own or the team's) starts as before; only the personal skills
(off by default, Q3) and the display change for it.

`row` is the one compact line every surface shows (status, start note, spawn approval, brief, TUI):
what deviates from the defaults, grouped by `enforced` and `advisory`, then `require`.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import capabilities as cap
from . import paneinput, permissions, skills
from .adapters import codex_option_args
from .capabilities import ADVISORY, ENFORCED, NAMES, Caps
from .paths import XtError

SHORT = {"commands": "cmds", "connectors": "conn", "network": "net", "credential_clis": "creds"}
INDENT = "    "  # status's caps row, under its agent's row
ROW_WIDTH = 76 - len(INDENT)  # 80 columns with 4 to spare
STATUS_WIDTH = ROW_WIDTH - len("caps: ")  # the row after its `caps: ` label


@dataclass
class Plan:
    caps: Caps
    args: list[str] = field(default_factory=list)  # extra harness arguments
    options: list[str] = field(default_factory=list)  # Codex -c options
    settings_file: str | None = None
    settings: permissions.Settings | None = None  # the legacy file, when one applies
    skipped: str = ""  # a team default file not applied (permissions.effective)
    connectors: list[str] = field(default_factory=list)
    row: str = ""  # at STATUS_WIDTH, for the start record and status
    generated: bool = False  # xt wrote the harness settings from the block
    was_loaded: bool = False  # pi had the operator's personal skills before this start (Q3)
    source: str = "none"  # where a settings-file harness gets its rules (see `shown`)
    legacy: list[str] = field(default_factory=list)  # what old lines set (legacy_items)


def legacy_items(ctx, a, adapter) -> list[str]:
    """What the old lines set, for the row (today's `settings:` and `codex options:` lines fold into
    it): the settings file (the agent's own or the team default), Codex's network, the connectors."""
    out = []
    rel = permissions.shown(ctx.team, a, adapter)
    if rel:
        out.append(rel)
    net = _legacy_network(getattr(a, "codex_options", []) or [])
    if net:
        out.append(f"codex network {net}")
    if getattr(a, "connectors", None):
        out.append(f"connectors {', '.join(a.connectors)}")
    return out


SETTINGS_RULES = ("write", "deny", "commands", "credential_clis")  # what only a settings file enforces


def shown(caps: Caps, adapter, source: str = "generated") -> tuple[list[str], list[str]]:
    """(enforced, advisory) capability names for the row. Enforced: those the block changed and the
    harness enforces. Advisory: every one that applies and the harness can't enforce (commands only
    when restricted, connectors only when some are named). `source` is where a settings-file
    harness gets its rules: "generated" from the block, "legacy" from the agent's own file (xt can't
    tell what it enforces, so those aren't listed), or "none" (nothing enforces them: advisory)."""
    enforced, advisory = [], []
    changed = set(caps.changed()) if caps.configured else set()
    file_rules = adapter is not None and bool(adapter.settings_flag)  # claude: rules live in its settings file
    for n in NAMES:
        if n == "commands" and caps.commands is None:
            continue
        if n == "connectors" and not caps.connectors:
            continue
        label = cap.support(adapter, n)
        if file_rules and n in SETTINGS_RULES and source != "generated":
            if source == "legacy":
                continue
            label = ADVISORY
        if label == ADVISORY:
            advisory.append(n)
        elif n in changed:
            enforced.append(n)
    return enforced, advisory


def source_of(ctx, a, adapter, caps: Caps) -> str:
    """"generated" (a [capabilities] block applies), "legacy" (its own or the team's settings file)
    or "none"."""
    if caps.configured:
        return "generated"
    return "legacy" if permissions.shown(ctx.team, a, adapter) else "none"


def row(caps: Caps, adapter, legacy: list[str], name: str, width: int = ROW_WIDTH, was_loaded: bool = False,
        source: str = "generated") -> str:
    """`require write; network enforced; deny, credential_clis advisory` (only deviations), with
    `legacy permissions (deprecated: xt capabilities NAME)` folded in; shorter words before `…`."""
    enforced, advisory = shown(caps, adapter, source)
    enforced = [n for n in enforced if n not in caps.require]  # a required one is enforced: said once

    def text(level: int) -> str:
        w = (lambda ns: ", ".join(SHORT.get(n, n) if level else n for n in ns))
        parts = []
        if caps.require:
            parts.append(f"{cap.REQUIRE} {w(caps.require)}")
        if enforced:
            parts.append(f"{w(enforced)} {ENFORCED}")
        if advisory:
            parts.append(f"{w(advisory)} {ADVISORY}")
        if was_loaded:
            parts.append("skills: none, was loaded")
        if legacy:
            parts.append((f"legacy {', '.join(legacy)} (deprecated: xt capabilities {name})",
                          f"legacy {', '.join(legacy)}, deprecated", f"deprecated {', '.join(legacy)}",
                          "legacy, deprecated")[level])
        return "; ".join(parts) or "defaults"

    for level in (0, 1, 2, 3):  # full words, then shorter names, then shorter notes, then `…`
        t = text(level)
        if len(t) <= width:
            return t
    return t[: width - 1] + "…"


BUILTIN_NOTE = "claude cmds: Claude Code's own read-only commands (date, ls…) run anyway"


def builtin_caveat(caps: Caps, adapter) -> bool:
    """Whether a row's `commands` is Claude's: its allow list covers commands beyond the built-in
    read-only set, which dontAsk lets through (date ran in the live round on rc8)."""
    return (adapter is not None and bool(adapter.settings_flag) and caps.configured and caps.commands is not None
            and cap.support(adapter, "commands") == ENFORCED)


def spawn_sentence(caps: Caps, adapter, source: str = "generated") -> str:
    """The spawn approval's line: `Approve its start: write, network enforced; deny, commands
    advisory (role text only).` (at most two rows of 80 columns)."""
    enforced, advisory = shown(caps, adapter, source)
    parts = []
    if caps.require:
        parts.append(f"{cap.REQUIRE} {', '.join(caps.require)}")
    enforced = [n for n in enforced if n not in caps.require]
    if enforced:
        parts.append(f"{', '.join(enforced)} {ENFORCED}")
    if advisory:
        parts.append(f"{', '.join(advisory)} {ADVISORY} (role text only)")
    return f"Approve its start: {'; '.join(parts) or 'the default capabilities'}."


def _legacy_network(options: list[str]) -> str | None:
    for o in options:
        key, _, value = o.replace(" ", "").partition("=")
        if key == "sandbox_workspace_write.network_access":
            return "on" if value == "true" else "off"
    return None


def team_skill_dirs(ctx) -> list[str]:
    return [str(ctx.paths.root / Path(s["path"]).parent) for s in skills.index(ctx.paths)]


class _New:
    """A hire not yet in team.toml: it gets the team's default capabilities."""

    def __init__(self, name: str, permissions: str | None):
        self.name = name
        self.permissions = permissions


def request_sentence(ctx, name: str, adapter, adapters: dict, own: str | None = None) -> str:
    """For a spawn request: refuses (XtError) a `require` this harness can't enforce, before any
    approval is asked for or anything is stored; else the approval's capability sentence. `own` is
    the permissions file the request names."""
    a = ctx.team.agent(name) or _New(name, own)
    caps = cap.effective(ctx.team, a)
    if caps.configured:
        refused = cap.refusal(name, caps, adapter, adapters)
        if refused:
            raise XtError(refused)
    source = "generated" if caps.configured else "legacy" if (own or permissions.shown(ctx.team, a, adapter)) else "none"
    return spawn_sentence(caps, adapter, source)


def status_row(ctx, a, adapter) -> str | None:
    """`caps: …` for `xt status`: what the agent's last start ran with (or, started by an older xt,
    what its harness enforces of the current settings); nothing for an agent never started."""
    from . import versions

    if not versions.ever_started(ctx, a.name):
        return None
    rec = versions.started_capabilities(ctx, a.name)
    if rec is not None and rec.get("row"):
        return f"caps: {rec['row']}"
    caps = cap.effective(ctx.team, a)
    return (f"caps: {row(caps, adapter, legacy_items(ctx, a, adapter), a.name, STATUS_WIDTH,
                         source=source_of(ctx, a, adapter, caps))}")


def detail_row(ctx, a, adapter) -> str | None:
    """The TUI agent detail's row, in full words (the pane has room): the old settings and Codex
    lines fold into it, as in status (ux on rc6); nothing for an agent never started."""
    from . import versions

    if not versions.ever_started(ctx, a.name):
        return None
    rec = versions.started_capabilities(ctx, a.name) or {}
    caps = cap.effective(ctx.team, a)
    return "caps: " + row(caps, adapter, legacy_items(ctx, a, adapter), a.name, 200,
                          bool(rec.get("skills_were_loaded")), source_of(ctx, a, adapter, caps))


def skills_were_loaded(ctx, a, adapter) -> bool:
    """Card #186 Q3: a pi agent last started by an xt that let it load the operator's personal skills
    (its start record has no capabilities), so this start changes what it has: said once."""
    from . import versions

    rec = versions.load(ctx).get("agents", {}).get(a.name)
    return adapter.name == "pi" and rec is not None and "capabilities" not in rec


def record(p: Plan) -> dict:
    """What the start ran with, for the `versions` start record (old records simply lack it)."""
    return {"configured": p.caps.configured, "row": p.row, "generated": p.generated,
            "require": list(p.caps.require), **({"skills_were_loaded": True} if p.was_loaded else {})}


def plan(ctx, a, adapter, adapters: dict) -> Plan:
    """What the agent starts with; refuses (XtError) before anything runs or is stored."""
    caps = cap.effective(ctx.team, a)
    name = a.name
    p = Plan(caps, connectors=list(a.connectors))
    if caps.configured:
        refused = cap.refusal(name, caps, adapter, adapters)
        if refused:
            raise XtError(refused)
    rel, p.skipped = permissions.effective(ctx.team, a, adapter)  # may refuse a `permissions` line
    p.settings = permissions.preflight(ctx.paths.root, rel) if rel else None  # refuses a bad file
    p.options = codex_option_args(name, a.harness, a.codex_options)  # refuses one off the allowlist (#169)
    data = None
    if caps.configured:
        extra = [c for c in a.connectors if c not in caps.connectors]
        if extra:
            raise XtError(f"{name}: `connectors = {list(a.connectors)}` would loosen the [capabilities] block "
                          f"(connectors = {caps.connectors}); a legacy line may only restrict")
        p.connectors = list(a.connectors) if a.connectors else list(caps.connectors)
        if adapter.name == "codex":
            net = _legacy_network(a.codex_options)
            if net == "on" and caps.network == "off":
                raise XtError(f"{name}: `codex_options = [\"sandbox_workspace_write.network_access=true\"]` would "
                              f"loosen the [capabilities] block (network = \"off\"); a legacy line may only restrict")
            p.options = cap.codex_args(Caps(**{**caps.__dict__, "network": net or caps.network}), ctx.paths.root)
        if caps.extras:  # the block's own extras file wins over a team default settings file
            if not adapter.settings_flag:
                raise XtError(f"{name}: extras = {caps.extras!r} is a Claude Code settings file, and {adapter.name} "
                              f"takes none; remove extras or hire {name} under claude")
            rel = caps.extras
            p.settings = permissions.preflight(ctx.paths.root, rel)  # refuses a bad file
        if adapter.name == "claude":
            if caps.skills:
                raise XtError(f"{name}: claude can't load single personal skills (it starts with all slash "
                              f"skills off); remove skills = {caps.skills} or hire {name} under pi")
            data = cap.claude_rules(name, caps, str(ctx.paths.xt_bin))
            if p.settings:
                data = cap.merge_extras(data, json.loads(p.settings.path.read_text()), rel)
            p.generated = True
    if adapter.name == "pi":  # card #186 Q3: no personal skills for any team agent; the team's are kept
        p.args += cap.pi_skill_args(caps, team_skill_dirs(ctx))
    p.settings_file = str(p.settings.path) if p.settings else None
    if a.role == "liaison" and adapter.name in paneinput.HOOKED:  # card #193: its settings plus the prompt hook
        p.settings_file = paneinput.hook_settings(ctx, name, rel if p.settings and data is None else None, data)
    elif data is not None:
        out = ctx.paths.state / "settings" / f"{name}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=1))
        p.settings_file = str(out)
    p.was_loaded = skills_were_loaded(ctx, a, adapter)
    p.source = "generated" if p.generated else "legacy" if p.settings else "none"
    p.legacy = legacy_items(ctx, a, adapter)
    p.row = row(caps, adapter, p.legacy, name, STATUS_WIDTH, p.was_loaded, p.source)
    return p
