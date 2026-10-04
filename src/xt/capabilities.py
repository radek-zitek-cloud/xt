"""Card #186: one capability model across harnesses.

A `[capabilities]` block per agent (`[agent.capabilities]`), with a team default
(`[defaults.capabilities]`), says what the agent may do in one vocabulary, whatever its harness:

- `write`: paths it may change (its own `members/<name>/` always); `deny`: paths it must never
  touch (the team's settings, `team.toml` and xt's own code always);
- `commands`: the commands it may run (unset: not restricted); `network`: `off` or `on`;
- `connectors`: named account connectors; `skills`: the operator's personal skills, `none` or names;
- `credential_clis`: command-line tools that hold the operator's credentials, denied by name
  (xt's list plus `deny`, less named `allow` exceptions);
- `require`: capabilities that must be enforced, or the start is refused.

This module parses and checks the blocks (at load, through `Team.check`) and works out an agent's
effective set: the team default, then the agent's block (key by key), with `require` from both.
Legacy lines (`permissions`, `codex_options`, `connectors`) keep working beside a team default;
an agent's own block beside its own legacy line is refused.
"""

import re
from dataclasses import dataclass, field

from .paths import XtError

NAMES = ("write", "deny", "commands", "network", "connectors", "skills", "credential_clis")
LEGACY = ("permissions", "codex_options", "connectors")
NETWORK = ("off", "on")
# command-line tools known to hold the operator's credentials (card #126)
CREDENTIAL_CLIS = ("gh", "glab", "aws", "gcloud", "az", "kubectl", "op", "bw", "fizzy", "doctl", "flyctl",
                   "heroku", "netlify", "vercel", "wrangler")
ALWAYS_DENIED = ("team.toml", "settings/", "bin/", "src/", "harnesses/", "protocol.md")


@dataclass
class Caps:
    """An agent's effective capabilities."""
    write: list[str] = field(default_factory=list)  # besides its own members/<name>/
    deny: list[str] = field(default_factory=list)  # besides ALWAYS_DENIED
    commands: list[str] | None = None  # None: not restricted
    network: str = "off"
    connectors: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)  # [] = none
    credential_clis: list[str] = field(default_factory=lambda: list(CREDENTIAL_CLIS))  # denied
    require: list[str] = field(default_factory=list)
    configured: bool = False  # a [capabilities] block applies (the agent's own or the team's)
    extras: str | None = None  # a Claude Code settings file merged on top, restricting only

    def changed(self) -> list[str]:
        """The capabilities that deviate from the defaults, in NAMES order (for the compact row)."""
        base = Caps()
        return [n for n in NAMES if getattr(self, n) != getattr(base, n)]


def _strings(value, key: str, where: str) -> list[str]:
    if isinstance(value, str) or not isinstance(value, list) or not all(isinstance(v, str) and v.strip()
                                                                         for v in value):
        raise XtError(f"{where} capabilities.{key} = {value!r} in team.toml isn't a list of names "
                      f"(e.g. {key} = [\"…\"])")
    return [str(v).strip() for v in value]


def parse(block, where: str) -> dict:
    """The block's settings as plain values; refuses unknown keys and bad values, naming them."""
    if not isinstance(block, dict):
        raise XtError(f"{where} capabilities in team.toml must be a table ([… .capabilities])")
    out: dict = {}
    for key, value in block.items():
        if key == "require":
            names = _strings(value, key, where)
            bad = [n for n in names if n not in NAMES]
            if bad:
                raise XtError(f"{where} capabilities.require names {', '.join(bad)}, which isn't a capability "
                              f"({', '.join(NAMES)})")
            out[key] = names
        elif key == "network":
            if value not in NETWORK:
                raise XtError(f"{where} capabilities.network = {value!r} in team.toml must be \"off\" or \"on\"")
            out[key] = str(value)
        elif key == "skills":
            out[key] = [] if value == "none" else _strings(value, key, where)
        elif key == "credential_clis":
            if isinstance(value, dict):
                unknown = [k for k in value if k not in ("allow", "deny")]
                if unknown:
                    raise XtError(f"{where} capabilities.credential_clis takes `allow` and `deny` lists, "
                                  f"not {', '.join(unknown)}")
                out[key] = {k: _strings(v, f"credential_clis.{k}", where) for k, v in value.items()}
            else:
                out[key] = {"deny": _strings(value, key, where)}
        elif key in ("write", "deny", "commands", "connectors"):
            out[key] = _strings(value, key, where)
        elif key == "extras":  # a Claude Code settings file on top, which may only restrict
            if not isinstance(value, str) or not value.strip():
                raise XtError(f"{where} capabilities.extras = {value!r} in team.toml must be a settings file "
                              f"path in the team repo (e.g. extras = \"settings/carol.json\")")
            out[key] = str(value).strip()
        else:
            raise XtError(f"{where} capabilities.{key} in team.toml isn't a capability "
                          f"({', '.join(NAMES)}, and require and extras)")
    return out


