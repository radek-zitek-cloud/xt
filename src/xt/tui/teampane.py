"""The Team pane's layout (card #128): the header line, one block per harness with its account
windows as bars, and the agents in fixed columns under it.

Pure functions of the snapshot and the pane width, so the layout is testable without a terminal.
Agents flow into up to three columns, column by column; a harness block takes as many of them as
its agents need, side by side while the blocks fit and stacked otherwise.
"""

import datetime as dt
import math
import re
from dataclasses import dataclass, field

from rich.text import Text

from ..usage import short

GAP = 2  # spaces between columns and between blocks
MAX_COLUMNS = 3
BAR_MAX, BAR_MIN = 8, 3  # the context bar's width in cells, shrunk before a column is given up
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


def cell(d: dict, w: Widths, bar: int, selected: bool = False) -> Text:
    """One agent: dot, name, short model, state, context tokens, a bar and the share of the window."""
    out = Text(no_wrap=True)
    out.append(d.get("dot", "○"), style=d.get("dot_style", "bright_black"))
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
    return out


def fit_columns(n_agents: int, width: int, w: Widths) -> tuple[int, int]:
    """(columns, bar width): as many columns (up to three) as the width allows, the bar shrunk
    first. Never more columns than agents."""
    for cols in range(min(MAX_COLUMNS, max(1, n_agents)), 0, -1):
        for bar in range(BAR_MAX, BAR_MIN - 1, -1):
            if cols * w.cell(bar) + GAP * (cols - 1) <= width:
                return cols, bar
    return 1, BAR_MIN


def allot(counts: list[int], cols: int) -> list[int]:
    """Columns per block, side by side: one each, then the rest to whichever block is tallest."""
    k = [1] * len(counts)
    for _ in range(cols - len(counts)):
        rows = [math.ceil(n / c) if n else 0 for n, c in zip(counts, k)]
        i = max(range(len(k)), key=lambda j: rows[j])
        if math.ceil(counts[i] / (k[i] + 1)) >= rows[i]:
            break  # another column wouldn't make the tallest block shorter
        k[i] += 1
    return k


# --- the pane ---------------------------------------------------------------------------------


def header_lines(left: Text, spend: str, width: int) -> list[Text]:
    """The team line with today's spend on the right; the spend on a line of its own when both
    don't fit."""
    from .model import fit

    if not spend:
        return [fit(left, "", width)]
    if left.cell_len + 2 + len(spend) <= width:
        line = left.copy()
        line.append(" " * (width - left.cell_len - len(spend)))
        line.append(spend, style="bright_black")
        return [line]
    return [fit(left, "", width), Text(spend.rjust(width), style="bright_black")]


def block_header(h: Harness, width: int, now: dt.datetime) -> list[Text]:
    """The harness name and its windows, wrapped onto more lines inside the block when needed."""
    from .model import fit

    name = h.name.upper()
    lines = [Text(name, style="bold")]
    indent = len(name) + 2
    for label, pct, reset in h.windows:
        seg = window_segment(label, pct, reset, now)
        if lines[-1].cell_len + 2 + seg.cell_len <= width:
            lines[-1].append("  ")
            lines[-1].append_text(seg)
        else:
            lines.append(Text(" " * indent) + seg)
    return [fit(ln, "", width) for ln in lines]


def pad(t: Text, width: int) -> Text:
    out = t.copy()
    out.append(" " * max(0, width - out.cell_len))
    return out


def span(k: int, cw: int) -> int:
    return k * cw + GAP * (k - 1)


def height(groups, by_harness: dict, cw: int, now: dt.datetime) -> int:
    """Lines the blocks take: each group's tallest header, then its tallest column."""
    return sum(max(len(block_header(b, span(k, cw), now)) for b, k in g)
               + max(math.ceil(len(by_harness[b.name]) / k) for b, k in g) for g in groups)


def render(header: Text, spend: str, harnesses: list[Harness], agents: list[dict], width: int,
           now: dt.datetime, selected: str | None = None) -> tuple[list[Text], list[str]]:
    """The pane's lines at `width`, and the agents' names in display order (for j/k)."""
    lines = header_lines(header, spend, width)
    by_harness: dict[str, list[dict]] = {}
    for a in agents:
        by_harness.setdefault(a["harness"], []).append(a)
    blocks = [h for h in harnesses if by_harness.get(h.name)]
    blocks += [Harness(n) for n in sorted(by_harness) if n not in {h.name for h in harnesses}]
    if not blocks:
        return lines, []
    w = widths(agents)
    cols, bar = fit_columns(len(agents), width, w)
    cw = w.cell(bar)
    counts = [len(by_harness[b.name]) for b in blocks]
    # one block under the other, each with every column; or side by side when that is shorter
    groups = [[(b, min(cols, n))] for b, n in zip(blocks, counts)]
    if len(blocks) <= cols:
        side = [list(zip(blocks, allot(counts, cols)))]
        if height(side, by_harness, cw, now) <= height(groups, by_harness, cw, now):
            groups = side
    order: list[str] = []
    for group in groups:
        spans = [span(k, cw) for _, k in group]
        heads = [block_header(b, sp, now) for (b, _), sp in zip(group, spans)]
        for i in range(max(len(hd) for hd in heads)):
            line = Text()
            for j, (hd, sp) in enumerate(zip(heads, spans)):
                line.append(" " * GAP if j else "")
                line.append_text(pad(hd[i] if i < len(hd) else Text(), sp))
            line.rstrip()
            lines.append(line)
        tall = [math.ceil(len(by_harness[b.name]) / k) for b, k in group]
        grid = []
        for (b, k), rows in zip(group, tall):
            members = by_harness[b.name]
            grid.append([members[c * rows:(c + 1) * rows] for c in range(k)])
            order += [a["name"] for a in members]
        for r in range(max(tall)):
            line = Text()
            for j, columns in enumerate(grid):
                for c, column in enumerate(columns):
                    line.append(" " * GAP if j or c else "")
                    if r < len(column):
                        line.append_text(cell(column[r], w, bar, column[r]["name"] == selected))
                    else:
                        line.append(" " * cw)
            line.rstrip()
            lines.append(line)
    return lines, order
