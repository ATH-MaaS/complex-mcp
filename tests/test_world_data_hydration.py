"""Regression tests for world-data hydration coverage (A1: 129/140 apps were
never wired to world_data.hydrate()).

Every app's session class now calls hydrate(self, "<App>") at the end of its
seed-branch __init__ (after the throwaway seed-rolled world + any fixtures).
hydrate() replaces every field the JSON declares wholesale, so with
COMPLEXMCP_WORLD_DATA active, get_session_dict() should reproduce the JSON
file exactly for every app whose JSON exists -- except apps world_data.py
explicitly documents it can't safely round-trip (currently just
LightWeather's "alerts", which dumps as a list but is stored as a dict; see
world_data.py's container-kind-mismatch skip).
"""
import glob
import importlib
import json
import os

import pytest

pytestmark = pytest.mark.filterwarnings("ignore")

WORLD_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "world_data")
# Apps whose get_session_dict() is genuinely {} (no state to hydrate/grade).
NO_STATE_APPS = {"LightNews", "LightSystem"}
# Known, documented hydration gaps -- container-kind mismatches that can't
# be round-tripped without a recoverable dict key. Keep this list honest:
# growing it silently would hide new regressions.
KNOWN_GAPS = {"LightWeather": {"alerts"}}


def _app_names():
    return sorted(
        os.path.basename(p)[:-5]
        for p in glob.glob(os.path.join(WORLD_DATA_DIR, "*.json"))
        if os.path.basename(p)[:-5] not in NO_STATE_APPS
    )


def _construct_hydrated_session(app_name, monkeypatch):
    monkeypatch.setenv("COMPLEXMCP_WORLD_DATA", os.path.abspath(WORLD_DATA_DIR))
    for path in sorted(glob.glob(f"software/{app_name}/*.py")):
        modname = path[:-3].replace("/", ".")
        module = importlib.import_module(modname)
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and hasattr(obj, "get_session_dict"):
                try:
                    return obj(os_cfg=None, seed=42)
                except Exception:
                    continue
    return None


@pytest.mark.parametrize("app_name", _app_names())
def test_world_data_hydrates_cleanly(app_name, monkeypatch):
    session = _construct_hydrated_session(app_name, monkeypatch)
    assert session is not None, f"{app_name}: could not construct a session"

    dumped = json.loads(json.dumps(session.get_session_dict(), default=str, sort_keys=True))
    with open(os.path.join(WORLD_DATA_DIR, f"{app_name}.json")) as fh:
        expected = json.loads(json.dumps(json.load(fh), sort_keys=True))

    gap_keys = KNOWN_GAPS.get(app_name, set())
    for key, exp_val in expected.items():
        if key in gap_keys:
            continue
        assert dumped.get(key) == exp_val, f"{app_name}.{key}: world data not reflected"


def test_world_data_inert_when_env_unset(monkeypatch):
    """hydrate() must be a no-op (return False) when COMPLEXMCP_WORLD_DATA
    isn't set -- world data is strictly opt-in."""
    monkeypatch.delenv("COMPLEXMCP_WORLD_DATA", raising=False)
    from software.LightAuction.auction import AuctionSession

    s1 = AuctionSession(os_cfg=None, seed=42)
    s2 = AuctionSession(os_cfg=None, seed=42)
    assert s1.get_session_dict() == s2.get_session_dict()
    assert list(s1.listings.values())[0].seller == "seller_a"  # seed-rolled, not world data
