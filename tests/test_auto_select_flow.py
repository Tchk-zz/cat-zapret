"""Regression tests for :mod:`ui.auto_select_flow`.

The auto-select flow used to sit in the middle of ``ui/main_window.py`` and had
no direct coverage: the GUI smoke tests build a window but never run a sweep.
These tests pin the parts that are easy to break while refactoring:

* the three button states ('idle' / 'choices' / 'running'),
* the dark-theme Home swap, including the promise that the cat emotion changes
  exactly once per transition,
* the fact that a non-dark theme never shows the dark panel,
* cancellation, and
* deferring the result until the waiting mini-game round is over.

The mixin is exercised through a tiny host object with stub widgets instead of a
real ``MainWindow``. That keeps the test fast and, more importantly, makes it
fail for the right reason: a change in the flow's logic, not in unrelated Qt
wiring.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from ui import auto_select_flow as flow_mod  # noqa: E402
from ui.auto_select_flow import AutoSelectFlowMixin  # noqa: E402


class _Widget:
    """Minimal stand-in for the Qt widgets the flow toggles."""

    def __init__(self, visible: bool = True) -> None:
        self.visible = bool(visible)
        self.raised = 0
        self.fixed_height: int | None = None
        self.messages: list[str] = []

    def setVisible(self, value: bool) -> None:
        self.visible = bool(value)

    def isVisible(self) -> bool:
        return self.visible

    def raise_(self) -> None:
        self.raised += 1

    def setFixedHeight(self, value: int) -> None:
        self.fixed_height = int(value)

    def set_message(self, text: str) -> None:
        self.messages.append(text)


class _Label(_Widget):
    def __init__(self) -> None:
        super().__init__()
        self.text = "unset"

    def setText(self, value: str) -> None:
        self.text = value


class _Game(_Widget):
    def __init__(self) -> None:
        super().__init__()
        self.searching: bool | None = None
        self.playing = False

    def set_searching(self, value: bool) -> None:
        self.searching = bool(value)

    def is_user_playing(self) -> bool:
        return self.playing


class _SleepZ(_Widget):
    def __init__(self) -> None:
        super().__init__()
        self.sleeping: bool | None = None

    def set_sleeping(self, value: bool) -> None:
        self.sleeping = bool(value)


class _Runner:
    def __init__(self, running: bool = False) -> None:
        self._running = running

    def is_running(self) -> bool:
        return self._running


class _Worker:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class _Host(AutoSelectFlowMixin):
    """Carries only the state the auto-select flow actually touches."""

    def __init__(self, theme: str = "dark", running: bool = False) -> None:
        self.current_theme = theme
        self.runner = _Runner(running)
        self.home_auto_stack = _Widget(visible=False)
        self.home_auto_panel = _Widget(visible=False)
        self.home_runner_card = _Widget(visible=False)
        self.waiting_runner_game = _Game()
        self.home_right_top_spacer = _Widget()
        self.home_tg_card = _Widget()
        self.home_zap_card = _Widget()
        self.btn_auto = _Widget()
        self.btn_check = _Widget()
        self.btn_auto_best = _Widget()
        self.btn_auto_work = _Widget()
        self.btn_auto_cancel = _Widget()
        self.home_cat = _Widget()
        self.sleep_z = _SleepZ()
        self.progress_label = _Label()
        self.frames: list[str] = []
        self.finished_with: list[object] = []
        self._home_cat_auto_active = False
        self._pending_auto_result = None
        self._auto_popup = None
        self._auto_worker = None
        self._auto_popup_closing = False

    def _set_home_cat_frame(self, frame: str) -> bool:
        self.frames.append(frame)
        return True

    def _on_auto_finished(self, result: object) -> None:
        # The real implementation needs a live window; the deferral test only
        # cares that the pending result is handed over exactly once.
        self.finished_with.append(result)


@pytest.fixture
def immediate_single_shot(monkeypatch):
    """Capture ``QTimer.singleShot`` calls instead of needing an event loop."""
    calls: list[tuple[int, object]] = []

    def fake_single_shot(msec, callback):
        calls.append((msec, callback))

    monkeypatch.setattr(flow_mod.QTimer, "singleShot", fake_single_shot)
    return calls


def test_running_state_hides_every_auto_button():
    host = _Host()
    host._set_auto_buttons("running")
    assert host.btn_auto.visible is False
    assert host.btn_check.visible is False
    assert host.btn_auto_best.visible is False
    assert host.btn_auto_work.visible is False
    assert host.btn_auto_cancel.visible is False


def test_choices_state_shows_best_and_working():
    host = _Host()
    host._set_auto_buttons("choices")
    assert host.btn_auto.visible is True
    assert host.btn_check.visible is True
    assert host.btn_auto_best.visible is True
    assert host.btn_auto_work.visible is True
    assert host.btn_auto_cancel.visible is False


def test_idle_state_shows_only_the_two_main_actions():
    host = _Host()
    host._set_auto_buttons("choices")
    host._set_auto_buttons("idle")
    assert host.btn_auto.visible is True
    assert host.btn_check.visible is True
    assert host.btn_auto_best.visible is False
    assert host.btn_auto_work.visible is False


def test_dark_panel_activation_swaps_home_content():
    host = _Host(theme="dark")

    host._set_dark_auto_panel_active(True)

    assert host.home_auto_stack.visible is True
    assert host.home_auto_stack.raised == 1
    assert host.home_auto_panel.visible is True
    assert host.home_runner_card.visible is True
    assert host.waiting_runner_game.searching is True
    assert host.home_right_top_spacer.fixed_height == 100
    # The idle cards and actions must give way to the search panel.
    assert host.home_tg_card.visible is False
    assert host.home_zap_card.visible is False
    assert host.btn_auto.visible is False
    assert host.btn_check.visible is False
    # Cat wakes up and starts searching.
    assert host.frames == ["search"]
    assert host.sleep_z.sleeping is False
    assert host._home_cat_auto_active is True


def test_dark_panel_deactivation_restores_idle_home_and_sleepy_cat():
    host = _Host(theme="dark", running=False)
    host._set_dark_auto_panel_active(True)

    host._set_dark_auto_panel_active(False)

    assert host.home_auto_stack.visible is False
    assert host.home_auto_panel.visible is False
    assert host.home_runner_card.visible is False
    assert host.waiting_runner_game.searching is False
    assert host.home_tg_card.visible is True
    assert host.home_zap_card.visible is True
    assert host.btn_auto.visible is True
    assert host.btn_check.visible is True
    # Engine is stopped, so the cat goes back to sleep with closed eyes.
    assert host.frames == ["search", "closed"]
    assert host.sleep_z.sleeping is True
    assert host._home_cat_auto_active is False


def test_dark_panel_deactivation_keeps_cat_awake_while_engine_runs():
    host = _Host(theme="dark", running=True)
    host._set_dark_auto_panel_active(True)

    host._set_dark_auto_panel_active(False)

    assert host.frames == ["search", "open"]
    assert host.sleep_z.sleeping is False


def test_repeated_activation_switches_the_cat_only_once():
    host = _Host(theme="dark")

    host._set_dark_auto_panel_active(True)
    host._set_dark_auto_panel_active(True)

    assert host.frames == ["search"]
    assert host.sleep_z.sleeping is False


def test_non_dark_theme_never_shows_the_dark_panel():
    host = _Host(theme="purple")

    host._set_dark_auto_panel_active(True)

    assert host.home_auto_stack.visible is False
    assert host.home_auto_panel.visible is False
    assert host.home_runner_card.visible is False
    assert host.waiting_runner_game.searching is False
    # Light/image themes keep their own cards and never touch the cat.
    assert host.home_tg_card.visible is True
    assert host.btn_auto.visible is True
    assert host.frames == []
    assert host._home_cat_auto_active is False


def test_cancel_stops_the_worker_and_reports_in_both_surfaces():
    host = _Host(theme="dark")
    host._auto_worker = _Worker()
    host._auto_popup = _Widget(visible=True)
    host.home_auto_panel.visible = True

    host._cancel_auto_select()

    assert host._auto_worker.cancelled is True
    assert host._auto_popup.messages == ["Отмена..."]
    assert host.home_auto_panel.messages == ["Отмена..."]
    assert host.progress_label.text == ""


def test_cancel_is_ignored_while_the_popup_is_already_closing():
    host = _Host(theme="dark")
    host._auto_worker = _Worker()
    host._auto_popup_closing = True

    host._cancel_auto_select()

    assert host._auto_worker.cancelled is False


def test_progress_updates_reach_popup_panel_and_tray():
    class _Tray:
        def __init__(self) -> None:
            self.states: list[tuple[str, str]] = []

        def set_state(self, state: str, text: str) -> None:
            self.states.append((state, text))

    class _Panel(_Widget):
        def __init__(self) -> None:
            super().__init__(visible=True)
            self.progress: list[tuple[int, int, str, str]] = []

        def update_progress(self, idx, total, name, phase) -> None:
            self.progress.append((idx, total, name, phase))

    host = _Host(theme="dark")
    host.tray = _Tray()
    host._auto_popup = _Panel()
    host.home_auto_panel = _Panel()

    host._on_auto_progress(2, 7, "strategy", "deep")

    assert host._auto_popup.progress == [(2, 7, "strategy", "deep")]
    assert host.home_auto_panel.progress == [(2, 7, "strategy", "deep")]
    assert host.tray.states == [("working", "подбор...")]
    assert host.progress_label.text == ""


def test_round_end_hands_the_deferred_result_over_once(immediate_single_shot):
    host = _Host(theme="dark")
    sentinel = object()
    host._pending_auto_result = sentinel

    host._on_waiting_runner_round_ended()

    # The result is cleared immediately so a second round cannot replay it.
    assert host._pending_auto_result is None
    assert len(immediate_single_shot) == 1
    delay, callback = immediate_single_shot[0]
    assert delay == 400
    callback()
    assert host.finished_with == [sentinel]

    host._on_waiting_runner_round_ended()
    assert len(immediate_single_shot) == 1


def test_round_end_without_a_pending_result_does_nothing(immediate_single_shot):
    host = _Host(theme="dark")

    host._on_waiting_runner_round_ended()

    assert immediate_single_shot == []
    assert host.finished_with == []
