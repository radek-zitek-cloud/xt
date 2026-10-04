"""v0.24.0, the documentation rework: README (#214), user guide (#219), examples (#220), story (#221)
and site (#222), checked against the code and the spec's bounds."""

import argparse
import html
import re
import subprocess

import pytest

from xt import cli

from .conftest import REPO

README = (REPO / "README.md").read_text()
GUIDE = (REPO / "docs" / "user-guide.md").read_text()
EXAMPLES = (REPO / "docs" / "examples.md").read_text()


def _sections(text: str) -> dict[str, str]:
    """`## ` heading -> its text, up to the next `## ` heading."""
    parts = re.split(r"^## (.+)$", text, flags=re.M)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts), 2)}


# --- #214 README ---------------------------------------------------------------------------------


def test_214_the_readme_is_short_and_links_onward():
    lines = README.splitlines()
    assert len(lines) <= 180 and len(re.findall(r"^## ", README, re.M)) <= 8
    for stale in ("as of v0.10.0", "Codex has carried every real team", "recommended for the liaison and lead",
                  "## Commands", "## Releasing"):
        assert stale not in README, stale
    for link in ("(docs/user-guide.md)", "(docs/examples.md)", "(docs/story.md)", "(docs/development.md)",
                 "(CHANGELOG.md)", "discussions/1", "issues/new/choose"):
        assert link in README, link
    assert "](docs/chat.svg)" in README and (REPO / "docs" / "chat.svg").read_text().startswith("<svg")
    svg = html.unescape((REPO / "docs" / "chat.svg").read_text()).replace("\xa0", " ")
    assert "xt chat with liaison" in svg and "tab answer (1)" in svg  # a capture of xt chat itself


def test_214_first_10_minutes_fits_its_bound_and_each_failure_is_in_the_guide():
    first = _sections(README)["First 10 minutes"]
    assert len(first.strip("\n").splitlines()) <= 30
    flat_first, flat_guide = " ".join(first.split()), " ".join(GUIDE.split())
    for failure in ("missing essentials", "xt: command not found", "next: start the Herdr session",
                    "blocked:liaison", "noprompt:liaison"):
        assert failure in flat_first and failure in flat_guide, failure
    assert "missing prerequisite: $tool" in (REPO / "bin" / "xt-clone.sh").read_text()  # the README's wording
    assert "missing essentials" in (REPO / "src" / "xt" / "init.py").read_text()
    assert "`xt chat`" in first.split("It works when", 1)[1]


def test_214_contributor_material_moved_to_development_md():
    dev = (REPO / "docs" / "development.md").read_text()
    for part in ("## Running the tests", "## Layout", "## Versioning", "## Releasing", "uv run pytest"):
        assert part in dev, part


def test_214_three_issue_forms_that_ask_what_a_maintainer_needs_and_warn_about_secrets():
    forms = sorted((REPO / ".github" / "ISSUE_TEMPLATE").glob("*.yml"))
    assert [f.name for f in forms] == ["bug.yml", "first-try.yml", "question.yml"]
    names = []
    for f in forms:
        text = f.read_text()
        name = re.search(r"^name: (.+)$", text, re.M).group(1)
        names.append(name)
        assert re.search(r"^description: .+$", text, re.M) and re.search(r"^body:$", text, re.M), f.name
        assert "don't paste secrets" in text.lower() or "please don't paste secrets" in text.lower(), f.name
        for line in text.splitlines():  # a plain scalar with ": " in it isn't valid YAML
            m = re.match(r"\s*(?:- )?[a-z_]+: (.+)$", line)
            if m and not m.group(1).startswith(('"', "'", "|", "[", "{")):
                assert ": " not in m.group(1), (f.name, line)
    assert names == ["Bug", "I tried it, here's what happened", "Question"]
    bug = (REPO / ".github" / "ISSUE_TEMPLATE" / "bug.yml").read_text()
    for asked in ("xt --version", "Harness and OS", "What you ran", "What you expected", "What happened"):
        assert asked in bug, asked


# --- #219 user guide -------------------------------------------------------------------------------


def _instruction_text(guide: str) -> str:
    """The guide without its headings and its Upgrading part (which may name versions)."""
    body = guide.split("#### Upgrading notes", 1)[0] + guide.split("## Working through an operator", 1)[1]
    return "\n".join(line for line in body.splitlines() if not line.startswith("#"))


def test_219_no_version_history_notes_in_instructions():
    text = _instruction_text(GUIDE)
    assert "from 0." not in text
    assert "as of v" not in text
    assert "removed in 0.24" in GUIDE and "xt capabilities carol" in GUIDE


def test_219_chat_comes_first_then_the_tui_then_the_operator():
    order = [GUIDE.index(h) for h in ("## Working in chat", "## Seeing how work flows", "## Running the team",
                                      "## Working through an operator", "## Command reference")]
    assert order == sorted(order)


def _commands():
    """(name, its parser) for every subcommand, nested ones included."""
    out = []

    def walk(parser, prefix):
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    out.append((f"{prefix} {name}".strip(), sub))
                    walk(sub, f"{prefix} {name}")

    walk(cli.build_parser(), "")
    return out


