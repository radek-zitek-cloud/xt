"""Questions with a declared answer type (cards #111 and #182).

A question to the human is a narrative that may end in one question of a declared type:

- **closed**: yes or no (`--closed`).
- **options**: two to four numbered options, each with its consequence, exactly one
  recommended (`--option "text :: consequence"`, repeated, and `--recommend N`); with `--other`
  the human may also answer in their own words.
- **open**: free text (an ask with none of these flags).

The type, the options, the recommendation and the human's answer are stored as data in the ledger
entry (`question` on the ask, `answer` on the reply), and the text keeps a readable block so every
view (pane, Inbox, brief, `xt log`) shows them as well:

    <the question>

    Options:
    1. <option> — <consequence>
    2. <option> — <consequence>
    Recommended: 2
    Other: answer in your own words.      (only with --other; else "Answer with the option's number.")

Older asks have no `question` data: one with #111's block (two or three options, own words always
allowed) is read from its text, any other is an open question (card #182, Q4). An answer that is
an option's number is recorded as that option's full text, so the append-only ledger keeps what
was chosen, not a bare "2".
"""

import re

from .paths import XtError

SEP = " :: "  # --option "text :: consequence"
LINE = re.compile(r"^([1-4])\. (.+?) — (.+)$")
MAX_OPTIONS = 4
CLOSED_TAIL = "Answer yes or no."
OTHER_TAIL = "Other: answer in your own words."
NUMBER_TAIL = "Answer with the option's number."
LEGACY_TAIL = "Or answer in your own words."  # #111's asks
YES, NO = ("yes", "y"), ("no", "n")


def refuse(why: str) -> XtError:
    return XtError(f"{why}. Nothing was sent; your question is unchanged, fix it and send it again.")


def render(question: str, options: list[str], recommend: list[int] | int | None = None,
           closed: bool = False, other: bool = False) -> str:
    """The text alone (#111's call)."""
    return build(question, options, recommend, closed, other)[0]


def build(question: str, options: list[str], recommend: list[int] | int | None = None,
          closed: bool = False, other: bool = False) -> tuple[str, dict]:
    """(the text to send, the question's data). Refuses a malformed question before anything is
    sent: the caller keeps the text and shows it back."""
    question = question.strip()
    recs = [] if recommend is None else [recommend] if isinstance(recommend, int) else list(recommend)
    if not question:
        raise refuse("the question itself is empty")
    if closed:
        if options or recs:
            raise refuse("a closed question is answered yes or no: leave out --option and --recommend")
        if other:
            raise refuse("a closed question is answered yes or no: --other belongs to a question with --option")
        return f"{question}\n\n{CLOSED_TAIL}", {"kind": "closed"}
    if not options:
        if recs:
            raise refuse("--recommend needs the options it picks from: add --option (two to four)")
        if other:
            raise refuse("--other adds a free-text answer to options: add --option (two to four)")
        return question, {"kind": "open"}
    parsed = []
    for raw in options:
        text, _, cons = raw.partition(SEP)
        if not text.strip():
            raise refuse(f"option {raw!r} is empty: --option \"<option>{SEP}<what happens then>\"")
        if not cons.strip():
            raise refuse(f"option {raw!r} needs a consequence: --option \"<option>{SEP}<what happens then>\"")
        if "\n" in raw:
            raise refuse("an option is one line")
        parsed.append({"text": text.strip(), "consequence": cons.strip()})
    if not 2 <= len(parsed) <= MAX_OPTIONS:
        raise refuse(f"give two to four options (got {len(parsed)})")
    if len(recs) != 1 or not 1 <= recs[0] <= len(parsed):
        got = "none" if not recs else ", ".join(map(str, recs))
        raise refuse(f"recommend exactly one of the options: --recommend 1..{len(parsed)} once (got {got})")
    lines = [question, "", "Options:"]
    lines += [f"{i}. {o['text']} — {o['consequence']}" for i, o in enumerate(parsed, 1)]
    lines += [f"Recommended: {recs[0]}", OTHER_TAIL if other else NUMBER_TAIL]
    return "\n".join(lines), {"kind": "options", "options": parsed, "recommend": recs[0], "other": other}


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


