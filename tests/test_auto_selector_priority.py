"""Tests for the auto-selector speed-ups: ordering and the deep-stage cap."""
import unittest
from pathlib import Path

from app.auto_selector import AutoSelector, prioritize
from app.strategy_manager import Strategy


def _strat(name):
    return Strategy(name=name, source_file=Path(name + ".bat"), args=["--wf-tcp=443"])


class _FakeRunner:
    """Minimal ProcessRunner stand-in: records starts, never touches WinDivert."""

    def __init__(self):
        self.started = []
        self.logs = []

    def start(self, strat):
        self.started.append(strat.name)

    def stop(self):
        pass

    def log(self, msg):
        self.logs.append(msg)


class _Res:
    """Stands in for connectivity CheckResult / DeepResult."""

    def __init__(self, discord=True, youtube=True, score=1.0, ok=False, latency_ms=10.0):
        self.discord = discord
        self.youtube = youtube
        self.score = score
        self.ok = ok
        self.latency_ms = latency_ms
        self.detail = "test"


class PrioritizeTests(unittest.TestCase):

    def test_last_working_goes_first(self):
        strategies = [_strat("A"), _strat("B"), _strat("C")]
        ordered = prioritize(strategies, last_working="C")
        self.assertEqual([s.name for s in ordered], ["C", "A", "B"])

    def test_preferred_order_follows_last_working(self):
        strategies = [_strat("A"), _strat("B"), _strat("C"), _strat("D")]
        ordered = prioritize(strategies, last_working="D", preferred_order=["B", "A"])
        self.assertEqual([s.name for s in ordered], ["D", "B", "A", "C"])

    def test_nothing_is_dropped_or_duplicated(self):
        strategies = [_strat("A"), _strat("B"), _strat("C")]
        ordered = prioritize(strategies, last_working="B", preferred_order=["B", "ghost"])
        self.assertEqual(sorted(s.name for s in ordered), ["A", "B", "C"])

    def test_unknown_hints_are_ignored(self):
        strategies = [_strat("A"), _strat("B")]
        ordered = prioritize(strategies, last_working="missing", preferred_order=["nope"])
        self.assertEqual([s.name for s in ordered], ["A", "B"])

    def test_empty_input(self):
        self.assertEqual(prioritize([], last_working="A"), [])


class DeepStageCapTests(unittest.TestCase):

    def _selector(self, runner, cap):
        sel = AutoSelector(
            runner,
            warmup_seconds=0.0,
            timeout=0.1,
            freeze_seconds=0.1,
            working_freeze_seconds=0.1,
            attempts=1,
            enable_voice=False,
            stall_timeout=0.1,
            max_deep_candidates=cap,
        )
        sel._cooldown = lambda: None
        return sel

    def test_deep_stage_is_capped_to_the_best_candidates(self):
        runner = _FakeRunner()
        sel = self._selector(runner, cap=2)
        strategies = [_strat(n) for n in ("A", "B", "C", "D")]
        # Quick stage: everything reaches Discord, with different latencies.
        latencies = {"A": 300.0, "B": 10.0, "C": 200.0, "D": 20.0}
        current = {"name": None}

        def fake_start(strat):
            current["name"] = strat.name
            runner.started.append(strat.name)

        runner.start = fake_start
        sel._quick = lambda: _Res(latency_ms=latencies[current["name"]])

        deep_seen = []

        def fake_deep(freeze_seconds, attempts):
            deep_seen.append(current["name"])
            return _Res(ok=True, score=5.0)

        sel._deep = fake_deep
        result = sel.run(strategies, mode="best")

        # Only the cap is deep-checked, and it keeps the two fastest.
        self.assertEqual(len(deep_seen), 2)
        self.assertEqual(sorted(deep_seen), ["B", "D"])
        self.assertIsNotNone(result.strategy)

    def test_no_cap_when_disabled(self):
        runner = _FakeRunner()
        sel = self._selector(runner, cap=0)
        strategies = [_strat(n) for n in ("A", "B", "C")]
        sel._quick = lambda: _Res()
        deep_calls = {"n": 0}

        def fake_deep(freeze_seconds, attempts):
            deep_calls["n"] += 1
            return _Res(ok=True, score=1.0)

        sel._deep = fake_deep
        sel.run(strategies, mode="best")
        self.assertEqual(deep_calls["n"], 3)

    def test_working_mode_respects_priority_hint(self):
        runner = _FakeRunner()
        sel = self._selector(runner, cap=8)
        strategies = [_strat(n) for n in ("A", "B", "C")]
        sel._quick = lambda: _Res()
        sel._deep = lambda freeze_seconds, attempts: _Res(ok=True, score=9.0)
        result = sel.run(strategies, mode="working", last_working="C")
        # First strategy tried must be the one that worked last time, and the
        # sweep stops right there.
        self.assertEqual(runner.started[0], "C")
        self.assertEqual(result.strategy.name, "C")
        self.assertEqual(result.tested, 1)

    def test_cancel_before_start_returns_cancelled(self):
        runner = _FakeRunner()
        sel = self._selector(runner, cap=8)
        strategies = [_strat("A")]
        sel._quick = lambda: _Res()
        sel._deep = lambda freeze_seconds, attempts: _Res(ok=True)

        original_warmup = sel._warmup

        def cancel_during_warmup():
            sel.cancel()
            return original_warmup()

        sel._warmup = cancel_during_warmup
        result = sel.run(strategies, mode="working")
        self.assertTrue(result.cancelled)


if __name__ == "__main__":
    unittest.main()
