"""Per-agent permission settings for Claude Code agents (card #117).

`permissions = "settings/liaison.json"` on an `[[agent]]` in team.toml (or once in `[defaults]` for
every Claude agent) passes that file to Claude Code with `--settings`. xt checks the file before the
start, because Claude Code (2.1.284) silently ignores a malformed file, an unknown `defaultMode` or a
broken rule and starts anyway: with no permission rules an unattended agent stops at the first
prompt nobody sees. Other settings keys are passed through unchecked; Claude Code owns its schema.
Settings files are the human's, like team.toml: an agent that could edit its own file could widen
its own permissions."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .paths import XtError

MODES = ("default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions", "manual")
PERMISSIVE = ("bypassPermissions", "acceptEdits")  # act without asking: the start note warns
RULE_LISTS = ("allow", "deny", "ask")
RULE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*(?:\((.*)\))?", re.S)  # Tool or Tool(specifier)


@dataclass
class Settings:
    rel: str  # as written in team.toml
    path: Path  # resolved, inside the team repo
    digest: str  # short sha256 of the content used for this start
    mode: str | None  # permissions.defaultMode, if set


def effective(team, agent, adapter) -> tuple[str | None, str]:
    """The settings file an agent starts with, and a note when a team default doesn't apply.

    An agent's own line wins; a harness that takes no settings file refuses it. The `[defaults]`
    value applies to agents whose harness takes one and is skipped (with a note) for the others,
    so a team default for its Claude agents doesn't stop its Codex agents from starting."""
    if agent.permissions:
        if not adapter.settings_flag:
            raise XtError(f"{agent.name}: harness {adapter.name} takes no settings file, so it takes no "
                          f"`permissions` line (asked for: {agent.permissions}); use claude for that agent "
                          f"or remove the line")
        return agent.permissions, ""
    default = team.default_permissions
    if not default:
        return None, ""
    if adapter.settings_flag:
        return default, ""
    return None, f"{agent.name}: team default permissions file {default} not applied ({adapter.name} takes no settings file)"


def shown(team, agent, adapter) -> str | None:
    """The effective settings path for status and detail views (never raises)."""
    if agent.permissions:
        return agent.permissions
    return team.default_permissions if adapter and adapter.settings_flag else None


def _rule_ok(rule) -> bool:
    if not isinstance(rule, str):
        return False
    m = RULE.fullmatch(rule.strip())
    if not m:
        return False
    depth = 0
    for ch in m.group(1) or "":
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if depth < 0:
            return False
    return depth == 0


def preflight(root: Path, rel: str) -> Settings:
    """Check a settings file before the harness starts; refuse with the reason."""
    where = f"permissions file {rel!r}"
    p = Path(rel)
    if p.is_absolute():
        raise XtError(f"{where}: must be a path inside the team repo, relative to it")
    if ".." in p.parts:
        raise XtError(f"{where}: `..` isn't allowed; keep settings files inside the team repo")
    top = root.resolve()
    full = (root / p).resolve()
    if not full.is_relative_to(top):
        raise XtError(f"{where}: resolves outside the team repo ({full}); a symlink out isn't allowed")
    if not full.exists():
        raise XtError(f"{where}: no such file in the team repo")
    if not full.is_file():
        raise XtError(f"{where}: not a regular file")
    try:
        raw = full.read_bytes()
    except OSError as e:
        raise XtError(f"{where}: can't read it ({e.strerror})") from None
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise XtError(f"{where}: not valid JSON ({e})") from None
    if not isinstance(data, dict):
        raise XtError(f"{where}: must be a JSON object (Claude Code settings)")
    perms = data.get("permissions", {})
    if not isinstance(perms, dict):
        raise XtError(f"{where}: `permissions` must be an object")
    mode = perms.get("defaultMode")
    if mode is not None and mode not in MODES:
        raise XtError(f"{where}: unknown permissions.defaultMode {mode!r} (Claude Code would ignore it); "
                      f"use one of {', '.join(MODES)}")
    for key in RULE_LISTS:
        rules = perms.get(key)
        if rules is None:
            continue
        if not isinstance(rules, list):
            raise XtError(f"{where}: permissions.{key} must be a list of rules")
        bad = [r for r in rules if not _rule_ok(r)]
        if bad:
            raise XtError(f"{where}: malformed permissions.{key} rule(s) {bad!r} (Claude Code would ignore "
                          f"them); a rule is a tool name, optionally with one (…) specifier")
    return Settings(rel=rel, path=full, digest=hashlib.sha256(raw).hexdigest()[:12], mode=mode)


def start_note(name: str, s: Settings) -> str:
    note = (f"{name}: Claude Code settings {s.rel} (sha256 {s.digest}, "
            f"permissions.defaultMode {s.mode or 'not set'})")
    if s.mode in PERMISSIVE:
        note += (f" — WARNING: {s.mode} lets {name} "
                 + ("run any tool without asking" if s.mode == "bypassPermissions" else "edit files without asking"))
    return note
