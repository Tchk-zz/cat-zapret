"""Tests for the log file (app/applog.py).

The journal must be impossible to break: it is the only trace left when one of
the ~120 deliberately-silent error handlers fires. So these tests check that it
writes, that it rotates instead of filling the disk, that repeated setup calls
do not duplicate every line, and that an unwritable location degrades to
"no log" instead of an exception.
"""
import logging
import tempfile
import unittest
from pathlib import Path

from app import applog
from app.process_runner import ProcessRunner


class _LogDirCase(unittest.TestCase):
    """Base class: point the journal at a throwaway folder and clean up.

    The handler keeps the file open, and Windows refuses to delete an open
    file, so handlers are detached before the temp folder is removed.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log_dir = Path(self._tmp.name)
        self.addCleanup(self._cleanup)
        applog.setup(directory=self.log_dir)

    def _cleanup(self):
        root = logging.getLogger(applog.LOGGER_NAME)
        for handler in list(root.handlers):
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
        self._tmp.cleanup()

    def read_log(self):
        path = self.log_dir / applog.LOG_FILENAME
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")


class LogWritingTests(_LogDirCase):

    def test_message_reaches_the_file(self):
        applog.get_logger("engine").warning("winws did not start")
        text = self.read_log()
        self.assertIn("winws did not start", text)
        self.assertIn("WARNING", text)
        self.assertIn("zapret.engine", text)

    def test_exception_details_are_recorded(self):
        log = applog.get_logger("engine")
        try:
            raise ValueError("boom")
        except ValueError:
            log.warning("something failed quietly", exc_info=True)
        text = self.read_log()
        self.assertIn("something failed quietly", text)
        self.assertIn("ValueError: boom", text)
        self.assertIn("Traceback", text)

    def test_repeated_setup_does_not_duplicate_lines(self):
        # Calling setup() twice used to attach a second handler, so every line
        # would be written twice.
        applog.setup(directory=self.log_dir)
        applog.get_logger("engine").info("only once please")
        self.assertEqual(self.read_log().count("only once please"), 1)
        self.assertEqual(len(logging.getLogger(applog.LOGGER_NAME).handlers), 1)

    def test_debug_is_filtered_by_default(self):
        applog.get_logger("engine").debug("noisy detail")
        self.assertNotIn("noisy detail", self.read_log())

    def test_app_logger_does_not_leak_into_python_root(self):
        self.assertFalse(logging.getLogger(applog.LOGGER_NAME).propagate)

    def test_area_names_are_namespaced(self):
        self.assertEqual(applog.get_logger("update").name, "zapret.update")
        self.assertEqual(applog.get_logger().name, "zapret")

    def test_startup_banner_mentions_the_version(self):
        applog.log_startup("1.8.4")
        self.assertIn("1.8.4", self.read_log())


class RotationTests(_LogDirCase):

    def test_file_rotates_instead_of_growing_forever(self):
        applog.setup(directory=self.log_dir, max_bytes=2048)
        log = applog.get_logger("engine")
        for i in range(400):
            log.info("a chatty engine line number %d with some padding text", i)
        current = self.log_dir / applog.LOG_FILENAME
        backups = sorted(self.log_dir.glob(applog.LOG_FILENAME + ".*"))
        self.assertTrue(backups, "the log should have rotated")
        # Rotation is size-based, so the live file stays small...
        self.assertLess(current.stat().st_size, 8192)
        # ...and old copies are capped, never an unbounded pile.
        self.assertLessEqual(len(backups), 2)


class UnwritableLocationTests(unittest.TestCase):

    def test_setup_survives_a_location_it_cannot_create(self):
        with tempfile.TemporaryDirectory() as td:
            blocker = Path(td) / "not-a-folder"
            blocker.write_text("x", encoding="utf-8")
            # Asking for a folder *inside a file* cannot possibly work.
            logger = applog.setup(directory=blocker / "logs")
            try:
                logger.warning("this must not raise")
                applog.get_logger("engine").error("neither must this")
            finally:
                for handler in list(logger.handlers):
                    logger.removeHandler(handler)
                    handler.close()


class LogPathTests(unittest.TestCase):

    def test_log_lives_in_the_user_data_folder(self):
        path = applog.log_path()
        self.assertEqual(path.name, applog.LOG_FILENAME)
        self.assertEqual(path.parent.name, "logs")
        self.assertEqual(path.parent.parent.name, "ZapretGUI")


class EngineLoggingTests(_LogDirCase):

    def test_engine_output_is_journalled(self):
        runner = ProcessRunner(Path("nowhere") / "winws.exe")
        runner.log("[Launch] test strategy")
        self.assertIn("[Launch] test strategy", self.read_log())

    def test_broken_log_view_callback_is_reported_not_swallowed(self):
        def boom(_msg):
            raise RuntimeError("log view is gone")

        runner = ProcessRunner(Path("nowhere") / "winws.exe", log_cb=boom)
        runner.log("engine says hello")  # must not raise
        text = self.read_log()
        self.assertIn("engine says hello", text)
        self.assertIn("log callback failed", text)
        self.assertIn("RuntimeError: log view is gone", text)


if __name__ == "__main__":
    unittest.main()