def question_of(msg: dict | None) -> dict:
    """A question's data: what its ask stored, or for an older ask, what its text says (#111's
    options with own words allowed, else open)."""
    msg = msg or {}
    if isinstance(msg.get("question"), dict) and msg["question"].get("kind") in ("closed", "options", "open"):
        return msg["question"]
    body = msg.get("body", "")
    opts = options_of(body)
    if not opts:
        return {"kind": "open"}
    rec = re.search(r"^Recommended: (\d+)$", body, re.M)
    return {"kind": "options", "other": True, "recommend": int(rec.group(1)) if rec else None,
            "options": [dict(zip(("text", "consequence"), opts[n].split(" — ", 1))) for n in sorted(opts)]}


def option_line(o: dict) -> str:
    return f"{o['text']} — {o['consequence']}"


def summary(q: dict) -> str:
    """A question's type in a few words, for listings: `yes/no`, `4 options, Other`, ``."""
    if q["kind"] == "closed":
        return "yes/no"
    if q["kind"] == "options":
        return f"{len(q['options'])} options" + (", Other" if q.get("other") else "")
    return ""


def data_line(m: dict) -> str | None:
    """The stored question or answer of a message in one line, for `xt log` (card #182)."""
    q, a = m.get("question"), m.get("answer")
    if isinstance(q, dict):
        if q.get("kind") == "options":
            return (f"question: options 1-{len(q.get('options') or [])}, recommended {q.get('recommend')}"
                    + (", Other allowed" if q.get("other") else ""))
        return f"question: {q.get('kind')}" + (" (yes/no)" if q.get("kind") == "closed" else " (free text)")
    if isinstance(a, dict):
        if a.get("option"):
            return f"answer: option {a['option']}"
        return f"answer: {a.get('value')}" if a.get("kind") == "closed" else f"answer: {a.get('kind')}, own words"
    return None


def hint(q: dict) -> str:
    """What an answer may be, said to the human."""
    if q["kind"] == "closed":
        return "answer yes or no"
    if q["kind"] == "options":
        n = len(q["options"])
        nums = "1 or 2" if n == 2 else f"1 to {n}"
        return f"answer {nums}" + (", or in your own words (Other)" if q.get("other") else "")
    return "answer in your own words"


def resolve_answer(q: dict, answer: str) -> tuple[str, dict]:
    """(the text to record, the answer's data) for an answer to question `q`; refuses an answer
    its type doesn't allow."""
    a = answer.strip()
    if not a:
        raise XtError("the answer is empty")
    if q["kind"] == "closed":
        word = a.lower().rstrip(".!")
        if word in YES:
            return "yes", {"kind": "closed", "value": "yes"}
        if word in NO:
            return "no", {"kind": "closed", "value": "no"}
        raise XtError(f"this is a yes/no question: answer yes or no (got {a!r})")
    if q["kind"] == "options":
        opts = q["options"]
        if re.fullmatch(r"\d+", a):
            n = int(a)
            if not 1 <= n <= len(opts):
                raise XtError(f"there's no option {n}; choose {', '.join(str(i) for i in range(1, len(opts) + 1))}"
                              + (" or answer in your own words" if q.get("other") else ""))
            full = option_line(opts[n - 1])
            return f"Option {n}: {full}", {"kind": "options", "option": n, "value": full}
        for n, o in enumerate(opts, 1):  # the TUI fills a number in as the option's text, as recorded
            if a == f"Option {n}: {option_line(o)}":
                return a, {"kind": "options", "option": n, "value": option_line(o)}
        if not q.get("other"):
            raise XtError(f"this question takes an option's number ({hint(q)}); it has no Other, so own words "
                          f"aren't an answer here. To say something else, message the asker instead")
        return answer.strip(), {"kind": "options", "other": True, "value": answer.strip()}
    return answer.strip(), {"kind": "open", "value": answer.strip()}


def resolve(question_body: str, answer: str) -> tuple[str, int | None]:
    """#111's call, kept for older callers: the text to record for an answer to a question body."""
    text, data = resolve_answer(question_of({"body": question_body}), answer)
    return (text, data.get("option")) if data.get("option") else (answer, None)
