"""Bring-your-own world data: hydrate a session's fields from user-authored
JSON instead of the seed-rolled/random world.

Guarded by the ``COMPLEXMCP_WORLD_DATA`` env var, so it's inert unless a run
explicitly opts in. When set to a directory, and that directory contains
``<AppName>.json``, the JSON is loaded and used to REPLACE the named
top-level fields on the session -- not merged, not overlaid onto the seeded
world: the fields the JSON declares become the session's entire state for
those fields, same as the seed roll they take the place of. (Contrast with
``fixtures.py``, which overlays a couple of entities onto an otherwise
seeded world -- world data replaces a whole app's world wholesale.)

The JSON must mirror the session's own field shape -- the same shape its
``get_session_dict()`` dump already produces: dicts of id -> dataclass keep
their id keys, lists of dataclasses stay lists. Each app calls
``hydrate(self, "LightXxx")`` once, at the end of its seed-branch
``__init__`` (after the normal seed-rolled content and any fixtures have
been generated) -- ``hydrate()`` then overwrites every field the JSON
declares, so the *observable* state (whatever ``get_session_dict()``
reports) ends up sourced only from world data, even though a throwaway
seed-rolled world was generated first. Generating-then-discarding is
deliberate: ``self.rng``/``self.os`` setup is entangled with content
generation in most apps' ``__init__`` (not factored into an isolable call),
so overwriting after the fact is the only way to replace content wholesale
without risking half-initialized sessions (dead rng, missing connector).

Shape resolution is two-tiered:
  1. A handful of apps need an explicit ``_SHAPES`` entry -- their
     ``get_session_dict()`` key doesn't map 1:1 onto a single attribute
     (renamed, e.g. LightTalk's "contacts" -> ``contacts_dict``; scalar
     needs a type conversion, e.g. LightBudget's "today" string ->
     ``self._today`` datetime; or the JSON key aggregates several
     attributes into one nested object, e.g. LightStock's "user"/"stocks").
  2. Everything else is resolved automatically: ``get_session_dict()``'s own
     AST tells us which attribute each key dumps and whether it's a
     dict/list of dataclasses or a scalar; the attribute's own
     ``self.x: T = ...`` annotation (inside ``__init__``) tells us the
     element type ``T`` to coerce JSON values into. No per-app shape
     function needed for the common ``{k: asdict(v) for k, v in
     self.x.items()}`` / ``[asdict(v) for v in self.x]`` patterns that make
     up the vast majority of apps.
"""
from __future__ import annotations

import ast
import dataclasses
import inspect
import json
import logging
import os
import typing

_log = logging.getLogger("complexmcp.world_data")


def active_dir() -> str:
    return os.environ.get("COMPLEXMCP_WORLD_DATA", "").strip()


def _coerce(tp, value):
    """Rebuild `value` (plain JSON dict/list/scalar) into the shape `tp`
    declares, recursing into nested dataclass/Dict/List/Set fields."""
    if value is None or tp is None:
        return value
    origin = typing.get_origin(tp)
    if origin is dict and isinstance(value, dict):
        args = typing.get_args(tp)
        vtype = args[1] if len(args) == 2 else None
        return {k: _coerce(vtype, v) for k, v in value.items()}
    if origin is list and isinstance(value, list):
        args = typing.get_args(tp)
        etype = args[0] if args else None
        return [_coerce(etype, v) for v in value]
    if origin is set and isinstance(value, list):
        args = typing.get_args(tp)
        etype = args[0] if args else None
        return {_coerce(etype, v) for v in value}
    if dataclasses.is_dataclass(tp) and isinstance(value, dict):
        hints = typing.get_type_hints(tp)
        kwargs = {}
        for f in dataclasses.fields(tp):
            if f.name in value:
                kwargs[f.name] = _coerce(hints.get(f.name, f.type), value[f.name])
        return tp(**kwargs)
    return value  # scalar (str/float/int/bool) or unresolvable type: as-is


# --------------------------------------------------------------------------
# Hand-authored overrides: {app_name: () -> {json_key: spec}}
#
# spec is one of:
#   ("dict", ElementCls[, attr_name])   -- json_key's dict values are ElementCls
#   ("list", ElementCls[, attr_name])   -- json_key's list elements are ElementCls
#   ("scalar", coerce_fn, attr_name)    -- json_key's scalar value needs a
#                                           type conversion and/or a rename
#   ("fn", callable)                    -- json_key's value doesn't map onto
#                                           a single attribute at all (e.g. it
#                                           aggregates several); callable(session, value)
#                                           does the assignment itself.
#
# attr_name defaults to json_key when omitted. Only apps whose
# get_session_dict() key doesn't reduce to "one attribute, faithfully
# dumped" need an entry here -- everything else is auto-derived, see
# _auto_shape() below.
# --------------------------------------------------------------------------
def _shop_shape():
    from software.LightShop.shop import Shop, CartItem, Transaction
    return {
        "shops": ("dict", Shop),
        "cart": ("list", CartItem),
        "trans_history": ("list", Transaction),
    }


