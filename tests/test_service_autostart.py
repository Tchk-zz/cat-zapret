"""Tests for autostart (app/autostart.py) and the Windows service (app/service_manager.py).

Both modules shell out to Windows tools (schtasks, sc, the registry), so the
tests never let a real command run: every subprocess call is replaced by a
recorder. What is verified is the part that actually broke for users before --
the exact command line built, the fallback when Task Scheduler refuses, the
order of "stop our own engine" vs "start the service", and the status cache
that used to make the window lag.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import autostart
from app.service_manager import SERVICE_NAME, ServiceManager


def _done(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class _Recorder:
    """Stands in for subprocess.run and remembers every command."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.calls = []
        self.result = _done(returncode, stdout, stderr)

    def __call__(self, args, **kwargs):
        self.calls.append((list(args), kwargs))
        return self.result

    def commands(self):
        return [args for args, _kw in self.calls]


class AutostartCommandTests(unittest.TestCase):

    def test_command_points_at_the_app(self):
        cmd = autostart._exe_command(minimized=False)
        self.assertIn(sys.executable, cmd)
        self.assertIn("main.py", cmd)
        # Paths must be quoted: "C:\Program Files\..." contains spaces.
        self.assertTrue(cmd.startswith('"'))
        self.assertNotIn("--minimized", cmd)

    def test_minimized_flag_is_added(self):
        self.assertTrue(
            autostart._exe_command(minimized=True).endswith(" --minimized")
        )


class AutostartEnableTests(unittest.TestCase):

    def setUp(self):
        self.win = mock.patch.object(autostart, "IS_WINDOWS", True)
        self.win.start()
        self.addCleanup(self.win.stop)

    def test_enable_creates_an_elevated_logon_task(self):
        rec = _Recorder(returncode=0)
        with mock.patch.object(autostart, "subprocess") as sp:
            sp.run = rec
            with mock.patch.object(autostart, "enable_run") as fallback:
                autostart.enable()
        cmd = rec.commands()[0]
        self.assertEqual(cmd[:4], ["schtasks", "/Create", "/TN", autostart.TASK_NAME])
        self.assertIn("ONLOGON", cmd)
        # /RL HIGHEST is what avoids a UAC prompt at every logon.
        self.assertIn("HIGHEST", cmd)
        self.assertIn("/F", cmd)
        fallback.assert_not_called()

    def test_enable_falls_back_to_the_registry_when_the_task_fails(self):
        rec = _Recorder(returncode=1, stderr="access denied")
        with mock.patch.object(autostart, "subprocess") as sp:
            sp.run = rec
            with mock.patch.object(autostart, "enable_run") as fallback:
                autostart.enable(minimized=True)
        fallback.assert_called_once_with(True)

    def test_disable_removes_both_mechanisms(self):
        rec = _Recorder(returncode=0)
        with mock.patch.object(autostart, "subprocess") as sp:
            sp.run = rec
            with mock.patch.object(autostart, "disable_run") as drop_key:
                autostart.disable()
        cmd = rec.commands()[0]
        self.assertEqual(cmd, ["schtasks", "/Delete", "/TN", autostart.TASK_NAME, "/F"])
        drop_key.assert_called_once_with()

    def test_enabled_when_the_task_exists_without_touching_the_registry(self):
        rec = _Recorder(returncode=0, stdout=autostart.TASK_NAME)
        with mock.patch.object(autostart, "subprocess") as sp:
            sp.run = rec
            self.assertTrue(autostart.is_enabled())
        self.assertEqual(rec.commands()[0][:2], ["schtasks", "/Query"])

    def test_not_enabled_when_neither_task_nor_key_is_present(self):
        rec = _Recorder(returncode=1)
        with mock.patch.object(autostart, "subprocess") as sp:
            sp.run = rec
            with mock.patch.dict(sys.modules):
                # is_enabled() falls through to the registry; a missing key
                # (FileNotFoundError) must simply mean "off", not an error.
                fake = mock.MagicMock()
                fake.HKEY_CURRENT_USER = 0
                fake.OpenKey.side_effect = FileNotFoundError
                sys.modules["winreg"] = fake
                self.assertFalse(autostart.is_enabled())

    def test_backwards_compatible_names_still_point_at_the_new_api(self):
        self.assertIs(autostart.enable_task, autostart.enable)
        self.assertIs(autostart.disable_task, autostart.disable)


