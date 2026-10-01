"""The Team pane's layout: the header line, today's spend, then one block per harness, its account
windows as bars and its agents under it, one column (card #162; card #128 had up to three).

Pure functions of the snapshot and the pane width, so the layout is testable without a terminal.
The pane never scrolls: what doesn't fit its height gives way to a last `+N more` line (`clip`).
"""

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Callable

from rich.style import Style
from rich.text import Text

from ..usage import short

BAR_MAX, BAR_MIN = 8, 3  # the context bar's width in cells, shrunk before the cell is cut
WINDOW_BAR = 10
PCT_WIDTH = 4  # "100%"
STATE_STYLE = {"idle": "green", "done": "green", "working": "yellow", "blocked": "red"}
SELECTED = "bold bright_white on blue"  # the selected agent's cell
EIGHTHS = " ▏▎▍▌▋▊▉█"
VENDOR = re.compile(r"^(?:[a-z0-9_.-]+/)?(?:claude-|anthropic[.-])?", re.I)
VERSIONED = re.compile(r"^([a-z]+)-(\d+)-(\d+)(?:-\d{8})?$", re.I)


@dataclass
class Harness:
    name: str
    windows: list[tuple[str, float, int | None]] = field(default_factory=list)  # (label, used %, resets_at)
    cue: bool = False  # a window with a stale or no reading: a dim `?` after the name (card #151)
    detail: Callable[[], object] | None = None  # what Detail shows with the harness line selected


def short_model(model: str | None) -> str:
    """`claude-sonnet-5-5` → `sonnet 5.5`: the vendor prefix dropped, a dashed version dotted, a
    date suffix dropped. Anything else (`gpt-5.2-codex`, `kimi`) is shown as it is."""
    if not model:
        return "default"
    m = VENDOR.sub("", model.strip())
    v = VERSIONED.match(m)
    return f"{v.group(1)} {v.group(2)}.{v.group(3)}" if v else (m or model)


def shown_model(configured: str | None, session: str | None) -> str:
    """The configured model; for `default` the real one when the agent's own session log names it."""
    if configured and configured != "default":
        return short_model(configured)
    return short_model(session) if session else "default"


def pct_style(pct: float) -> str:
    return "red" if pct >= 85 else "yellow" if pct >= 70 else ""


def window_bar(pct: float, width: int = WINDOW_BAR) -> str:
    full = round(max(0.0, min(100.0, pct)) / 100 * width)
    return "▓" * full + "░" * (width - full)


def context_bar(frac: float, width: int) -> str:
    """A bar in eighths of a cell, exactly `width` cells."""
    eighths = round(max(0.0, min(1.0, frac)) * width * 8)
    full, part = divmod(eighths, 8)
    return ("█" * full + (EIGHTHS[part] if part else "")).ljust(width)[:width]


def reset_text(resets_at: int | None, now: dt.datetime) -> str:
    """`resets 11:50` within a day, else `resets Tue 12:00`."""
    if not resets_at:
        return ""
    try:
        when = dt.datetime.fromtimestamp(resets_at, now.tzinfo)
    except (OverflowError, OSError, ValueError):
        return ""
    return f"resets {when:%H:%M}" if when - now < dt.timedelta(days=1) else f"resets {when:%a %H:%M}"


def window_segment(label: str, pct: float, resets_at: int | None, now: dt.datetime) -> Text:
    out = Text(f"{label} ")
    out.append(window_bar(pct), style=pct_style(pct) or "cyan")
    out.append(f" {pct:>3.0f}%")
    reset = reset_text(resets_at, now)
    if reset:
        out.append(f" {reset}", style="bright_black")
    return out


# --- agent cells ------------------------------------------------------------------------------


@dataclass
class Widths:
    name: int
    model: int
    state: int
    tokens: int

    def cell(self, bar: int) -> int:
        # dot, name, model, state, tokens, ▕bar▏, percentage, one space between each
        return 1 + 1 + self.name + 1 + self.model + 1 + self.state + 1 + self.tokens + 1 + (bar + 2) + 1 + PCT_WIDTH


def tokens_text(d: dict) -> str:
    if d.get("used") is None:
        return "—"
    return f"{'~' if d.get('approximate') else ''}{short(d['used'])}"


def context_pct(d: dict) -> float | None:
    return 100 * d["used"] / d["window"] if d.get("used") is not None and d.get("window") else None


def widths(agents: list[dict]) -> Widths:
    """Column widths shared by every agent in the pane, so columns line up across rows and blocks."""
    return Widths(max((len(a["name"]) for a in agents), default=4),
                  max((len(a["model"]) for a in agents), default=7),
                  max((len(a["state"]) for a in agents), default=4),
                  max((len(tokens_text(a)) for a in agents), default=1))


def dot_style(d: dict) -> str:
    """The state dot's style: the state word's colour while the agent runs, dim when it doesn't
    (card #157). Only the terminal's named colours, so the human's theme decides the shades."""
    return STATE_STYLE.get(d["state"], "bright_black") if d.get("running") else "bright_black"


