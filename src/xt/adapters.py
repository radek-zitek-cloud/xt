"""Harness adapters: `harnesses/<kind>.toml` declares how xt starts an agent in that harness."""

import json
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field

from .paths import Paths, XtError


@dataclass
class Adapter:
    name: str
    herdr_kind: str
    binary: str
    args: list[str] = field(default_factory=list)
    model_flag: str | None = None
    summary: str = ""
    limits: list[str] = field(default_factory=list)
    # Dialogs the harness may show before it takes input: [{"match": [...], "keys": [...]}]
    startup_dialogs: list[dict] = field(default_factory=list)
    # Where the harness keeps its session logs (a glob, ~ allowed) and their format, so xt can
    # read an agent's context usage; windows for models whose logs don't state it.
    sessions: str | None = None
    session_format: str | None = None
    context_windows: dict[str, int] = field(default_factory=dict)
    # Desktop/browser control for agents (card #89): "blocked" (switched off by the args), "none"
    # (the harness has no such tools), "partial" or unset (not fully enforced: xt says so at start).
    desktop_tools: str | None = None
    desktop_tools_note: str = ""
    # The operator's account connectors (mail, files, calendar…; card #101): "blocked", "none" or
    # "partial"; the args that block them unless an agent opts in, and how an opt-in works.
    connectors: str | None = None
    connectors_note: str = ""
    connector_block_args: list[str] = field(default_factory=list)
    connector_style: str | None = None  # "claude-mcp" (named opt-in possible) or None (no opt-in)
    # The flag that passes a settings file (per-agent permissions, card #117); None = not supported.
    settings_flag: str | None = None
    # Readiness before the first prompt (card #167): Herdr can report the harness started before it
    # takes input. With `ready_settle = N`, xt waits until the screen stays unchanged for N checks a
    # second apart; with `check_prompt_in_log`, it checks the session log for the prompt's opening.
    ready_settle: int = 0
    check_prompt_in_log: bool = False

    @property
    def installed(self) -> bool:
        return shutil.which(self.binary) is not None

    def start_args(self, model: str | None, connectors: list[str] | None = None, cwd: str | None = None,
                   settings: str | None = None) -> list[str]:
        """The harness's command-line arguments. Without `connectors`, the operator's account
        connectors are blocked; with them, only those connectors are exposed. `settings` is a
        checked settings file (card #117)."""
        args = list(self.args)
        if settings:
            if not self.settings_flag:
                raise XtError(f"harness {self.name} takes no settings file")
            args += [self.settings_flag, settings]
        if not connectors:
            args += self.connector_block_args
        elif self.connector_style == "claude-mcp":
            others = [s for s in claude_mcp_servers(self.binary, cwd) if s not in connectors]
            if others:
                args += ["--disallowedTools", *(f"mcp__{tool_prefix(s)}" for s in others)]
        else:
            # Only an adapter that can expose exactly the named connectors takes an opt-in: Codex
            # can switch its apps on only as a whole (card #101, found in acceptance).
            raise XtError(f"harness {self.name} can't expose single account connectors, so it takes no "
                          f"`connectors` opt-in (asked for: {', '.join(connectors)}); use a harness "
                          f"that can (claude) for that agent, or remove the line")
        if model:
            if not self.model_flag:
                raise XtError(f"harness {self.name} has no model flag declared; leave the model empty")
            args += [self.model_flag, model]
        return args


def tool_prefix(server: str) -> str:
    """How Claude Code names a server's tools: `claude.ai Gmail` -> mcp__claude_ai_Gmail__…"""
    return re.sub(r"[^A-Za-z0-9_-]", "_", server)


def claude_mcp_servers(binary: str = "claude", cwd: str | None = None, timeout: int = 90) -> list[str]:
    """Every MCP server a Claude Code session here would load, read from its start-up record. The
    process is stopped right after that record, before any model call, so it costs nothing."""
    p = subprocess.Popen([binary, "--output-format", "stream-json", "--verbose", "-p", "ok"], cwd=cwd,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True)
    try:
        for line in p.stdout:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("type") == "system" and d.get("subtype") == "init":
                return [s["name"] for s in d.get("mcp_servers", [])]
        raise XtError("couldn't read Claude Code's MCP servers (no start-up record)")
    finally:
        p.kill()


def load_adapters(paths: Paths) -> dict[str, Adapter]:
    out = {}
    for f in sorted(paths.harnesses.glob("*.toml")):
        d = tomllib.loads(f.read_text())
        out[f.stem] = Adapter(
            name=f.stem,
            herdr_kind=d.get("herdr_kind", f.stem),
            binary=d.get("binary", f.stem),
            args=list(d.get("args", [])),
            model_flag=d.get("model_flag"),
            summary=d.get("summary", ""),
            limits=list(d.get("limits", [])),
            startup_dialogs=[
                {
                    "match": [dlg["match"]] if isinstance(dlg["match"], str) else list(dlg["match"]),
                    "keys": list(dlg.get("keys", ["enter"])),
                    "name": dlg.get("name", dlg["match"] if isinstance(dlg["match"], str) else dlg["match"][0]),
                }
                for dlg in d.get("startup_dialogs", [])
            ],
            sessions=d.get("sessions"),
            session_format=d.get("session_format"),
            context_windows={k: int(v) for k, v in d.get("context_windows", {}).items()},
            desktop_tools=d.get("desktop_tools"),
            desktop_tools_note=d.get("desktop_tools_note", ""),
            connectors=d.get("connectors"),
            connectors_note=d.get("connectors_note", ""),
            connector_block_args=list(d.get("connector_block_args", [])),
            connector_style=d.get("connector_style"),
            settings_flag=d.get("settings_flag"),
            ready_settle=int(d.get("ready_settle", 0)),
            check_prompt_in_log=bool(d.get("check_prompt_in_log", False)),
        )
    return out


def get_adapter(paths: Paths, harness: str) -> Adapter:
    adapters = load_adapters(paths)
    if harness not in adapters:
        raise XtError(f"no adapter for harness {harness!r} (have: {', '.join(adapters) or 'none'})")
    a = adapters[harness]
    if not a.installed:
        raise XtError(f"harness {harness!r} isn't installed here (`{a.binary}` not on PATH)")
    return a
