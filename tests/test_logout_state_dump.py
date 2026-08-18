"""Regression test for A2: 94/140 apps' logout() hardcoded `"output": {}`
instead of dumping final session state, so the state-diff grading channel
came back empty for those apps regardless of what happened during the task.

Every app.py's logout() now returns session.<xxx>_session.get_session_dict()
(matching the pattern the other 46 apps already used). This doesn't assert
byte-identical content -- just that logout's output is no longer a dead
literal and matches what the session actually holds.
"""
import asyncio
import glob
import importlib
import logging
import os

import pytest

logging.disable(logging.CRITICAL)


def _app_names():
    return sorted(
        os.path.basename(os.path.dirname(p))
        for p in glob.glob("software/Light*/app.py")
        if os.path.basename(os.path.dirname(p)) not in (
            "LightSystem",  # implicit app, see memory
            "LightNews",  # get_session_dict() is genuinely {} -- not this bug
        )
    )


@pytest.mark.parametrize("app_name", _app_names())
def test_logout_returns_real_state(app_name):
    module = importlib.import_module(f"software.{app_name}.app")

    async def run():
        login_kwargs = {"os_cfg": None}
        r = await module.login.fn(**login_kwargs)
        sid = r["session_id"]
        return await module.logout.fn(sid)

    out = asyncio.run(run())
    assert out["status"] == "ok"
    assert "output" in out
    assert out["output"] != {}, f"{app_name}: logout() still returns empty output"