def cell(d: dict, w: Widths, bar: int, selected: bool = False) -> Text:
    """One agent: dot, name, short model, state, context tokens, a bar and the share of the window.
    The whole cell carries the agent's name as meta, so a click on it selects the agent (card #157)."""
    out = Text(no_wrap=True)
    if d.get("unlaunched"):  # running without xt's launch settings (card #165)
        out.append("!", style="bold red")
    else:
        out.append(d.get("dot", "○"), style=dot_style(d))
    out.append(f" {d['name']:<{w.name}} ", style="bold" if d.get("running") else "")
    out.append(f"{d['model']:<{w.model}} ", style="bright_black")
    out.append(f"{d['state']:<{w.state}} ", style=STATE_STYLE.get(d["state"], "bright_black"))
    out.append(f"{tokens_text(d):>{w.tokens}} ", style="bright_black")
    pct = context_pct(d)
    style = pct_style(pct) if pct is not None else ""
    out.append("▕", style="bright_black")
    out.append(context_bar(pct / 100, bar) if pct is not None else " " * bar, style=style or "cyan")
    out.append("▏", style="bright_black")
    out.append(f" {f'{pct:.0f}%' if pct is not None else '':>{PCT_WIDTH}}", style=style)
    if selected:
        out.stylize(SELECTED)
    out.stylize(Style.from_meta({"agent": d["name"]}))
    return out


def fit_bar(width: int, w: Widths) -> int:
    """The widest context bar with which an agent's cell fits `width`; the narrowest one when none
    does (the cell is then cut at the pane's edge)."""
    return next((bar for bar in range(BAR_MAX, BAR_MIN - 1, -1) if w.cell(bar) <= width), BAR_MIN)


# --- the pane ---------------------------------------------------------------------------------

HEADER = ":header"  # the key of the header line (no agent name has a colon); a harness line's is harness_key(name)
MORE = "+{n} more (widen the terminal)"


def harness_key(name: str) -> str:
    return f"harness:{name}"


def block_header(h: Harness, width: int, now: dt.datetime) -> list[Text]:
    """The harness name and its windows, wrapped onto more lines inside the block when needed."""
    from .model import fit

    name = h.name.upper()
    lines = [Text(name, style="bold")]
    if h.cue:
        lines[0].append(" ?", style="bright_black")
    indent = lines[0].cell_len + 2
    for label, pct, reset in h.windows:
        seg = window_segment(label, pct, reset, now)
        if lines[-1].cell_len + 2 + seg.cell_len <= width:
            lines[-1].append("  ")
            lines[-1].append_text(seg)
        else:
            lines.append(Text(" " * indent) + seg)
    return [fit(ln, "", width) for ln in lines]


def separator(width: int) -> Text:
    return Text("─" * width, style="bright_black")


def wrap_header(header: Text, width: int) -> list[Text]:
    """The header on as many lines as it needs, broken only between its ` · ` parts, so what needs
    the human is never cut off at the pane's edge; a part longer than a line is cut with `…`."""
    from .model import fit

    out: list[Text] = []
    for part in header.split(" · ", allow_blank=True):
        part.rstrip()
        if out and out[-1].cell_len + 3 + part.cell_len <= width:
            out[-1].append(" · ")
            out[-1].append_text(part)
        else:
            out.append(part)
    return [fit(ln, "", width) for ln in out] or [Text("")]


def render(header: Text, spend: str, harnesses: list[Harness], agents: list[dict], width: int,
           now: dt.datetime, selected: str | None = None) -> list[tuple[Text, str | None]]:
    """The pane's lines at `width`, top to bottom, each with the key of the row it belongs to: the
    header line (HEADER), a harness's lines (harness_key), an agent's line (its name), or None for
    today's spend and the separators. In order: the header, today's spend, a separator, then per
    harness its usage line and its agents, a separator between harnesses (card #162). The header and
    the harness lines are rows that can be selected too (card #151); `selected` is a row's key."""
    from .model import fit

    out: list[tuple[Text, str | None]] = [(ln, HEADER) for ln in wrap_header(header, width)]
    if spend:
        out.append((fit(Text(spend, style="bright_black"), "", width), None))
    by_harness: dict[str, list[dict]] = {}
    for a in agents:
        by_harness.setdefault(a["harness"], []).append(a)
    blocks = [h for h in harnesses if by_harness.get(h.name)]
    blocks += [Harness(n) for n in sorted(by_harness) if n not in {h.name for h in harnesses}]
    w = widths(agents)
    bar = fit_bar(width, w)
    for b in blocks:
        out.append((separator(width), None))
        out += [(ln, harness_key(b.name)) for ln in block_header(b, width, now)]
        out += [(fit(cell(a, w, bar, a["name"] == selected), "", width), a["name"]) for a in by_harness[b.name]]
    for line, key in out:  # the header and harness rows: selected like an agent, and a click selects them
        if key in (HEADER, *(harness_key(b.name) for b in blocks)):
            if key == selected:
                line.append(" " * max(0, width - line.cell_len))
                line.stylize(SELECTED)
            line.stylize(Style.from_meta({"team_row": key}))
    return out


def clip(lines: list[tuple[Text, str | None]], limit: int | None) -> tuple[list[tuple[Text, str | None]], int]:
    """At most `limit` lines: when they don't all fit, the first `limit - 1` and a last `+N more
    (widen the terminal)` line, N being the harnesses and agents with no line left in view. Also N.
    A row cut in half (a harness's second usage line) counts as shown."""
    if limit is None or len(lines) <= limit:
        return lines, 0
    kept = lines[:max(0, limit - 1)]
    shown = {k for _, k in kept}
    hidden = [k for k in dict.fromkeys(k for _, k in lines[len(kept):]) if k is not None and k not in shown]
    return kept + [(Text(MORE.format(n=len(hidden)), style="bright_black"), None)], len(hidden)
