"""Structured choices in questions (card #111).

An ask may carry two or three numbered options, each with its consequence, and exactly one
recommendation. They're written into the question's text as a fixed block, so every view (Inbox,
TUI dialog, brief, delivered message, `xt log`) shows them without any other change and the ledger
format stays as it is:

    <the question>

    Options:
    1. <option> — <consequence>
    2. <option> — <consequence>
    Recommended: 2
    Or answer in your own words.

An answer that is just an option's number is recorded as that option's full text, so the
append-only ledger keeps what was chosen, not a bare "2".
"""

import re

from .paths import XtError

SEP = " :: "  # --option "text :: consequence"
LINE = re.compile(r"^([1-3])\. (.+?) — (.+)$")


def render(question: str, options: list[str], recommend: int | None) -> str:
    """The question with its options block; refuses a malformed set (nothing is sent)."""
    question = question.strip()
    if not options and recommend is None:
        return question
    why = None
    parsed = []
    for raw in options:
        text, _, cons = raw.partition(SEP)
        if not text.strip() or not cons.strip():
            why = f"option {raw!r} needs a consequence: --option \"<option>{SEP}<what happens then>\""
            break
        if "\n" in raw:
            why = "an option is one line"
            break
        parsed.append((text.strip(), cons.strip()))
    if why is None and not 2 <= len(options) <= 3:
        why = f"give two or three options (got {len(options)})"
    if why is None and (recommend is None or not 1 <= recommend <= len(options)):
        why = f"recommend exactly one of the options: --recommend 1..{len(options)}"
    if why is None and not question:
        why = "the question itself is empty"
    if why:
        raise XtError(f"{why}. Nothing was sent; your question is unchanged, fix the options and send it again.")
    lines = [question, "", "Options:"]
    lines += [f"{i}. {text} — {cons}" for i, (text, cons) in enumerate(parsed, 1)]
    lines += [f"Recommended: {recommend}", "Or answer in your own words."]
    return "\n".join(lines)


def options_of(body: str) -> dict[int, str]:
    """{number: "option — consequence"} from a question's options block; {} when it has none."""
    if "\nOptions:\n" not in body:
        return {}
    block = body.split("\nOptions:\n", 1)[1]
    out = {}
    for line in block.splitlines():
        m = LINE.match(line.strip())
        if m:
            out[int(m.group(1))] = f"{m.group(2)} — {m.group(3)}"
        elif line.startswith("Recommended:"):
            break
    return out


def resolve(question_body: str, answer: str) -> tuple[str, int | None]:
    """The text to record for an answer: an option's full text when the answer is just its number."""
    opts = options_of(question_body)
    a = answer.strip()
    if not opts or not re.fullmatch(r"\d+", a):
        return answer, None
    n = int(a)
    if n not in opts:
        raise XtError(f"there's no option {n}; choose {', '.join(map(str, sorted(opts)))} or answer in your own words")
    return f"Option {n}: {opts[n]}", n