def check(doc) -> list[str]:
    """Problems with every capability block and with mixing, for `Team.check`."""
    problems = []
    defaults = doc.get("defaults", {}).get("capabilities")
    if defaults is not None:
        try:
            parse(defaults, "[defaults]")
        except XtError as e:
            problems.append(str(e))
    for a in doc.get("agent", []):
        if "capabilities" not in a:
            continue
        where = f"agent {a.get('name')}'s"
        try:
            parse(a["capabilities"], where)
        except XtError as e:
            problems.append(str(e))
            continue
        legacy = [k for k in LEGACY if a.get(k)]
        if legacy:
            problems.append(mixing_text(str(a.get("name")), legacy))
    return problems


def mixing_text(name: str, legacy: list[str]) -> str:
    lines = " and ".join(f"`{k} = …`" for k in legacy)
    return (f"agent {name} has both a [capabilities] block and {lines} in team.toml: use one. "
            f"`xt capabilities {name}` prints the block equivalent to the old lines")


def _apply(caps: Caps, settings: dict) -> None:
    for key, value in settings.items():
        if key == "require":
            caps.require = sorted(set(caps.require) | set(value), key=NAMES.index)
        elif key == "credential_clis":
            denied = [c for c in caps.credential_clis if c not in value.get("allow", [])]
            caps.credential_clis = denied + [c for c in value.get("deny", []) if c not in denied]
        else:
            setattr(caps, key, list(value) if isinstance(value, list) else value)


ENFORCED, ADVISORY, REQUIRE = "enforced", "advisory", "require"  # the three words, on every surface


def support(adapter, name: str) -> str:
    """`enforced` when the harness's adapter declares it enforces this capability, else `advisory`."""
    return ENFORCED if adapter is not None and adapter.capabilities.get(name) == ENFORCED else ADVISORY


def refusal(agent: str, caps: Caps, adapter, adapters: dict) -> str | None:
    """Why a start is refused: a `require`d capability this harness can only treat as advisory. It
    names the capability, the harness and the nearest enforceable configuration; None to start."""
    harness = adapter.name if adapter is not None else "?"
    for name in caps.require:
        if support(adapter, name) == ENFORCED:
            continue
        others = sorted(h for h, a in adapters.items() if h != harness and support(a, name) == ENFORCED)
        hire = f", or hire {agent} under {' or '.join(others)}" if others else ""
        return (f"{agent} can't start: {name} is marked require, and {harness} can only keep it advisory "
                f"(role text only). Drop require on {name}{hire}")
    return None


# --- what each adapter generates (card #186; the support tables are in harnesses/*.toml) ------------

# Claude Code tools an agent needs that change nothing; under dontAsk anything not allowed is refused
CLAUDE_READ_TOOLS = ("Read", "Glob", "Grep", "TodoWrite")


def claude_path(p: str) -> str:
    """A path in Claude Code's rule syntax, for everything under it: `//abs/**`, `~/x/**`, `rel/**`."""
    p = p.rstrip("/") or "/"
    if p.startswith("/"):
        p = "/" + p
    return f"{p}/**" if not p.endswith("**") else p


