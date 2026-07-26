"""Tests for the engine launcher (app/process_runner.py).

No real winws.exe is ever started: subprocess.Popen is replaced by a fake
process, so the tests can check the things that used to go wrong in real use --
the exact command line, output capture, the "engine died on its own" report
(which must NOT fire when the user stopped it), and the fact that only our own
process tree is killed, never every winws on the machine.
"""
import logging
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from app import applog
from app.process_runner import ProcessRunner


class _Strategy:
    def __init__(self, name="test strategy", args=None):
        self.name = name
        self.args = list(args or ["--wf-tcp=80,443"])


class _Stream:
    """Fake stdout: yields the given lines, then optionally blocks on a gate."""

    def __init__(self, lines, gate=None):
        self._lines = list(lines)
        self._gate = gate

    def __iter__(self):
        for line in self._lines:
            yield line
        if self._gate is not None:
            self._gate.wait(5)


class _FakeProc:
    def __init__(self, lines=(), exit_code=0, gate=None, hang_on_wait=False):
        self.pid = 4242
        self.stdout = _Stream(lines, gate)
        self._code = exit_code
        self._finished = False
        self.hang_on_wait = hang_on_wait
        self.terminated = False
        self.killed = False

    def poll(self):
        return self._code if self._finished else None

    def wait(self, timeout=None):
        if self.hang_on_wait and not self.killed:
            raise subprocess.TimeoutExpired(cmd="winws.exe", timeout=timeout)
        self._finished = True
        return self._code

    def terminate(self):
        self.terminated = True
        if not self.hang_on_wait:
            self._finished = True

    def kill(self):
        self.killed = True
        self._finished = True


