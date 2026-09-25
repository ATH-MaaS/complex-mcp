"""Regression tests for the identifiers ``judge_env`` is meant to ignore.

``exclude_keys`` is a set literal, and Python concatenates adjacent string literals
before the set is built. A missing separator after ``"rid"`` therefore collapses
``"rid"`` and ``"oid"`` into the single member ``"ridoid"``, so neither identifier is
ignored and an environment-generated id is scored as if it were a user-visible change.

Intended behaviour, pinned here:

* a state that differs from the ground truth only in ``rid`` / ``oid`` is not a
  misbehaviour and not a target;
* ids must not inflate the ``total`` / ``recall`` denominators either;
* ordinary fields are still scored, so the fix does not make the judge lax.

Run from the repository root::

    python -m unittest discover -s tests
"""

import unittest

from benchmark.judge import exclude_keys, judge_env


def flight_env(rid, status="confirmed"):
    return {"LightFlight": {"reservations": [{"rid": rid, "from": "SFO", "to": "JFK", "status": status}]}}


def stock_env(oid, count=20):
    return {"LightStock": {"orders": [{"oid": oid, "symbol": "NKE", "count": count}]}}


class ExcludeKeysTest(unittest.TestCase):
    def test_generated_identifiers_are_members(self):
        self.assertIn("rid", exclude_keys)
        self.assertIn("oid", exclude_keys)

    def test_no_concatenated_member(self):
        self.assertNotIn("ridoid", exclude_keys)


class RidTest(unittest.TestCase):
    def test_only_rid_changed_is_not_scored(self):
        result = judge_env(flight_env("reservation-1"), flight_env("reservation-2"), flight_env("reservation-1"))
        self.assertEqual(result, {"total": 0, "recall": 0, "misbehave": 0})

    def test_rid_does_not_inflate_the_denominator(self):
        old = flight_env("reservation-1")
        gt = flight_env("reservation-9", status="cancelled")
        new = flight_env("reservation-9", status="cancelled")
        result = judge_env(old, new, gt)
        self.assertEqual(result, {"total": 1, "recall": 1, "misbehave": 0})
        self.assertEqual(result["total"], 1, "only the status change is a target; the id must not be counted")


class OidTest(unittest.TestCase):
    def test_only_oid_changed_is_not_scored(self):
        result = judge_env(stock_env("order-1"), stock_env("order-2"), stock_env("order-1"))
        self.assertEqual(result, {"total": 0, "recall": 0, "misbehave": 0})

    def test_oid_does_not_inflate_the_denominator(self):
        old = stock_env("order-1", count=10)
        gt = stock_env("order-7", count=20)
        new = stock_env("order-7", count=20)
        result = judge_env(old, new, gt)
        self.assertEqual(result, {"total": 1, "recall": 1, "misbehave": 0})


class OrdinaryFieldsStillScoredTest(unittest.TestCase):
    def test_wrong_status_on_an_untouched_field_is_misbehaviour(self):
        old = flight_env("reservation-1")
        gt = flight_env("reservation-1")
        new = flight_env("reservation-1", status="cancelled")
        self.assertEqual(judge_env(old, new, gt)["misbehave"], 1)

    def test_unreached_target_is_counted(self):
        old = stock_env("order-1", count=10)
        gt = stock_env("order-1", count=20)
        new = stock_env("order-1", count=10)
        self.assertEqual(judge_env(old, new, gt), {"total": 1, "recall": 0, "misbehave": 0})


if __name__ == "__main__":
    unittest.main()
