"""Is each running agent the process xt started, with xt's launch settings? (card #165)

xt starts an agent by exporting XT_AGENT=<name> in a fresh pane and then starting the harness with
its model, settings file and connector and tool blocks. A terminal multiplexer that restores its
session after a power cycle resumes the agents with a plain resume command instead: same names, same
panes, none of those settings, and no XT_AGENT. So the signal is the identity variable in the live
harness process's environment, read from /proc: a harness process (its program is claude, codex or
pi, as for the identity guard) whose working directory is the team repo and whose environment has
XT_AGENT=<name> means xt started that agent. Herdr's agent list gives no process id, and a restored
process keeps no id xt recorded, so xt looks for the variable rather than for a known process.

A warning needs positive evidence (rc5, from the rc2 and rc4 staging): a visible harness process in
the team repo without XT_AGENT, of the agent's harness. Herdr-live agents with no matching XT_AGENT
process are warned about only when there are at least as many such processes of their harness as
there are such agents (a restore resumes them all); otherwise xt can't tell which process is whose.
An agent whose process simply isn't visible (a sandbox shows a few processes, possibly another
agent's with its own XT_AGENT) is "not checked", and so is one when a harness process of its kind
can't be read: never a match and never a warning, and no alert changes because of it.
"""

import os
from dataclasses import dataclass, field

from .alerts import Alerts
from .context import Ctx

PROC = "/proc"
STARTED, MISSING, UNCHECKED = "started by xt", "without xt's launch settings", "not checked"
ALERT = "launch:"  # alert key prefix, one per agent
HARNESSES = ("claude", "codex", "pi")  # the programs the identity guard knows (cli.HARNESS_BINARIES)


@dataclass
class Scan:
    names: set[str]  # XT_AGENT values of the team's harness processes
    whole: str | None = None  # why nothing could be looked at (a sandbox's PID namespace, no /proc)
    unlaunched: dict[str, int] = field(default_factory=dict)  # harness -> its processes without XT_AGENT
    unreadable: dict[str, str] = field(default_factory=dict)  # harness -> why one couldn't be read


ISOLATED = "xt runs in a PID namespace here (a sandbox?), so the agents' processes aren't visible"
INVISIBLE = "its process isn't visible from here (a sandbox?)"


def isolated(proc: str | None = None) -> bool:
    """Whether this process sits in a nested PID namespace, as in some sandboxes: /proc then shows
    only the namespace's few processes, so an agent's absence there says nothing (rc2 staging)."""
    try:
        with open(f"{proc or PROC}/self/status") as fh:
            for line in fh:
                if line.startswith("NSpid:"):
                    return len(line.split()) > 2  # one pid per namespace level
    except OSError:
        pass
    return False


def _names(pid_dir: str) -> set[str]:
    comm = open(f"{pid_dir}/comm").read().strip()
    argv = open(f"{pid_dir}/cmdline", "rb").read().split(b"\0")
    return {comm, *(os.path.basename(a.decode(errors="replace")) for a in argv[:2] if a)}


def _harness(names: set[str]) -> str | None:
    return next((h for h in HARNESSES for n in names if n == h or n.startswith(h + "-")), None)


def scan_proc(root: str, proc: str | None = None) -> Scan:
    """What the harness processes working in the team repo `root` carry: their XT_AGENT values, and
    per harness how many have none or couldn't be read."""
    proc = proc or PROC
    if isolated(proc):
        return Scan(set(), ISOLATED)
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError as e:
        return Scan(set(), f"can't list processes ({e.strerror or e})")
    s = Scan(set())
    real_root = os.path.realpath(root)
    for pid in pids:
        d = f"{proc}/{pid}"
        try:
            harness = _harness(_names(d))
        except (OSError, ValueError):
            continue  # gone meanwhile, or not a process
        if harness is None:
            continue
        try:
            cwd = os.path.realpath(os.readlink(f"{d}/cwd"))
        except OSError:
            cwd = None  # unknown: it may belong to this team
        if cwd is not None and cwd != real_root:
            continue  # another team's or the human's own harness
        try:
            env = open(f"{d}/environ", "rb").read()
        except PermissionError:
            s.unreadable[harness] = f"no permission to read process {pid}'s environment"
            continue
        except OSError:
            continue
        agent = next((v[len(b"XT_AGENT="):].decode(errors="replace") for v in env.split(b"\0")
                      if v.startswith(b"XT_AGENT=")), None)
        if agent is None:
            s.unlaunched[harness] = s.unlaunched.get(harness, 0) + 1
        else:
            s.names.add(agent)  # whoever it is: never evidence against another agent
    return s


scan = scan_proc  # tests replace this (they run no real agents)


def check(ctx: Ctx, live: dict) -> dict[str, tuple[str, str]]:
    """name -> (STARTED | MISSING | UNCHECKED, detail) for each running agent of the roster."""
    agents = [a for a in ctx.team.agents() if a.kind != "human" and a.name in live]
    if not agents:
        return {}
    s = scan(str(ctx.paths.root))
    out: dict[str, tuple[str, str]] = {}
    unmatched: dict[str, list[str]] = {}
    for a in agents:
        if a.name in s.names:
            out[a.name] = (STARTED, "")
        elif s.whole:
            out[a.name] = (UNCHECKED, s.whole)
        else:
            unmatched.setdefault(a.harness or "?", []).append(a.name)
    for harness, names in unmatched.items():
        k = s.unlaunched.get(harness, 0)
        if harness in s.unreadable:
            result = (UNCHECKED, s.unreadable[harness])  # the unreadable one may be the agent
        elif k == 0:
            result = (UNCHECKED, INVISIBLE)
        elif k >= len(names):
            result = (MISSING, f"{k} {harness} process(es) in the team repo run without XT_AGENT")
        else:
            result = (UNCHECKED, f"{k} {harness} process(es) in the team repo run without XT_AGENT, "
                                 f"for {len(names)} agents without one: xt can't tell which is whose")
        for n in names:
            out[n] = result
    return out


def warning(name: str) -> str:
    return (f"{name} is running without xt's launch settings (restored by the multiplexer?): its model, "
            f"permissions and connector blocks may be missing. Run `xt restart {name}` (or `--all`).")


def alert(ctx: Ctx, results: dict[str, tuple[str, str]], live: dict) -> list[str]:
    """Raise one Inbox alert per agent running without xt's launch settings (once per occurrence);
    clear it once the agent is started by xt again or no longer running. "Not checked" changes
    nothing for that agent. Returns the names newly alerted."""
    alerts = Alerts(ctx)
    raised = []
    for name, (state, _) in results.items():
        if state == MISSING and alerts.raise_(f"{ALERT}{name}", warning(name)):
            raised.append(name)
    keep = {f"{ALERT}{n}" for n, (state, _) in results.items() if state in (MISSING, UNCHECKED)}
    alerts.resolve_prefix(ALERT, keep)
    return raised


def flagged(ctx: Ctx) -> set[str]:
    """Agents with an open launch-settings alert (the Team pane marks them)."""
    return {k[len(ALERT):] for k in Alerts(ctx).active() if k.startswith(ALERT)}