class _RunnerCase(unittest.TestCase):
    """Shared setup: a fake winws.exe on disk and a throwaway log file."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.winws = self.dir / "bin" / "winws.exe"
        self.winws.parent.mkdir(parents=True, exist_ok=True)
        self.winws.write_text("not a real exe", encoding="utf-8")
        # Keep engine chatter out of the user's real log file.
        applog.setup(directory=self.dir / "logs")
        self.addCleanup(self._cleanup)
        self.killed_commands = []
        run_patch = mock.patch("app.process_runner.subprocess.run")
        self.run_mock = run_patch.start()
        self.run_mock.side_effect = lambda args, **kw: self.killed_commands.append(
            list(args)
        )
        self.addCleanup(run_patch.stop)

    def _cleanup(self):
        root = logging.getLogger(applog.LOGGER_NAME)
        for handler in list(root.handlers):
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
        self._tmp.cleanup()

    def _runner(self, **kw):
        self.lines = []
        kw.setdefault("log_cb", self.lines.append)
        return ProcessRunner(self.winws, **kw)

    def _start(self, runner, proc, strategy=None):
        with mock.patch("app.process_runner.subprocess.Popen", return_value=proc) as popen:
            pid = runner.start(strategy or _Strategy())
        self.popen = popen
        return pid

    def _join_reader(self, runner):
        if runner._reader is not None:
            runner._reader.join(timeout=5)
            self.assertFalse(runner._reader.is_alive())


class StartTests(_RunnerCase):

    def test_command_is_the_engine_plus_strategy_arguments(self):
        runner = self._runner()
        proc = _FakeProc()
        pid = self._start(runner, proc, _Strategy("basic", ["--wf-tcp=80", "--dpi-desync=fake"]))
        self._join_reader(runner)
        args, kwargs = self.popen.call_args
        self.assertEqual(args[0], [str(self.winws), "--wf-tcp=80", "--dpi-desync=fake"])
        # Launched from the engine folder so its relative lists resolve.
        self.assertEqual(kwargs["cwd"], str(self.winws.parent))
        self.assertEqual(kwargs["stderr"], subprocess.STDOUT)
        self.assertEqual(pid, 4242)

    def test_missing_engine_is_reported_clearly(self):
        runner = ProcessRunner(self.dir / "bin" / "absent.exe")
        with self.assertRaises(FileNotFoundError) as ctx:
            runner.start(_Strategy())
        self.assertIn("winws.exe", str(ctx.exception))

    def test_launch_failure_is_logged_and_raised(self):
        runner = self._runner()
        with mock.patch(
            "app.process_runner.subprocess.Popen", side_effect=OSError("denied")
        ):
            with self.assertRaises(OSError):
                runner.start(_Strategy())
        self.assertTrue(any("denied" in line for line in self.lines))
        self.assertFalse(runner.is_running())

    def test_exclusion_filter_is_applied(self):
        runner = self._runner(args_filter=lambda args: args + ["--exclude=vk.com"])
        self._start(runner, _FakeProc())
        self._join_reader(runner)
        self.assertIn("--exclude=vk.com", self.popen.call_args[0][0])

    def test_broken_exclusion_filter_does_not_block_the_launch(self):
        def boom(_args):
            raise ValueError("bad exclusion list")

        runner = self._runner(args_filter=boom)
        self._start(runner, _FakeProc(), _Strategy("basic", ["--wf-tcp=80"]))
        self._join_reader(runner)
        # Original arguments survive and the problem is visible in the log.
        self.assertEqual(self.popen.call_args[0][0], [str(self.winws), "--wf-tcp=80"])
        self.assertTrue(any("bad exclusion list" in line for line in self.lines))

    def test_starting_again_replaces_the_previous_engine(self):
        runner = self._runner()
        first = _FakeProc(gate=threading.Event())
        self._start(runner, first)
        second = _FakeProc()
        self._start(runner, second)
        self.assertTrue(first.terminated)
        self.assertIs(runner._proc, second)

    def test_running_strategy_is_remembered(self):
        runner = self._runner()
        strategy = _Strategy("my strategy")
        self._start(runner, _FakeProc(gate=threading.Event()), strategy)
        self.assertTrue(runner.is_running())
        self.assertIs(runner.current_strategy, strategy)


class OutputTests(_RunnerCase):

    def test_engine_output_is_captured_and_shown(self):
        runner = self._runner()
        self._start(runner, _FakeProc(lines=["windivert initialized\n", "\n", "capture started\n"]))
        self._join_reader(runner)
        self.assertIn("windivert initialized", runner.last_output())
        self.assertIn("capture started", runner.last_output())
        # Blank lines are dropped instead of padding the log view.
        self.assertEqual(len(runner.last_output().splitlines()), 2)
        self.assertIn("windivert initialized", self.lines)

    def test_only_the_last_300_lines_are_kept(self):
        runner = self._runner()
        self._start(runner, _FakeProc(lines=["line %d\n" % i for i in range(400)]))
        self._join_reader(runner)
        kept = runner.last_output().splitlines()
        self.assertEqual(len(kept), 300)
        self.assertEqual(kept[0], "line 100")
        self.assertEqual(kept[-1], "line 399")

    def test_output_is_cleared_on_restart(self):
        runner = self._runner()
        self._start(runner, _FakeProc(lines=["old line\n"]))
        self._join_reader(runner)
        self._start(runner, _FakeProc(lines=["new line\n"]))
        self._join_reader(runner)
        self.assertNotIn("old line", runner.last_output())
        self.assertIn("new line", runner.last_output())


class UnexpectedExitTests(_RunnerCase):

    def test_engine_dying_on_its_own_is_reported(self):
        seen = []
        runner = self._runner(on_exit=lambda code, out: seen.append((code, out)))
        self._start(runner, _FakeProc(lines=["windivert error\n"], exit_code=1))
        self._join_reader(runner)
        self.assertEqual(len(seen), 1)
        code, out = seen[0]
        self.assertEqual(code, 1)
        self.assertIn("windivert error", out)
        self.assertTrue(any("1" in line and "winws.exe" in line for line in self.lines))

    def test_user_initiated_stop_is_not_reported_as_a_crash(self):
        seen = []
        gate = threading.Event()
        runner = self._runner(on_exit=lambda code, out: seen.append(code))
        self._start(runner, _FakeProc(lines=["working\n"], gate=gate))
        runner.stop()
        gate.set()
        self._join_reader(runner)
        self.assertEqual(seen, [])

    def test_a_broken_exit_callback_does_not_kill_the_reader(self):
        def boom(_code, _out):
            raise RuntimeError("window already closed")

        runner = self._runner(on_exit=boom)
        self._start(runner, _FakeProc(exit_code=2))
        self._join_reader(runner)  # must finish, not hang or crash


class StopTests(_RunnerCase):

    def test_stop_terminates_and_forgets_the_engine(self):
        runner = self._runner()
        proc = _FakeProc(gate=threading.Event())
        self._start(runner, proc)
        runner.stop()
        self.assertTrue(proc.terminated)
        self.assertFalse(runner.is_running())
        self.assertIsNone(runner.current_strategy)

    def test_a_hanging_engine_is_force_killed(self):
        runner = self._runner()
        proc = _FakeProc(gate=threading.Event(), hang_on_wait=True)
        self._start(runner, proc)
        runner.stop()
        self.assertTrue(proc.killed)

    def test_stop_kills_only_our_own_process_tree(self):
        runner = self._runner()
        self._start(runner, _FakeProc(gate=threading.Event()))
        runner.stop()
        self.assertIn(["taskkill", "/F", "/T", "/PID", "4242"], self.killed_commands)
        # The broad sweep would also kill the Windows service: never automatic.
        self.assertFalse(
            any("/IM" in cmd for cmd in self.killed_commands),
            "stop() must not kill every winws.exe",
        )

    def test_stop_is_safe_when_nothing_is_running(self):
        runner = self._runner()
        runner.stop()
        self.assertFalse(runner.is_running())
        self.assertEqual(self.killed_commands, [])

    def test_explicit_cleanup_sweeps_every_engine(self):
        runner = self._runner()
        runner.kill_all_winws()
        self.assertEqual(
            self.killed_commands, [["taskkill", "/F", "/IM", "winws.exe", "/T"]]
        )


if __name__ == "__main__":
    unittest.main()