def claude_rules(name: str, caps: Caps, xt_bin: str) -> dict:
    """The generated Claude Code settings for an agent with a [capabilities] block. What it truly
    enforces: file edits only under `write` (and the agent's notes), nothing under `deny`; shell
    commands only from `commands` (when set) and never a credential CLI, by name; WebFetch and
    WebSearch only with network on. A command it may run can still reach the network: that limit
    is by name, not isolation."""
    allow = list(CLAUDE_READ_TOOLS) + [f"Edit({claude_path(p)})" for p in [f"members/{name}/", *caps.write]]
    deny = [f"Edit({claude_path(p)})" for p in ALWAYS_DENIED if p.endswith("/")]
    deny += [f"Edit({p})" for p in ALWAYS_DENIED if not p.endswith("/")]
    for p in caps.deny:
        deny += [f"Read({claude_path(p)})", f"Edit({claude_path(p)})"]
    if caps.commands is None:
        allow.append("Bash")
    else:
        # xt in every spelling agents use (the reply hint's absolute path, bin/xt and ./bin/xt from the
        # team repo, xt on PATH), and cd, so `cd <repo> && xt …` passes too (live round on rc8)
        for x in (xt_bin, "bin/xt", "./bin/xt", "xt", "cd"):
            allow += [f"Bash({x} *)", f"Bash({x})"]
        for c in caps.commands:
            allow += [f"Bash({c} *)", f"Bash({c})"]
    for c in caps.credential_clis:
        deny += [f"Bash({c} *)", f"Bash({c})"]
    web = ["WebFetch", "WebSearch"]
    (allow if caps.network == "on" else deny).extend(web)
    allow += [f"mcp__{re.sub(r'[^A-Za-z0-9_-]', '_', c)}" for c in caps.connectors]  # adapters.tool_prefix
    return {"permissions": {"defaultMode": "dontAsk", "allow": allow, "deny": deny}}


def _covers(rule: str, rules: list[str]) -> bool:
    return rule in rules


def merge_extras(generated: dict, extras: dict, where: str) -> dict:
    """The legacy settings file as extras on top of the generated settings: it may add deny and ask
    rules and other keys, and allow rules the generated set allows anyway; a rule or mode that would
    loosen the generated restrictions is refused, naming both."""
    gen = generated["permissions"]
    perms = extras.get("permissions", {}) if isinstance(extras.get("permissions"), dict) else {}
    mode = perms.get("defaultMode")
    if mode not in (None, "dontAsk"):
        raise XtError(f"{where}: permissions.defaultMode {mode!r} would loosen the [capabilities] block's "
                      f"generated `dontAsk`; remove it from {where}")
    for rule in perms.get("allow", []):
        if _covers(rule, gen["deny"]):
            raise XtError(f"{where}: allow rule {rule!r} would loosen the [capabilities] block, which "
                          f"denies {rule!r}; remove it from {where} or change the block")
        if not (_covers(rule, gen["allow"]) or _contained(rule, gen["allow"])):
            raise XtError(f"{where}: allow rule {rule!r} is outside what the [capabilities] block allows; "
                          f"add it to the block (write, commands, network, connectors) or remove it from {where}")
    out = {k: v for k, v in extras.items() if k != "permissions"}
    out.update({k: v for k, v in generated.items() if k != "permissions"})
    out["permissions"] = {**{k: v for k, v in perms.items() if k not in ("allow", "deny", "ask")},
                          "defaultMode": "dontAsk",
                          "allow": gen["allow"] + [r for r in perms.get("allow", []) if r not in gen["allow"]],
                          "deny": gen["deny"] + [r for r in perms.get("deny", []) if r not in gen["deny"]],
                          **({"ask": list(perms["ask"])} if perms.get("ask") else {})}
    return out


GOVERNED = ("Edit", "Write", "MultiEdit", "NotebookEdit", "Bash", "WebFetch", "WebSearch")  # by the block


