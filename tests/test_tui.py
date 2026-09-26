import asyncio

from xt.tui.app import Help, Panel, Prompt, XtTui, demo_model


def test_tui_demo_navigation_and_popups():
    async def run():
        app = XtTui(demo_model())
        async with app.run_test(size=(120, 40)) as pilot:
            assert app.focused.id == "panel-1"
            await pilot.press("2", "j", "j")
            assert app.focused.id == "panel-2"
            assert app.focused.border_subtitle == "3 of 4"
            await pilot.press("s")
            assert isinstance(app.screen, Prompt)
            await pilot.press("escape", "question_mark")
            assert isinstance(app.screen, Help)
            await pilot.press("escape", "tab")
            assert isinstance(app.focused, Panel) and app.focused.id == "panel-3"

    asyncio.run(run())