def _budget_shape():
    from software.LightBudget.budget import Category, Transaction, Budget
    from datetime import datetime
    return {
        "categories": ("dict", Category),
        "transactions": ("dict", Transaction),
        "budgets": ("dict", Budget),
        # get_session_dict() dumps self._today as a "YYYY-MM-DD" string.
        "today": ("scalar", lambda v: datetime.fromisoformat(v), "_today"),
    }


def _talk_shape():
    from software.LightTalk.contact import Contact, Group
    return {
        # get_session_dict() calls this "contacts"; the live attr is contacts_dict.
        "contacts": ("dict", Contact, "contacts_dict"),
        "groups": ("list", Group),
    }


def _tax_shape():
    # Only "today" needs an override (str -> datetime); "filings",
    # "deductions", "income_sources" all resolve fine via _auto_shape() and
    # are left for it -- an override here would only replace them, not add
    # to them (see hydrate()'s merge).
    from datetime import datetime
    return {
        "today": ("scalar", lambda v: datetime.fromisoformat(v), "_today"),
    }


def _wallet_shape():
    from datetime import datetime
    return {
        "today": ("scalar", lambda v: datetime.fromisoformat(v), "_today"),
    }


def _podcast_shape():
    return {
        # self.subscribed is a Set[str]; JSON carries it as a sorted list.
        "subscribed": ("scalar", lambda v: set(v), "subscribed"),
    }


def _flight_shape():
    from software.LightFlight.flight import BookingItem, PassengerInfo
    return {
        # get_session_dict() calls this "bookings"; the live attr is current_bookings.
        "bookings": ("list", BookingItem, "current_bookings"),
        "passengers": ("list", PassengerInfo),
    }


def _stock_user_fn(session, value):
    session.user_tier = value.get("tier", session.user_tier)
    session.trading_balance = value.get("trading_balance", session.trading_balance)
    session.savings_balance = value.get("savings_balance", session.savings_balance)
    session.frozen_margin = value.get("frozen_margin", session.frozen_margin)


def _stock_stocks_fn(session, value):
    from software.LightStock.stock import Position, PendingOrder, StockTransaction
    portfolio = value.get("portfolio")
    if portfolio is not None:
        session.portfolio = {p["ticker"]: _coerce(Position, p) for p in portfolio}
    pending = value.get("pending_orders")
    if pending is not None:
        session.pending_orders = [_coerce(PendingOrder, p) for p in pending]
    history = value.get("trade_history")
    if history is not None:
        session.trade_history = [_coerce(StockTransaction, p) for p in history]
    watch = value.get("watch_list")
    if watch is not None:
        session.watchlist = set(watch)
    alerts = value.get("price_alerts")
    if alerts is not None:
        session.price_alerts = dict(alerts)


def _stock_shape():
    return {
        "user": ("fn", _stock_user_fn),
        "stocks": ("fn", _stock_stocks_fn),
    }


_SHAPES = {
    "LightShop": _shop_shape,
    "LightBudget": _budget_shape,
    "LightTalk": _talk_shape,
    "LightTax": _tax_shape,
    "LightWallet": _wallet_shape,
    "LightPodcast": _podcast_shape,
    "LightFlight": _flight_shape,
    "LightStock": _stock_shape,
}


def _talk_post_hydrate(session) -> None:
    """LightTalk derives uid_dict/uids from contacts_dict, and my_uid/my_name/
    my_gender identify which contact is "me" -- all stale once hydrate()
    replaces contacts_dict wholesale. Rebuild them from the hydrated data,
    repointing "me" at whichever hydrated contact is tagged "me" (falls back
    to leaving the seed-rolled my_uid alone if none is tagged, so a partial
    JSON that doesn't declare "contacts" doesn't break identity)."""
    contacts = getattr(session, "contacts_dict", {})
    if not contacts:
        return
    session.uid_dict = {c.name: uid for uid, c in contacts.items()}
    session.uids = list(contacts.keys())
    for uid, c in contacts.items():
        if getattr(c, "tag", None) == "me":
            session.my_uid = uid
            session.my_name = c.name
            session.my_gender = c.gender
            break


_POST_HYDRATE = {
    "LightTalk": _talk_post_hydrate,
}


# --------------------------------------------------------------------------
# Auto-derivation: infer {json_key: spec} straight from get_session_dict()'s
# own source, for the apps with no _SHAPES entry above.
# --------------------------------------------------------------------------
_AUTO_SHAPE_CACHE: dict = {}


def _first_self_attr(node: ast.AST):
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self":
            return n.attr
    return None


def _classify(value_node: ast.AST):
    """Returns (kind, attr_name) for one get_session_dict() return-dict value."""
    if isinstance(value_node, ast.DictComp):
        attr = _first_self_attr(value_node.generators[0].iter) if value_node.generators else None
        return "dict", attr
    if isinstance(value_node, ast.ListComp):
        attr = _first_self_attr(value_node.generators[0].iter) if value_node.generators else None
        return "list", attr
    if isinstance(value_node, ast.Call) and isinstance(value_node.func, ast.Name) and value_node.func.id == "list":
        return "list", _first_self_attr(value_node)
    return "scalar", _first_self_attr(value_node)