class AutostartOtherSystemsTests(unittest.TestCase):

    def test_nothing_runs_outside_windows(self):
        rec = _Recorder()
        with mock.patch.object(autostart, "IS_WINDOWS", False):
            with mock.patch.object(autostart, "subprocess") as sp:
                sp.run = rec
                self.assertFalse(autostart.is_enabled())
                autostart.enable()
                autostart.disable()
                autostart.enable_run()
                autostart.disable_run()
        self.assertEqual(rec.calls, [])


class _FakeService(ServiceManager):
    """ServiceManager that records commands instead of running sc.exe."""

    def __init__(self, zapret_dir, results=None):
        super().__init__(zapret_dir)
        self.calls = []
        self.results = results or {}
        self.default = _done(0, "")

    def _run(self, args, **kw):
        args = list(args)
        self.calls.append(args)
        for key, value in self.results.items():
            if key in " ".join(args):
                return value
        return self.default

    def commands(self):
        return [" ".join(c) for c in self.calls]


class _Strategy:
    def __init__(self, name, args):
        self.name = name
        self.args = list(args)


class ServiceStatusTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.win = mock.patch("app.service_manager.IS_WINDOWS", True)
        self.win.start()
        self.addCleanup(self.win.stop)

    def test_running_service_is_reported(self):
        svc = _FakeService(self.dir, {"query": _done(0, "SERVICE_NAME: zapret\nSTATE: 4 RUNNING")})
        self.assertTrue(svc.is_installed())
        self.assertTrue(svc.is_running())
        self.assertEqual(svc.status_text(), "\u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442")

    def test_installed_but_stopped_service_is_reported(self):
        svc = _FakeService(self.dir, {"query": _done(0, "SERVICE_NAME: zapret\nSTATE: 1 STOPPED")})
        self.assertTrue(svc.is_installed())
        self.assertFalse(svc.is_running())
        self.assertEqual(svc.status_text(), "\u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0430")

    def test_missing_service_is_reported(self):
        svc = _FakeService(self.dir, {"query": _done(1060, "")})
        self.assertFalse(svc.is_installed())
        self.assertFalse(svc.is_running())
        self.assertEqual(svc.status_text(), "\u043d\u0435 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0430")

    def test_status_is_cached_so_the_timer_does_not_spawn_sc_every_tick(self):
        svc = _FakeService(self.dir, {"query": _done(0, "SERVICE_NAME: zapret\nSTATE: 4 RUNNING")})
        for _ in range(5):
            svc.is_running()
            svc.status_text()
        self.assertEqual(len(svc.calls), 1)

    def test_invalidate_forces_a_fresh_query(self):
        svc = _FakeService(self.dir, {"query": _done(0, "SERVICE_NAME: zapret\nSTATE: 4 RUNNING")})
        svc.is_running()
        svc.invalidate_status()
        svc.is_running()
        self.assertEqual(len(svc.calls), 2)


class ServiceInstallTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.win = mock.patch("app.service_manager.IS_WINDOWS", True)
        self.win.start()
        self.addCleanup(self.win.stop)

    def _with_winws(self):
        binary = self.dir / "bin" / "winws.exe"
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("not a real exe", encoding="utf-8")
        return binary

    def test_missing_engine_is_explained_not_silently_ignored(self):
        svc = _FakeService(self.dir)
        msg = svc.install(_Strategy("any", ["--wf-tcp=80"]))
        self.assertIn("winws.exe", msg)
        self.assertEqual(svc.calls, [])

    def test_missing_strategy_is_explained(self):
        self._with_winws()
        svc = _FakeService(self.dir)
        msg = svc.install(_Strategy("empty", []))
        self.assertIn("\u0441\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u044f", msg)
        self.assertEqual(svc.calls, [])

    def test_install_registers_the_engine_with_autostart(self):
        binary = self._with_winws()
        svc = _FakeService(self.dir)
        svc.install(_Strategy("basic", ["--wf-tcp=80,443", "--dpi-desync=fake"]))
        create = [c for c in svc.calls if c[:2] == ["sc", "create"]]
        self.assertEqual(len(create), 1)
        cmd = create[0]
        self.assertEqual(cmd[2], SERVICE_NAME)
        bin_path = cmd[cmd.index("binPath=") + 1]
        # The exe path must be one quoted token, args appended after it.
        self.assertTrue(bin_path.startswith('"' + str(binary) + '" '))
        self.assertIn("--dpi-desync=fake", bin_path)
        self.assertEqual(cmd[cmd.index("start=") + 1], "auto")

    def test_arguments_containing_spaces_are_quoted(self):
        self._with_winws()
        svc = _FakeService(self.dir)
        svc.install(_Strategy("spacey", ["--hostlist=C:/my lists/all.txt"]))
        create = [c for c in svc.calls if c[:2] == ["sc", "create"]][0]
        bin_path = create[create.index("binPath=") + 1]
        self.assertIn('"--hostlist=C:/my lists/all.txt"', bin_path)

    def test_previous_registration_is_replaced(self):
        self._with_winws()
        svc = _FakeService(self.dir)
        svc.install(_Strategy("basic", ["--wf-tcp=80"]))
        joined = svc.commands()
        self.assertLess(
            joined.index("sc delete " + SERVICE_NAME),
            [i for i, c in enumerate(joined) if c.startswith("sc create")][0],
        )

    def test_our_engine_is_stopped_before_the_service_starts(self):
        # Otherwise the service cannot grab WinDivert and dies with error 1060,
        # leaving "installed but stopped".
        self._with_winws()
        events = []

        class _Svc(_FakeService):
            def _run(self, args, **kw):
                events.append(" ".join(args))
                return super()._run(args, **kw)

        svc = _Svc(self.dir)
        svc.install(
            _Strategy("basic", ["--wf-tcp=80"]),
            on_pre_start=lambda: events.append("gui engine stopped"),
        )
        self.assertIn("gui engine stopped", events)
        self.assertLess(
            events.index("gui engine stopped"),
            events.index("sc start " + SERVICE_NAME),
        )

    def test_a_broken_pre_start_hook_does_not_abort_the_install(self):
        self._with_winws()
        svc = _FakeService(self.dir)

        def boom():
            raise RuntimeError("could not stop the engine")

        svc.install(_Strategy("basic", ["--wf-tcp=80"]), on_pre_start=boom)
        self.assertIn("sc start " + SERVICE_NAME, svc.commands())

    def test_flowseal_script_is_preferred_when_present(self):
        (self.dir / "service.bat").write_text("@echo off", encoding="utf-8")
        svc = _FakeService(self.dir, {"service.bat": _done(0, "installed")})
        out = svc.install(_Strategy("basic", ["--wf-tcp=80"]))
        self.assertEqual(out, "installed")
        self.assertTrue(svc.calls[0][:2] == ["cmd", "/c"])
        self.assertEqual(svc.calls[0][-1], "install")


class ServiceStartStopRemoveTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.win = mock.patch("app.service_manager.IS_WINDOWS", True)
        self.win.start()
        self.addCleanup(self.win.stop)

    def test_start_and_stop_use_sc(self):
        svc = _FakeService(self.dir)
        svc.start()
        svc.stop()
        self.assertIn("sc start " + SERVICE_NAME, svc.commands())
        self.assertIn("sc stop " + SERVICE_NAME, svc.commands())

    def test_remove_stops_before_deleting(self):
        svc = _FakeService(self.dir)
        svc.remove()
        cmds = svc.commands()
        self.assertLess(
            cmds.index("sc stop " + SERVICE_NAME),
            cmds.index("sc delete " + SERVICE_NAME),
        )

    def test_actions_refresh_the_cached_status(self):
        svc = _FakeService(self.dir, {"query": _done(0, "SERVICE_NAME: zapret\nSTATE: 4 RUNNING")})
        svc.is_running()  # fills the cache
        svc.stop()
        self.assertIsNone(svc._status_cache)

    def test_everything_is_a_no_op_outside_windows(self):
        with mock.patch("app.service_manager.IS_WINDOWS", False):
            svc = _FakeService(self.dir)
            self.assertIn("Windows", svc.install(_Strategy("basic", ["--wf-tcp=80"])))
            self.assertIn("Windows", svc.start())
            self.assertIn("Windows", svc.stop())
            self.assertIn("Windows", svc.remove())
            self.assertFalse(svc.is_installed())
            self.assertEqual(svc.calls, [])


if __name__ == "__main__":
    unittest.main()
