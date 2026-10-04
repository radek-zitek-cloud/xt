"""Card #215: the agent-lifecycle modules import each other in one direction only.

The import graph is built from the source, imports inside functions included. A cycle that passes
through one of the lifecycle modules or the shared layer (also through other modules on the way)
fails the test, naming the modules in it and the pairs that import each other directly.
"""

import ast
from pathlib import Path

import xt

LIFECYCLE = ("spawn", "watch", "reset", "jobs", "dispatch", "paneinput", "brief")
SHARED = ("lifecycle", "approvals")


def _name(src: Path, path: Path) -> str:
    return ".".join(path.relative_to(src).with_suffix("").parts).removesuffix(".__init__") or "__init__"


def import_graph(src: Path) -> dict[str, set[str]]:
    """module -> the xt modules it imports (relative imports, at any depth in the file)."""
    graph: dict[str, set[str]] = {}
    for path in sorted(src.rglob("*.py")):
        mod = _name(src, path)
        package = mod.split(".") if path.name == "__init__.py" else mod.split(".")[:-1]
        if mod == "__init__":
            package = []
        deps = graph.setdefault(mod, set())
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ImportFrom) or not node.level:
                continue
            base = package[: len(package) - (node.level - 1)]
            if node.module:
                target = ".".join(base + node.module.split("."))
                found = [target] + [f"{target}.{a.name}" for a in node.names]
            else:
                found = [".".join(base + [a.name]) for a in node.names]
            deps.update(t for t in found if (src / (t.replace(".", "/") + ".py")).exists() and t != mod)
    return graph


def cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """The strongly connected components with more than one module (Tarjan)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    found: list[list[str]] = []

    def visit(v: str) -> None:
        index[v] = low[v] = len(index)
        stack.append(v)
        on_stack.add(v)
        for w in sorted(graph.get(v, ())):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                found.append(sorted(comp))

    for v in sorted(graph):
        if v not in index:
            visit(v)
    return found


def lifecycle_problems(src: Path) -> list[str]:
    """Every cycle through a lifecycle or shared-layer module, and every import of a lifecycle
    module by the shared layer; empty when the layers hold."""
    graph = import_graph(src)
    watched = set(LIFECYCLE) | set(SHARED)
    problems = []
    for comp in cycles(graph):
        if watched & set(comp):
            pairs = sorted({f"{a} <-> {b}" for a in comp for b in graph[a]
                            if a < b and a in graph.get(b, ()) and {a, b} & set(LIFECYCLE)})
            problems.append(f"import cycle through {', '.join(comp)}; two-way pairs: {'; '.join(pairs) or 'none'}")
    for shared in SHARED:
        bad = sorted(graph.get(shared, set()) & set(LIFECYCLE))
        if bad:
            problems.append(f"the shared layer's {shared} imports {', '.join(bad)}")
    # after the cycles, so a tree from before the shared layer (v0.22.1) still names its pairs first
    missing = [m for m in LIFECYCLE + SHARED if not (src / f"{m}.py").exists()]
    if missing:
        problems.append(f"modules missing: {', '.join(missing)}")
    return problems


def test_215_no_import_cycle_through_the_lifecycle_modules():
    problems = lifecycle_problems(Path(xt.__file__).parent)
    assert not problems, "\n".join(problems)