def _get_session_dict_return(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "get_session_dict":
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Dict):
                    return stmt.value
    return None


def _init_annotations(tree: ast.AST, module_ns: dict):
    """Map attr_name -> resolved type object, from `self.x: T = ...`
    anywhere in the module (normally inside __init__)."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Attribute):
            if isinstance(node.target.value, ast.Name) and node.target.value.id == "self":
                try:
                    out[node.target.attr] = eval(  # noqa: S307 -- trusted first-party source
                        compile(ast.Expression(node.annotation), "<ann>", "eval"), module_ns
                    )
                except Exception:
                    _log.debug("world_data: couldn't resolve annotation for self.%s", node.target.attr)
    return out


def _auto_shape(app_name: str, session) -> dict:
    """Derive {json_key: spec} for `app_name` from its session module's own
    get_session_dict() + __init__ annotations. Cached per app."""
    if app_name in _AUTO_SHAPE_CACHE:
        return _AUTO_SHAPE_CACHE[app_name]

    shape = {}
    module = inspect.getmodule(type(session))
    try:
        src = inspect.getsource(module)
        tree = ast.parse(src)
        ret = _get_session_dict_return(tree)
        anns = _init_annotations(tree, vars(module))
        if ret is not None:
            for key_node, value_node in zip(ret.keys, ret.values):
                if not (isinstance(key_node, ast.Constant) and isinstance(key_node.value, str)):
                    continue
                key = key_node.value
                kind, attr = _classify(value_node)
                if kind == "scalar":
                    # Raw passthrough only -- anything needing a type
                    # conversion (dates, sets, ...) belongs in _SHAPES.
                    if attr:
                        shape[key] = ("scalar", lambda v: v, attr)
                    continue
                if not attr:
                    continue
                tp = anns.get(attr)
                elem_cls = None
                if tp is not None:
                    origin = typing.get_origin(tp)
                    args = typing.get_args(tp)
                    if origin in (dict,) and len(args) == 2:
                        elem_cls = args[1]
                    elif origin in (list, set) and args:
                        elem_cls = args[0]
                if tp is not None and origin is not None:
                    container_kind = "dict" if origin is dict else "list" if origin in (list, set) else None
                    if container_kind is not None and container_kind != kind:
                        # get_session_dict() exposes this as e.g. a list
                        # (list(self.x.values())) but self.x is actually a
                        # dict (or vice versa) -- round-tripping would need
                        # the dict key, which isn't recoverable from the
                        # dumped shape alone. Leave it un-hydrated rather
                        # than corrupt the attribute's real container type.
                        _log.warning(
                            "world_data: %s.%s dumps as %s but is stored as "
                            "%s -- skipping (can't round-trip the dict key)",
                            app_name, attr, kind, container_kind,
                        )
                        shape[key] = ("skip",)
                        continue
                if elem_cls is not None and dataclasses.is_dataclass(elem_cls):
                    shape[key] = (kind, elem_cls, attr)
                else:
                    # No resolvable dataclass element type (e.g. a plain
                    # List[str]/Dict[str,float]): raw passthrough is exact.
                    shape[key] = (kind, None, attr)
    except Exception:
        _log.warning("world_data: auto-shape derivation failed for %s", app_name, exc_info=True)

    _AUTO_SHAPE_CACHE[app_name] = shape
    return shape


def hydrate(session, app_name: str) -> bool:
    """Load ``<COMPLEXMCP_WORLD_DATA>/<app_name>.json`` onto ``session``,
    replacing each field the JSON declares. Returns True if a file was found
    and applied, False if world data isn't active for this run (or no file
    exists for this app -- e.g. LightSystem's is empty)."""
    d = active_dir()
    if not d:
        return False
    path = os.path.join(d, f"{app_name}.json")
    if not os.path.isfile(path):
        return False
    with open(path) as fh:
        data = json.load(fh)

    # Auto-derived shape is the base; hand-authored _SHAPES entries override
    # individual keys (renames, scalar coercions, aggregates) without
    # dropping the keys auto-derivation already gets right.
    shape = dict(_auto_shape(app_name, session))
    shape_fn = _SHAPES.get(app_name)
    if shape_fn:
        shape.update(shape_fn())

    for key, value in data.items():
        spec = shape.get(key)
        if spec is None:
            setattr(session, key, value)  # no declared shape: raw JSON as-is
            continue
        kind = spec[0]
        if kind == "skip":
            continue
        if kind == "fn":
            spec[1](session, value)
            continue
        if kind == "scalar":
            _, coerce_fn, attr_name = spec
            setattr(session, attr_name, coerce_fn(value))
            continue
        cls = spec[1]
        attr_name = spec[2] if len(spec) > 2 else key
        if kind == "dict" and isinstance(value, dict):
            setattr(session, attr_name, {k: _coerce(cls, v) for k, v in value.items()})
        elif kind == "list" and isinstance(value, list):
            setattr(session, attr_name, [_coerce(cls, v) for v in value])
        else:
            setattr(session, attr_name, value)

    post_fn = _POST_HYDRATE.get(app_name)
    if post_fn:
        post_fn(session)
    return True
