import pytest

from xt.dispatch import Queue, done_recipient, drain, send
from xt.paths import XtError

from .conftest import add_member


def test_policy_allows_only_the_reports_to_chain(ctx):
    add_member(ctx, "carol")
    add_member(ctx, "dave")
    for a in ("liaison", "lead", "carol", "dave"):
        ctx.herdr.add(a)
    send(ctx, "carol", "lead", "report", "hi")
    send(ctx, "lead", "carol", "task", "do it")
    with pytest.raises(XtError, match="may only message"):
        send(ctx, "carol", "dave", "ask", "psst")
    with pytest.raises(XtError, match="may only message"):
        send(ctx, "carol", "liaison", "ask", "skip the lead")
    with pytest.raises(XtError, match="tasks go downward"):
        send(ctx, "carol", "lead", "task", "boss, do this")
    with pytest.raises(XtError, match="only the liaison"):
        send(ctx, "lead", "carol", "goal", "a goal")
    send(ctx, "human", "dave", "ask", "human may talk to anyone")


def test_unknown_or_retired_agents_are_refused(ctx):
    with pytest.raises(XtError, match="not an active member"):
        send(ctx, "mallory", "lead", "report", "x")
    add_member(ctx, "carol")
    ctx.team.set_status("carol", "retired")
    ctx.team.save()
    ctx.reload_team()
    with pytest.raises(XtError, match="not an active member"):
        send(ctx, "lead", "carol", "task", "x")


def test_agents_never_call_herdr_the_supervisor_delivers(ctx):
    # an agent's shell may be sandboxed (codex blocks Herdr's socket), so agent sends only queue
    add_member(ctx, "carol")
    ctx.herdr.add("carol")
    msg, status = send(ctx, "lead", "carol", "task", "parse the file")
    assert status.startswith("queued") and ctx.herdr.prompts == []
    assert drain(ctx) == [f"delivered #{msg['id']} to carol"]
    text = ctx.herdr.last_prompt("carol")
    assert text.startswith(f"[xt #{msg['id']} task from:lead to:carol]\nparse the file")
    assert f"--as carol --type report --ref {msg['id']}" in text
    assert f"--type done --ref {msg['id']}" in text


def test_queued_messages_are_delivered_as_one_batch(ctx):
    add_member(ctx, "carol")
    ctx.herdr.add("carol", status="working")
    m1, s1 = send(ctx, "lead", "carol", "task", "first")
    m2, s2 = send(ctx, "lead", "carol", "ask", "second")
    assert s1.startswith("queued") and s2.startswith("queued")
    assert drain(ctx) == []
    ctx.herdr.live["carol"].status = "idle"
    assert drain(ctx) == [f"delivered #{m1['id']}, #{m2['id']} to carol"]
    assert len(ctx.herdr.prompts) == 1
    text = ctx.herdr.last_prompt("carol")
    assert "2 messages arrived while you were busy" in text
    assert text.index("first") < text.index("second")
    assert Queue(ctx).pending() == []


def test_human_message_to_idle_agent_carries_queued_ones_along(ctx):
    add_member(ctx, "carol")
    ctx.herdr.add("carol", status="blocked")
    send(ctx, "lead", "carol", "task", "first")
    ctx.herdr.live["carol"].status = "idle"
    _, status = send(ctx, "human", "carol", "ask", "second")
    assert status == "delivered with 1 earlier queued"
    text = ctx.herdr.last_prompt("carol")
    assert "first" in text and "second" in text
    assert Queue(ctx).pending() == []


def test_batch_marks_messages_about_closed_items_as_stale(ctx):
    add_member(ctx, "carol")
    for a in ("lead", "carol"):
        ctx.herdr.add(a)
    ctx.herdr.live["lead"].status = "working"
    t, _ = send(ctx, "lead", "carol", "task", "do x")
    send(ctx, "carol", "lead", "report", "halfway on x", ref=t["id"])
    send(ctx, "carol", "lead", "done", "x finished", ref=t["id"])
    ctx.herdr.live["lead"].status = "idle"
    drain(ctx)
    text = ctx.herdr.last_prompt("lead")
    assert text.count("(stale:") == 2  # both are about the now-closed task
    assert "halfway on x" in text and "x finished" in text


def test_notes_are_logged_not_delivered(ctx):
    ctx.herdr.add("liaison")
    msg, status = send(ctx, "liaison", "", "note", "Human: wants a 1,000-word article")
    assert (msg["from"], msg["to"], msg["type"]) == ("liaison", "liaison", "note")
    assert "not delivered" in status and ctx.herdr.prompts == []
    with pytest.raises(XtError, match="not an active member"):
        send(ctx, "mallory", "", "note", "x")


def test_done_rules(ctx):
    add_member(ctx, "carol")
    add_member(ctx, "dave")
    for a in ("lead", "carol", "dave"):
        ctx.herdr.add(a)
    t, _ = send(ctx, "lead", "carol", "task", "x")
    with pytest.raises(XtError, match="needs --ref"):
        send(ctx, "carol", "lead", "done", "ok")
    with pytest.raises(XtError, match="owned by carol"):
        send(ctx, "dave", "lead", "done", "mine now", ref=t["id"])
    send(ctx, "carol", "lead", "done", "ok", ref=t["id"])
    assert ctx.ledger.item(t["id"]) is None
    with pytest.raises(XtError, match="not an open"):
        send(ctx, "carol", "lead", "done", "again", ref=t["id"])


def test_done_for_a_human_opened_goal_goes_up_the_chain(ctx):
    for a in ("liaison", "lead"):
        ctx.herdr.add(a)
    g, _ = send(ctx, "human", "lead", "goal", "a goal the human dispatched")
    item = ctx.ledger.item(g["id"])
    assert done_recipient(ctx.team, "lead", item) == "liaison"
    add_member(ctx, "carol")
    with pytest.raises(XtError, match="report done for"):
        send(ctx, "lead", "carol", "done", "allowed chain, wrong recipient", ref=g["id"])
    send(ctx, "lead", "liaison", "done", "finished", ref=g["id"])
    assert ctx.ledger.item(g["id"]) is None


def test_message_size_limit(ctx):
    ctx.herdr.add("lead")
    with pytest.raises(XtError, match="over the 4096 limit"):
        send(ctx, "liaison", "lead", "report", "x" * 5000)


def test_messages_to_human_are_not_delivered_via_herdr(ctx):
    ctx.herdr.add("liaison")
    _, status = send(ctx, "liaison", "human", "report", "hello human")
    assert "human" in status and ctx.herdr.prompts == []


def test_closing_a_goal_closes_its_leftover_tasks(ctx):
    add_member(ctx, "carol")
    for a in ("liaison", "lead", "carol"):
        ctx.herdr.add(a)
    g, _ = send(ctx, "liaison", "lead", "goal", "a goal")
    first, _ = send(ctx, "lead", "carol", "task", "review v1", ref=g["id"])
    second, _ = send(ctx, "lead", "carol", "task", "review v2", ref=g["id"])
    send(ctx, "carol", "lead", "done", "v2 approved", ref=second["id"])
    assert ctx.ledger.item(first["id"]) is not None  # the superseded first review is still open
    send(ctx, "lead", "liaison", "done", "goal finished", ref=g["id"])
    assert ctx.ledger.open_items() == []
    auto = [m for m in ctx.ledger.messages() if m["from"] == "xt" and m["type"] == "done"]
    assert [m["ref"] for m in auto] == [first["id"]] and "goal #" in auto[0]["body"]
    assert all("review v1" not in t for _, t in ctx.herdr.prompts[-1:])  # nobody woken for it
