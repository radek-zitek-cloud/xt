"""Claude Code settings files in the team repo (card #117): the check before a start.

A [capabilities] block's `extras = "settings/carol.json"` (card #186) puts such a file on top of the
settings xt generates. xt checks the file before the start, because Claude Code (2.1.284) silently
ignores a malformed file, an unknown `defaultMode` or a broken rule and starts anyway. Other settings
keys are passed through unchecked; Claude Code owns its schema. Settings files are the human's, like
team.toml: an agent that could edit its own file could widen its own permissions. (The older
`permissions` line in team.toml was removed in 0.24, card #218.)"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .paths import XtError

MODES = ("default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions", "manual")
RULE_LISTS = ("allow", "deny", "ask")
RULE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*(?:\((.*)\))?", re.S)  # Tool or Tool(specifier)


@dataclass
class Settings:
    rel: str  # as written in team.toml
    path: Path  # resolved, inside the team repo
    digest: str  # short sha256 of the content used for this start
    mode: str | None  # permissions.defaultMode, if set


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
    """The start's note on the extras file (a mode other than dontAsk is refused before it, by
    capabilities.merge_extras)."""
    return (f"{name}: Claude Code settings {s.rel} (sha256 {s.digest}, "
            f"permissions.defaultMode {s.mode or 'not set'})")
