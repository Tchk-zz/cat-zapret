"""Sequentially try strategies to find a working (or the best) one.

Two modes:
  * "working" -- stop at the first strategy that genuinely passes (base +
                 short freeze + Discord voice). Fast.
  * "best"    -- two stages: a quick filter over every strategy, then a deep
                 check (freeze, throughput, stability, voice) on the survivors,
                 keeping the highest-scoring one.

If nothing fully passes, the best partial result is returned instead of
nothing, so the sweep never says "nothing found" when something improved.

Runs on a worker thread (see ui.workers) so the UI stays responsive.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from . import connectivity
from .process_runner import ProcessRunner
from .strategy_manager import Strategy


@dataclass
class AutoSelectResult:
    strategy: Optional[Strategy]
    tested: int
    total: int
    cancelled: bool = False
    partial: bool = False
    detail: str = ""
    latency_ms: Optional[float] = None
    mode: str = "working"


ProgressCb = Callable[[int, int, Strategy, str], None]


class AutoSelector:
    def __init__(
        self,
        runner: ProcessRunner,
        warmup_seconds: float = 3.0,
        timeout: float = 6.0,
        freeze_seconds: float = 16.0,
        working_freeze_seconds: float = 6.0,
        attempts: int = 3,
        enable_voice: bool = True,
        stall_timeout: float = 4.0,
    ):
        self.runner = runner
        self.warmup_seconds = warmup_seconds
        self.timeout = timeout
        self.freeze_seconds = freeze_seconds
        self.working_freeze_seconds = working_freeze_seconds
        self.attempts = attempts
        self.enable_voice = enable_voice
        self.stall_timeout = stall_timeout
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    # --- helpers ----------------------------------------------------------
    def _warmup(self) -> bool:
        """Wait for the engine to settle. Returns False if cancelled.

        Uses Event.wait() instead of a sleep loop, so pressing "Отмена"
        aborts within microseconds instead of up to a quarter of a second.
        """
        return not self._cancel.wait(self.warmup_seconds)

    def _restart(self, strat: Strategy) -> None:
        try:
            self.runner.start(strat)
        except Exception as exc:  # noqa: BLE001
            self.runner.log(f"[auto] failed to re-start {strat.name}: {exc}")

    def _deep(self, freeze_seconds: float, attempts: int):
        return connectivity.deep_check(
            timeout=self.timeout,
            freeze_seconds=freeze_seconds,
            attempts=attempts,
            enable_voice=self.enable_voice,
            stall_timeout=self.stall_timeout,
            cancel=self._cancel,
        )

    def _quick(self):
        """Cheap reachability pass used to skip hopeless strategies early."""
        return connectivity.check(self.timeout, cancel=self._cancel)

    def _cooldown(self) -> None:
        self.runner.stop()
        # Let WinDivert fully release before the next strategy binds.
        # Interruptible so cancelling doesn't add 0.4 s per remaining step.
        self._cancel.wait(0.4)

    # --- entry point ------------------------------------------------------
    def run(
        self,
        strategies: List[Strategy],
        on_progress: Optional[ProgressCb] = None,
        mode: str = "working",
    ) -> AutoSelectResult:
        self._cancel.clear()
        on_progress = on_progress or (lambda *_: None)
        if mode == "best":
            return self._run_best(strategies, on_progress)
        return self._run_working(strategies, on_progress)

    # --- working mode -----------------------------------------------------
    def _run_working(self, strategies, on_progress) -> AutoSelectResult:
        total = len(strategies)
        best_partial = None  # (strat, score, latency, detail)
        for idx, strat in enumerate(strategies, start=1):
            if self._cancel.is_set():
                self.runner.stop()
                return AutoSelectResult(None, idx - 1, total, cancelled=True, mode="working")
            on_progress(idx, total, strat, "запуск")
            try:
                self.runner.start(strat)
            except Exception as exc:  # noqa: BLE001
                self.runner.log(f"[auto] {strat.name} failed to start: {exc}")
                continue
            if not self._warmup():
                self.runner.stop()
                return AutoSelectResult(None, idx, total, cancelled=True, mode="working")
            # Cheap gate first: a strategy that can't even reach Discord will
            # never pass the deep check, so don't spend the whole freeze window
            # on it. This is what turned a ~30-minute sweep into a few minutes
            # on heavily-filtered connections.
            on_progress(idx, total, strat, "быстрая проверка")
            quick = self._quick()
            if self._cancel.is_set():
                self.runner.stop()
                return AutoSelectResult(None, idx, total, cancelled=True, mode="working")
            if not quick.discord:
                self.runner.log(f"[auto] {strat.name}: {quick.detail} — пропуск")
                if quick.youtube and (best_partial is None or best_partial[1] < 1):
                    best_partial = (strat, 1, quick.latency_ms, quick.detail)
                self._cooldown()
                continue
            on_progress(idx, total, strat, "проверка")
            res = self._deep(self.working_freeze_seconds, 1)
            self.runner.log(f"[auto] {strat.name}: {res.detail}")
            if res.ok:
                on_progress(idx, total, strat, "успех")
                return AutoSelectResult(
                    strat, idx, total, detail=res.detail,
                    latency_ms=res.latency_ms, mode="working",
                )
            if res.score > 0:
                cand = (strat, res.score, res.latency_ms, res.detail)
                if best_partial is None or cand[1] > best_partial[1]:
                    best_partial = cand
            self._cooldown()
        if best_partial is not None:
            strat, _score, lat, detail = best_partial
            self._restart(strat)
            return AutoSelectResult(
                strat, total, total, partial=True, detail=detail,
                latency_ms=lat, mode="working",
            )
        return AutoSelectResult(None, total, total, mode="working")

    # --- best mode (two-stage) -------------------------------------------
    def _run_best(self, strategies, on_progress) -> AutoSelectResult:
        total = len(strategies)
        candidates: List[Strategy] = []
        best_partial = None  # (strat, score, latency, detail) from quick stage

        # Stage 1: quick filter over every strategy.
        for idx, strat in enumerate(strategies, start=1):
            if self._cancel.is_set():
                self.runner.stop()
                return AutoSelectResult(None, idx - 1, total, cancelled=True, mode="best")
            on_progress(idx, total, strat, "быстрый отбор")
            try:
                self.runner.start(strat)
            except Exception as exc:  # noqa: BLE001
                self.runner.log(f"[auto] {strat.name} failed to start: {exc}")
                continue
            if not self._warmup():
                self.runner.stop()
                return AutoSelectResult(None, idx, total, cancelled=True, mode="best")
            q = self._quick()
            self.runner.log(f"[auto] {strat.name}: {q.detail}")
            if q.discord:
                candidates.append(strat)
            elif q.score > 0:
                cand = (strat, q.score, q.latency_ms, q.detail)
                if best_partial is None or cand[1] > best_partial[1]:
                    best_partial = cand
            self._cooldown()

        if not candidates:
            if best_partial is not None:
                strat, _s, lat, detail = best_partial
                self._restart(strat)
                return AutoSelectResult(
                    strat, total, total, partial=True, detail=detail,
                    latency_ms=lat, mode="best",
                )
            return AutoSelectResult(None, total, total, mode="best")

        # Stage 2: deep check on the survivors; keep the highest score.
        best_deep = None  # (strat, score, ok, latency, detail)
        m = len(candidates)
        for j, strat in enumerate(candidates, start=1):
            if self._cancel.is_set():
                self.runner.stop()
                return AutoSelectResult(None, j - 1, m, cancelled=True, mode="best")
            on_progress(j, m, strat, "глубокая проверка")
            try:
                self.runner.start(strat)
            except Exception as exc:  # noqa: BLE001
                self.runner.log(f"[auto] {strat.name} failed to start: {exc}")
                continue
            if not self._warmup():
                self.runner.stop()
                return AutoSelectResult(None, j, m, cancelled=True, mode="best")
            on_progress(j, m, strat, "скорость / фриз / голос")
            res = self._deep(self.freeze_seconds, self.attempts)
            self.runner.log(f"[auto] {strat.name} [{res.score:.0f}]: {res.detail}")
            cand = (strat, res.score, res.ok, res.latency_ms, res.detail)
            if best_deep is None or res.score > best_deep[1]:
                best_deep = cand
            self._cooldown()

        if best_deep is not None:
            strat, _score, ok, lat, detail = best_deep
            self._restart(strat)
            return AutoSelectResult(
                strat, m, m, partial=not ok, detail=detail,
                latency_ms=lat, mode="best",
            )
        if best_partial is not None:
            strat, _s, lat, detail = best_partial
            self._restart(strat)
            return AutoSelectResult(
                strat, total, total, partial=True, detail=detail,
                latency_ms=lat, mode="best",
            )
        return AutoSelectResult(None, total, total, mode="best")