def _contained(rule: str, allow: list[str]) -> bool:
    """An extras allow rule inside what the block allows: `Edit(//a/b/**)` under `Edit(//a/**)`,
    any `Bash(…)` when the shell is open, `Bash(git status)` or `Bash(git:*)` under `Bash(git *)`,
    xt itself however it's spelled, an `mcp__` tool of a named connector, and any tool the block
    doesn't govern (Read, Task, …: allowing it loosens nothing the block restricts)."""
    tool, _, spec = rule.partition("(")
    spec = spec.rstrip(")")
    if spec.endswith(":*"):
        spec = spec[:-2] + " *"
    if tool.startswith("mcp__"):
        return any(a.startswith("mcp__") and (tool == a or tool.startswith(a + "__")) for a in allow)
    if tool not in GOVERNED or (tool == "Bash" and "Bash" in allow):
        return True
    if tool == "Bash" and spec and spec.split()[0].rsplit("/", 1)[-1] == "xt":
        return True  # every agent may run xt; the generated rule uses its absolute path
    for a in allow:
        atool, _, aspec = a.partition("(")
        aspec = aspec.rstrip(")")
        if atool != tool or not aspec:
            continue
        if aspec.endswith("/**") and spec.startswith(aspec[:-2]):
            return True
        if aspec.endswith(" *") and (spec == aspec[:-2] or spec.startswith(aspec[:-1])):
            return True
    return False


def resolve(p: str, root) -> str:
    """A capability path as an absolute path (for harness flags)."""
    from pathlib import Path

    q = Path(p).expanduser()
    return str(q if q.is_absolute() else Path(root) / q)


def codex_args(caps: Caps, root) -> list[str]:
    """Codex start arguments: the workspace-write sandbox (the only mode in which the network switch
    and extra writable roots apply: without it, codex-cli 0.160.0 in a folder it doesn't trust yet
    exits 1 on `--add-dir`; live round on rc8), its network switch, and each `write` path as
    `--add-dir` (plain paths, nothing for Herdr's shell to quote)."""
    args = ["-s", "workspace-write",
            "-c", f"sandbox_workspace_write.network_access={'true' if caps.network == 'on' else 'false'}"]
    for p in caps.write:
        args += ["--add-dir", resolve(p, root)]
    return args


PI_SKILL_DIRS = ("~/.pi/agent/skills", "~/.agents/skills")  # where pi's personal skills live (1.0.2)


def pi_skill_args(caps: Caps, team_skills: list[str]) -> list[str]:
    """pi without the operator's personal skills (`--no-skills`), the team's own skills passed back
    one by one, and each named personal skill from the first folder that has it."""
    from pathlib import Path

    args = ["--no-skills"]
    for d in team_skills:
        args += ["--skill", d]
    for name in caps.skills:
        found = next((Path(d).expanduser() / name for d in PI_SKILL_DIRS if (Path(d).expanduser() / name).is_dir()),
                     None)
        if found is None:
            raise XtError(f"skill {name!r} isn't a personal skill pi can load (looked in {', '.join(PI_SKILL_DIRS)})")
        args += ["--skill", str(found)]
    return args


