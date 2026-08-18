"""Seedless world snapshots.

Freeze a session's *generated* world so it can be loaded verbatim at login
instead of being rolled from a seed (ETOM-style: the world is read, not rolled).

Why pickle rather than hand-written JSON per app: a session's world is an
arbitrary object graph — typed dataclasses, nested lists/dicts, a `random.Random`
that is *shared* by reference with helpers like `TimeMachine`. Pickle preserves
that graph, including the shared-rng identity and the exact post-generation rng
state, so runtime id/timestamp/network minting reproduces the old seeded sequence
byte-for-byte. One utility works for all ~140 apps; no per-app serializer.

Recipe per app:
  1. BEFORE making the session seedless, run a bake against the still-seed-based
     code:  bake_session(core_session_at_seed_42, path)
     (bake while the core class is imported under its normal module name, so the
     pickle's class reference matches the one that exists at load time).
  2. Make the core session's __init__ seedless:
        restore_into(self, path); self.os = <live connector>
     (restore_into copies the frozen attributes onto `self`; pickle never calls
     __init__, so a changed/seedless class body is fine.)

A4 reconciliation -- seed vs. content, two different guarantees:
  `resolve_seed()` below always drives `self.rng`, so ids/timestamps/minted
  values are reproducible for a given seed (tests/test_seed_plumbing.py).
  That is NOT the same as "content varies by seed" -- ~102 of 138 apps load
  their substantive content (listings, tickets, messages, ...) from a static
  per-app corpus that a seed change never touches; only ~36 apps' content
  actually differs across seeds. See software/utils/seed_content_registry.py
  for the empirically-derived per-app answer. For task authors who need
  per-task content control on a seed-static app, the mechanism is
  software.utils.world_data (hydrate) or software.utils.fixtures, not seed;
  run_benchmark.py logs a one-time advisory when a task's declared seed
  can't actually do anything for one of its apps.
"""
from __future__ import annotations

import inspect
import logging
import os
import pickle
from pathlib import Path

_log = logging.getLogger("complexmcp.world_snapshot")

# Per-connection attributes that must NOT be frozen into the world — they are
# rebuilt from the live login (os_cfg) each session.
_LIVE_ATTRS = ("os",)


def _caller_app_label() -> str:
    """Best-effort app name for a boot-mode log line: the directory name of
    whichever module called seed_mode() (software/<App>/foo.py -> "<App>").
    Best-effort only — falls back to "?" if the stack is shallower than
    expected (e.g. seed_mode() called directly from a REPL/test)."""
    try:
        caller = inspect.stack()[2]  # [0]=this fn, [1]=seed_mode, [2]=app __init__
        return Path(caller.filename).resolve().parent.name
    except Exception:
        return "?"


# ---------------------------------------------------------------------------
# Seed architecture (default). The harness is seed-based: __init__ ROLLS the
# world from a seed (random.Random(seed)) so different seeds give different
# worlds (anti-memorisation, seed-based re-tiering). seed=42 reproduces the
# original frozen fixture exactly.
#
# The seedless static snapshot (world.pkl) is now an explicit escape hatch only:
# set COMPLEXMCP_SEED_MODE=static (or seedless/off/0/false/no) to load it.
#
# Log
# ---------------------------------------------------------------------------
def seed_mode() -> bool:
    """True iff apps should generate their world from a seed. This is the DEFAULT;
    only an explicit opt-out loads the frozen static snapshot."""
    raw = os.environ.get("COMPLEXMCP_SEED_MODE", "seed")
    seeded = raw.strip().lower() not in (
        "static", "seedless", "snapshot", "frozen", "0", "false", "off", "no",
    )
    app = _caller_app_label()
    if seeded:
        _log.info("[seed-mode] %s booting seed=%s (COMPLEXMCP_SEED_MODE=%r)",
                   app, resolve_seed(), raw)
    else:
        _log.warning(
            "[seed-mode] %s booting SEEDLESS from frozen world.pkl "
            "(COMPLEXMCP_SEED_MODE=%r) — gt_env is baked per-task-seed, so this "
            "world will NOT match gt_env unless world.pkl was baked at this "
            "task's seed. If this is unexpected, unset COMPLEXMCP_SEED_MODE.",
            app, raw)
    return seeded


def resolve_seed(seed=None) -> int:
    """The seed to roll the world from: explicit arg wins, else $COMPLEXMCP_SEED,
    else 42 (the fixture's own seed)."""
    if seed is not None:
        return int(seed)
    env = os.environ.get("COMPLEXMCP_SEED")
    if env not in (None, ""):
        return int(env)
    return 42


def bake_session(core, path) -> None:
    """Pickle `core`'s world to `path`, minus its live connection attrs."""
    stash = {k: getattr(core, k) for k in _LIVE_ATTRS if hasattr(core, k)}
    for k in stash:
        setattr(core, k, None)
    try:
        with open(path, "wb") as fh:
            pickle.dump(core, fh, protocol=pickle.HIGHEST_PROTOCOL)
    finally:
        for k, v in stash.items():
            setattr(core, k, v)


def restore_into(target, path):
    """Load a frozen world (from `path`) onto the live instance `target`.

    Copies the frozen attributes onto `target.__dict__`. The caller is
    responsible for (re)attaching live connection attrs (e.g. `target.os`)
    afterwards. Returns `target`.
    """
    with open(path, "rb") as fh:
        loaded = pickle.load(fh)
    target.__dict__.update(loaded.__dict__)
    return target
