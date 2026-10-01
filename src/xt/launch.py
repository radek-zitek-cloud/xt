"""Is each running agent the process xt started, with xt's launch settings? (card #165)

xt starts an agent by exporting XT_AGENT=<name> in a fresh pane and then starting the harness with
its model, settings file and connector and tool blocks. A terminal multiplexer that restores its
session after a power cycle resumes the agents with a plain resume command instead: same names, same
panes, none of those settings, and no XT_AGENT. So the signal is the identity variable in the live
harness process's environment, read from /proc: a harness process (its program is claude, codex or
pi, as for the identity guard) whose working directory is the team repo and whose environment has
XT_AGENT=<name> means xt started that agent. Herdr's agent list gives no process id, and a restored
process keeps no id xt recorded, so xt looks for the variable rather than for a known process.

A harness process whose environment can't be read (another user's, or no /proc in a sandbox) could
be the agent, so then the answer is "not checked", never a match and never a warning.
"""

import os
from dataclasses import dataclass

from .alerts import Alerts
from .context import Ctx

PROC = "/proc"
STARTED, MISSING, UNCHECKED = "started by xt", "without xt's launch settings", "not checked"
ALERT = "launch:"  # alert key prefix, one per agent


@dataclass
class Scan:
    names: set[str]  # XT_AGENT values of the team's harness processes
    unreadable: str | None = None  # why some harness process couldn't be inspected


def _names(pid_dir: str) -> set[str]:
    comm = open(f"{pid_dir}/comm").read().strip()
    argv = open(f"{pid_dir}/cmdline", "rb").read().split(b"\0")
    return {comm, *(os.path.basename(a.decode(errors="replace")) for a in argv[:2] if a)}


def scan_proc(root: str, proc: str | None = None) -> Scan:
    """XT_AGENT values in the environments of harness processes working in the team repo `root`."""
    from .cli import harness_in

    proc = proc or PROC
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError as e:
        return Scan(set(), f"can't list processes ({e.strerror or e})")
    found: set[str] = set()
    unreadable = None
    real_root = os.path.realpath(root)
    for pid in pids:
        d = f"{proc}/{pid}"
        try:
            if not harness_in([_names(d)]):
                continue
        except (OSError, ValueError):
            continue  # gone meanwhile, or not a process
        try:
            cwd = os.path.realpath(os.readlink(f"{d}/cwd"))
        except OSError:
            cwd = None  # unknown: it may belong to this team
        if cwd is not None and cwd != real_root:
            continue  # another team's or the human's own harness
        try:
            env = open(f"{d}/environ", "rb").read()
        except PermissionError:
            unreadable = f"no permission to read process {pid}'s environment"
            continue
        except OSError:
            continue
        for var in env.split(b"\0"):
            if var.startswith(b"XT_AGENT="):
                found.add(var[len("XT_AGENT="):].decode(errors="replace"))
    return Scan(found, unreadable)


scan = scan_proc  # tests replace this (they run no real agents)


def check(ctx: Ctx, live: dict) -> dict[str, tuple[str, str]]:
    """name -> (STARTED | MISSING | UNCHECKED, detail) for each running agent of the roster."""
    names = [a.name for a in ctx.team.agents() if a.kind != "human" and a.name in live]
    if not names:
        return {}
    s = scan(str(ctx.paths.root))
    out = {}
    for n in names:
        if n in s.names:
            out[n] = (STARTED, "")
        elif s.unreadable:
            out[n] = (UNCHECKED, s.unreadable)
        else:
            out[n] = (MISSING, "no harness process in the team repo has XT_AGENT=" + n)
    return out


def warning(name: str) -> str:
    return (f"{name} is running without xt's launch settings (restored by the multiplexer?): its model, "
            f"permissions and connector blocks may be missing. Run `xt restart {name}` (or `--all`).")


def alert(ctx: Ctx, results: dict[str, tuple[str, str]], live: dict) -> list[str]:
    """Raise one Inbox alert per agent running without xt's launch settings (once per occurrence);
    clear it once the agent is started by xt again or not running. Returns the names newly alerted."""
    alerts = Alerts(ctx)
    raised = []
    for name, (state, _) in results.items():
        if state == MISSING and alerts.raise_(f"{ALERT}{name}", warning(name)):
            raised.append(name)
    # keep: still missing, or not checked this time (no news either way)
    keep = {f"{ALERT}{n}" for n, (state, _) in results.items() if state in (MISSING, UNCHECKED)}
    alerts.resolve_prefix(ALERT, keep)
    return raised


def flagged(ctx: Ctx) -> set[str]:
    """Agents with an open launch-settings alert (the Team pane marks them)."""
    return {k[len(ALERT):] for k in Alerts(ctx).active() if k.startswith(ALERT)}