def convert(agent, settings: dict | None, rel: str | None) -> str:
    """`xt capabilities NAME`: the [capabilities] block equivalent to the agent's legacy lines and
    settings file, as TOML for review. It changes nothing; what the vocabulary can't say is listed as
    "kept in extras" (it stays in the file, which then restricts on top of the block)."""
    block: dict = {}
    kept: list[str] = []
    perms = (settings or {}).get("permissions", {}) if isinstance((settings or {}).get("permissions"), dict) else {}
    write, deny, commands, open_shell, clis_allowed, connectors_seen = [], [], [], False, [], []
    loosen: list[str] = []  # what the extras file has that the block would refuse at start
    for rule in perms.get("allow", []):
        tool, _, spec = str(rule).partition("(")
        spec = spec.rstrip(")")
        if tool in ("Edit", "Write") and spec:
            p = spec[1:] if spec.startswith("//") else spec
            p = p[:-3] if p.endswith("/**") else p
            if p != f"members/{agent.name}":
                write.append(p)
        elif tool == "Bash" and not spec:
            open_shell = True
        elif tool == "Bash":
            cmd = spec[:-2] if spec.endswith(" *") else spec[:-2] if spec.endswith(":*") else spec
            if cmd.split()[0] in CREDENTIAL_CLIS:
                clis_allowed.append(cmd.split()[0])
            elif "xt" != cmd.rsplit("/", 1)[-1] and cmd not in commands:
                commands.append(cmd)
        elif tool in ("WebFetch", "WebSearch"):
            block["network"] = "on"
        elif tool in CLAUDE_READ_TOOLS or tool == "Read":
            continue  # reading is allowed under the block anyway
        elif tool.startswith("mcp__"):
            connectors_seen.append(tool)
        else:
            kept.append(f"allow {rule}")  # a tool the block doesn't govern: stays in extras
    for rule in perms.get("deny", []):
        tool, _, spec = str(rule).partition("(")
        spec = spec.rstrip(")")
        if tool in ("Edit", "Read", "Write") and spec:
            p = spec[1:] if spec.startswith("//") else spec
            p = p[:-3] if p.endswith("/**") else p
            if p.rstrip("/") + ("/" if spec.endswith("/**") else "") not in ALWAYS_DENIED and p not in deny:
                deny.append(p)
        elif tool == "Bash" and spec and spec.split()[0].rstrip(":*") in CREDENTIAL_CLIS:
            continue  # denied by default
        elif tool in ("WebFetch", "WebSearch"):
            continue  # network is off by default
        else:
            kept.append(f"deny {rule}")
    for rule in perms.get("ask", []):
        kept.append(f"ask {rule}")
    if perms.get("defaultMode") not in (None, "dontAsk"):
        loosen.append(f"defaultMode {perms['defaultMode']} (the block's settings use dontAsk)")
    kept += [f"key {k}" for k in (settings or {}) if k != "permissions"]
    connectors = list(getattr(agent, "connectors", None) or [])
    prefixes = {"mcp__" + re.sub(r"[^A-Za-z0-9_-]", "_", c) for c in connectors}
    for tool in connectors_seen:
        if any(tool == p or tool.startswith(p + "__") for p in prefixes):
            kept.append(f"allow {tool}")  # covered by its named connector
        else:
            loosen.append(f"allow {tool} (a connector the block doesn't name: add it to connectors)")
    if write:
        block["write"] = write
    if deny:
        block["deny"] = deny
    if commands and not open_shell:
        block["commands"] = commands
    if clis_allowed:
        block["credential_clis"] = {"allow": sorted(set(clis_allowed))}
    for o in getattr(agent, "codex_options", []) or []:
        if o.replace(" ", "") == "sandbox_workspace_write.network_access=true":
            block["network"] = "on"
    if connectors:
        block["connectors"] = connectors
    if (kept or loosen) and rel:
        block["extras"] = rel  # the file stays, on top of the block, for what the block can't say
    import tomlkit

    lines = [f"# xt capabilities {agent.name}: the block equivalent to its legacy lines"
             + (f" and {rel}" if rel else "") + " (nothing was changed).",
             f"# Under its [[agent]] entry (name = \"{agent.name}\"), replacing "
             + " and ".join(f"`{k}`" for k in LEGACY if getattr(agent, k, None)) + ":",
             "[agent.capabilities]"]
    lines += tomlkit.dumps(block).strip().splitlines() if block else ["# (the defaults: nothing to set)"]
    if kept:
        lines.append(f"# kept in extras ({rel}: the block can't say these, so `extras` keeps the file "
                     f"on top, where it may only restrict):")
        lines += [f"#   {k}" for k in kept]
    if loosen:
        lines.append(f"# would loosen the block, so the start refuses them until they are removed from {rel}:")
        lines += [f"#   {k}" for k in loosen]
    return "\n".join(lines)


def effective(team, agent) -> Caps:
    """The agent's capabilities: defaults, then `[defaults.capabilities]`, then its own block."""
    caps = Caps()
    defaults = team.doc.get("defaults", {}).get("capabilities")
    own = team.capabilities_block(agent.name) if agent is not None else None
    for block in (defaults, own):
        if block is not None:
            _apply(caps, parse(block, ""))
            caps.configured = True
    return caps
