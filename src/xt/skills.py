"""The team's skills: `skills/<name>/SKILL.md`, indexed into every first prompt and brief."""

import re

from .paths import Paths

_FRONT = re.compile(r"^---\s*\n(.*?)\n---", re.S)


def index(paths: Paths) -> list[dict]:
    out = []
    for f in sorted(paths.skills.glob("*/SKILL.md")):
        meta = {}
        m = _FRONT.match(f.read_text())
        if m:
            for line in m.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"')
        out.append(
            {
                "name": meta.get("name", f.parent.name),
                "description": meta.get("description", ""),
                "path": str(f.relative_to(paths.root)),
            }
        )
    return out


def render(paths: Paths) -> str:
    items = index(paths)
    if not items:
        return "(no team skills yet)"
    return "\n".join(f"- {s['name']}: {s['description']} ({s['path']})" for s in items)
