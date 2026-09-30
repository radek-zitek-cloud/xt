"""v0.17.0, card #133: the published version is refreshed at supervisor start, after `xt version use`
and `xt version rollback`, and by hand (`xt version check`); it is never shown older than the
installed final. Each test runs on a disposable team whose upstream is a local repo (v0.15.0 newest)
and whose cache says an older release.
"""

import datetime as dt
import json

from xt import cli, switch, versions
from xt.tui.model import version_text
from xt.watch import Supervisor

from .test_batch_0140 import _g, team  # noqa: F401  (team is a fixture)


def _now():
    return dt.datetime.now(dt.timezone.utc).astimezone()


def _cache(ctx, version, hours_ago=0.0, **more):
    checked = (_now() - dt.timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    data = versions.load(ctx)
    data["published"] = {"version": version, "checked": checked, "error": None, **more}
    (ctx.paths.state / "versions.json").write_text(json.dumps(data))


def _published(ctx):
    return versions.load(ctx)["published"]


def _counting(monkeypatch):
    calls = []
    real = versions.refresh_published

    def counted(ctx, now, *a, **k):
        calls.append(now)
        return real(ctx, now, *a, **k)

    monkeypatch.setattr(versions, "refresh_published", counted)
    return calls


def test_the_supervisor_refreshes_once_at_start_then_every_six_hours(team, monkeypatch):  # noqa: F811
    _cache(team, "0.11.0")  # checked just now, so not due by the interval
    calls = _counting(monkeypatch)
    sup = Supervisor(team, out=lambda *_: None)
    sup.check_published()
    assert len(calls) == 1 and _published(team)["version"] == "0.15.0"
    sup.check_published()  # the interval applies again
    assert len(calls) == 1
    _cache(team, "0.15.0", hours_ago=7)
    sup.check_published()
    assert len(calls) == 2
    # a new supervisor (a restart) checks again at once
    Supervisor(team, out=lambda *_: None).check_published()
    assert len(calls) == 3


def test_an_offline_start_keeps_the_last_known_and_never_blocks(team):  # noqa: F811
    _cache(team, "0.13.0")
    _g(team.paths.root, "remote", "set-url", "upstream", str(team.paths.root.parent / "gone"))
    Supervisor(team, out=lambda *_: None).check_published()  # returns, no exception
    pub = _published(team)
    assert pub["version"] is None and pub["last_known"] == "0.13.0" and pub["error"]
    line = versions.current(team, live_names=set(), supervisor_running=False).line()
    assert "published 0.13.0 (last known, check failed:" in line


def test_a_version_switch_and_a_rollback_refresh_it(team):  # noqa: F811
    _cache(team, "0.11.0")
    lines = switch.use(team, "v0.14.0")
    assert lines[-1] == "published xt: 0.15.0" and _published(team)["version"] == "0.15.0"
    assert "published 0.15.0 (checked just now)" in versions.current(team, live_names=set(),
                                                                       supervisor_running=False).line()
    _cache(team, "0.11.0")
    lines = switch.rollback(team)
    assert lines[-1] == "published xt: 0.15.0" and _published(team)["version"] == "0.15.0"


def test_the_manual_check_refreshes_and_prints_the_result(team, monkeypatch, capsys):  # noqa: F811
    _cache(team, "0.11.0")
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: team))
    args = cli.build_parser().parse_args(["version", "check", "--as", "lead"])  # any member may check
    args.func(args)
    out = capsys.readouterr().out
    assert out.startswith("published xt: 0.15.0\n")
    assert "xt versions: published 0.15.0 (checked just now) · installed 0.13.0" in out
    assert "a newer release is published (0.15.0)" in out


def test_an_older_cache_than_the_installed_final_is_never_shown(team):  # noqa: F811
    switch.use(team, "v0.14.0")  # installed 0.14.0; then the cache says 0.13.0, the refresh fails
    _cache(team, "0.13.0", hours_ago=1)
    _g(team.paths.root, "remote", "set-url", "upstream", str(team.paths.root.parent / "gone"))
    v = versions.current(team, live_names=set(), supervisor_running=False)
    assert v.pending and not v.upgrade_available
    assert "published ≥ installed, check pending · installed 0.14.0" in v.line() and "0.13.0" not in v.line()
    assert v.title().endswith("published ≥ installed") and "0.13.0" not in version_text(v).plain
    assert "check pending" in version_text(v).plain
    # stale: retried every 15 minutes instead of every 6 hours, and a failure keeps "pending"
    assert versions.published_due(team, _now())
    _cache(team, "0.13.0", hours_ago=0.1)
    assert not versions.published_due(team, _now())
    Supervisor(team, out=lambda *_: None).check_published()
    v = versions.current(team, live_names=set(), supervisor_running=False)
    assert _published(team)["last_known"] == "0.13.0" and v.pending and "check pending" in v.line()
    # once the upstream answers, the real number shows
    _g(team.paths.root, "remote", "set-url", "upstream", str(team.paths.root.parent / "upstream"))
    Supervisor(team, out=lambda *_: None).check_published()
    v = versions.current(team, live_names=set(), supervisor_running=False)
    assert not v.pending and "published 0.15.0 (checked just now)" in v.line()


def test_a_candidate_or_an_equal_version_is_not_stale():
    assert not versions.stale("0.16.1", "0.17.0rc1")  # installed is a candidate, not a final
    assert not versions.stale("0.17.0", "0.17.0")
    assert not versions.stale("0.18.0", "0.17.0")
    assert not versions.stale(None, "0.17.0")
    assert versions.stale("0.16.1", "0.17.0")


def test_otherwise_the_six_hour_interval_still_applies(team):  # noqa: F811
    _cache(team, "0.13.0", hours_ago=5)  # installed 0.13.0: not stale
    assert not versions.published_due(team, _now())
    _cache(team, "0.13.0", hours_ago=6.1)
    assert versions.published_due(team, _now())