def test_219_every_command_and_option_is_in_the_reference_and_nothing_invented():
    reference = GUIDE.split("## Command reference", 1)[1]
    headings = set(re.findall(r"^### `xt ([a-z-]+)", reference, re.M)) | {"deny"}  # approve, deny share one
    names = {name.split()[0] for name, _ in _commands()}
    assert names <= headings, sorted(names - headings)
    assert headings <= names | {"approve", "deny"}, sorted(headings - names)  # no invented command
    for name, sub in _commands():
        words = name.split()
        if len(words) == 2:  # a nested subcommand, e.g. `xt goal new`: named in its parent's section
            assert f"xt {name}" in reference or f"xt {words[0]} " in reference, name
        for action in sub._actions:
            for flag in action.option_strings:
                if flag in ("-h", "--help", "--as"):
                    continue
                assert flag in GUIDE, (name, flag)
    for positional in ("show", "check", "use", "rollback", "add", "remove", "list", "pid", "new", "dispatch"):
        assert positional in reference, positional
    assert "--version" in GUIDE and "Every command accepts `--as NAME` and `-h`" in GUIDE


def test_219_links_inside_the_guide_resolve_to_its_headings():
    slugs = {re.sub(r"[^\w\- ]", "", h.strip().lower()).replace(" ", "-")
             for h in re.findall(r"^#+ (.+)$", GUIDE, re.M)}
    for anchor in re.findall(r"\]\(#([^)]+)\)", GUIDE):
        assert anchor in slugs, anchor


# --- #220 examples ---------------------------------------------------------------------------------


def test_220_every_example_is_labelled_and_none_has_an_old_permission_line():
    for heading, body in _sections(EXAMPLES).items():
        if not re.match(r"\d+\. ", heading):
            continue
        assert re.match(r"\s*\*(Runnable|Illustrative)[:.]", body), heading
    for line in EXAMPLES.splitlines():
        assert not re.match(r"\s*(permissions|codex_options|connectors) = ", line), line
    for wanted in ("A goal with read-back", "A question with options", "A hire waiting for your yes",
                   "the wheel", "A team.toml with a capability block"):
        assert wanted in EXAMPLES, wanted
    assert "from 0." not in EXAMPLES


def _blocks(text: str, lang: str) -> list[str]:
    return re.findall(rf"```{lang}\n(.*?)```", text, re.S)


def test_220_the_runnable_capability_example_does_what_it_shows(paths, monkeypatch, capsys):
    """Section 8 in a fresh team (what `xt init --yes` writes): the block loads, a typo is refused."""
    section = _sections(EXAMPLES)["8. A team.toml with a capability block"]
    (entry,) = _blocks(section, "toml")
    (settings,) = _blocks(section, "json")
    loads, refused = _blocks(section, "text")
    (paths.root / "settings").mkdir()
    (paths.root / "settings" / "researcher.json").write_text(settings)
    paths.team_toml.write_text(paths.team_toml.read_text() + "\n" + entry)
    monkeypatch.setenv("XT_ROOT", str(paths.root))
    assert cli.main(["goal", "list"]) == 0
    assert capsys.readouterr().out == loads
    paths.team_toml.write_text(paths.team_toml.read_text().replace('extras = "settings/researcher.json"',
                                                                   'extras = "settings/researcher.json"\nnetwerk = "on"'))
    assert cli.main(["goal", "list"]) == 1
    assert capsys.readouterr().err == refused


def test_220_the_illustrative_hire_quotes_what_xt_prints(ctx):
    from xt.spawn import request_spawn

    section = _sections(EXAMPLES)["6. A hire waiting for your yes"]
    ctx.herdr.add("lead")
    (ctx.paths.roles / "writer.md").write_text("# Role: writer\n")
    out = request_spawn(ctx, "lead", "writer", "claude", None, "writer", None)
    assert f"# {out.replace('approval #1', 'approval #6')}" in section or f"# {out}" in section.replace("#6", "#1")
    body = [m["body"] for m in ctx.ledger.messages() if m["type"] == "approval"][-1]
    shown = " ".join(_blocks(section, "text")[0].split())
    for sentence in ("WARNING: writer would start without generated settings, so the operator's own claude "
                     "defaults apply (a [capabilities] block in team.toml gives it some).",
                     "Approve its start: write, deny, network, credential_clis advisory (role text only)."):
        assert sentence in " ".join(body.split()) and sentence in shown, sentence


# --- #221 story -------------------------------------------------------------------------------------


def test_221_the_story_only_gains_a_date_line_and_the_epilogue():
    story = (REPO / "docs" / "story.md").read_text()
    try:
        base = subprocess.run(["git", "-C", str(REPO), "show", "772eec8fba4a9aa1b75b8d41b453661fb4ad4781:docs/story.md"],
                              capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("the v0.23.0 commit isn't in this checkout")
    epilogue = story.split("## Since then\n", 1)[1].split("## Read more", 1)[0]
    date_line = story.splitlines()[2]
    assert date_line.startswith("*Written 28 September 2026") and "(#since-then)" in date_line
    rebuilt = story.replace(date_line + "\n\n", "", 1).replace("## Since then\n" + epilogue, "")
    assert rebuilt == base
    assert len(epilogue.strip("\n").splitlines()) <= 60
    assert "(user-guide.md)" in epilogue and "(../CHANGELOG.md)" in epilogue


# --- #222 site ---------------------------------------------------------------------------------------


def test_222_the_site_agrees_with_the_readme():
    page = (REPO / "site" / "index.html").read_text()
    version = re.search(r'^version = "([\d.]+)', (REPO / "pyproject.toml").read_text(), re.M).group(1)
    assert f"open source · MIT · v{version}" in page
    assert "https://github.com/radek-zitek-cloud/xt/issues/new/choose" in page
    assert "https://github.com/radek-zitek-cloud/xt/discussions/1" in page
    assert "github.com/radek-zitek-cloud/xt#quick-start" in page and "## Quick start" in README
    chat = page.split('<div class="chat">', 1)[1].split("</div></div>", 1)[0]
    assert "Options:" in chat and "Recommended: 1" in chat and "Answer yes or no." in chat
