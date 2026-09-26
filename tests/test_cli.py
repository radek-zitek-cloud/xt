from xt.cli import build_parser


def test_as_is_accepted_after_goal_subcommands():
    p = build_parser()
    a = p.parse_args(["goal", "new", "weather", "Build", "it", "--as", "liaison"])
    assert (a.goal_cmd, a.slug, a.title, a.as_) == ("new", "weather", ["Build", "it"], "liaison")
    a = p.parse_args(["goal", "dispatch", "weather", "--as", "liaison"])
    assert a.as_ == "liaison"


def test_send_defaults_to_report():
    a = build_parser().parse_args(["send", "lead", "--as", "carol", "hello", "there"])
    assert (a.to, a.type, a.body, a.as_) == ("lead", "report", ["hello", "there"], "carol")
