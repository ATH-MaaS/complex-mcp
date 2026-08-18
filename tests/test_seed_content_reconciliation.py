"""Regression tests for A4: task.toml's `seed` and world_data/fixture are two
independent content mechanisms, and declaring a seed for an app whose content
is actually static (loaded from a per-app corpus, not rolled) silently
implied per-task content variation that never happened.

This isn't a rewrite of the ~102 static apps -- their content is
static-by-design (tests/test_seed_plumbing.py already documents seed's only
guaranteed contract is driving self.rng for ids/timestamps). The fix is
reconciliation: an empirically-derived registry (seed_content_registry.py)
plus a run_benchmark.py advisory so task authors/tooling know which
mechanism actually governs a given app's content instead of assuming seed
does.
"""
import os

import pytest

from software.utils.seed_content_registry import CONTENT_VARIES_BY_SEED, seed_rolls_content


def test_registry_covers_every_stateful_app():
    import glob

    apps = {
        os.path.basename(p)
        for p in glob.glob("software/Light*")
        if os.path.basename(p) not in ("LightNews", "LightSystem")
    }
    missing = apps - set(CONTENT_VARIES_BY_SEED)
    assert not missing, f"apps missing from seed_content_registry: {missing}"


def test_unknown_app_defaults_to_varies_true():
    # Conservative default: an app not yet classified should never trigger a
    # false reconciliation warning.
    assert seed_rolls_content("LightTotallyMadeUpApp") is True


def test_known_static_and_varying_examples():
    # Spot-check both directions against apps whose behavior is obvious from
    # their own source (corpus-backed vs id/rng-bearing containers).
    assert seed_rolls_content("LightAuction") is True  # listings/bids carry rng-minted ids
    assert seed_rolls_content("LightWeather") is False  # static forecast corpus


def _static_apps_needing_warning(apps, seed, world_data_active, fixture_apps=frozenset()):
    """Mirrors run_benchmark.py's warning condition without needing to drive
    the full CLI loop."""
    if seed is None or world_data_active:
        return []
    return sorted(a for a in apps if a not in fixture_apps and not seed_rolls_content(a))


def test_warns_when_seed_declared_without_world_data_for_static_app():
    hits = _static_apps_needing_warning(["LightWeather"], seed=42, world_data_active=False)
    assert hits == ["LightWeather"]


def test_no_warning_when_world_data_active():
    hits = _static_apps_needing_warning(["LightWeather"], seed=42, world_data_active=True)
    assert hits == []


def test_no_warning_when_no_seed_declared():
    hits = _static_apps_needing_warning(["LightWeather"], seed=None, world_data_active=False)
    assert hits == []


def test_no_warning_for_fixture_covered_app():
    hits = _static_apps_needing_warning(
        ["LightShop"], seed=42, world_data_active=False, fixture_apps={"LightShop"}
    )
    assert hits == []


def test_no_warning_for_seed_varying_app():
    hits = _static_apps_needing_warning(["LightAuction"], seed=42, world_data_active=False)
    assert hits == []
