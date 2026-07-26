"""Rotating log file for Zapret GUI.

Why this module exists: the code swallows exceptions in ~120 places (many of
them deliberately -- a failed tray icon or a missing font must never kill the
app), but until now there was no journal at all, so a silent failure left no
trace whatsoever and "it just does nothing" bug reports were impossible to
diagnose. Everything now goes to
``%LOCALAPPDATA%\\ZapretGUI\\logs\\zapret-gui.log``.

Rules for this module:

* Nothing here may raise. If the log file cannot be created (read-only disk,
  antivirus lock, no writable profile) we attach a NullHandler and the app
  keeps working exactly as before.
* The file is size-capped and rotated, so a long-running app with a chatty
  engine can never fill the user's disk.
* It is deliberately independent from the on-screen log view in the UI: that
  one is for the user, this one is for diagnosing a broken install.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

# Root name for all app loggers. Child loggers are "zapret.<area>".
LOGGER_NAME = "zapret"
LOG_FILENAME = "zapret-gui.log"

# 512 KB per file plus two rotated copies: enough history to explain a failed
# start, small enough to paste into a bug report.
_MAX_BYTES = 512 * 1024
_BACKUP_COUNT = 2

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Set once the file handler has been attached, so get_logger() can configure
# logging lazily on first use without re-opening the file every call.
_configured = False


def log_dir() -> Path:
    """Folder holding the log files (inside the per-user data directory)."""
    from .config import default_data_dir
    return default_data_dir() / "logs"


def log_path() -> Path:
    """Full path of the current log file."""
    return log_dir() / LOG_FILENAME


def setup(
    level: int = logging.INFO,
    directory: Optional[Path] = None,
    max_bytes: int = _MAX_BYTES,
) -> logging.Logger:
    """Attach the rotating file handler and return the root app logger.

    Safe to call more than once: existing handlers are replaced instead of
    piling up (which would write every line several times).

    Args:
        level: minimum level written to the file.
        directory: override the log folder (used by the tests).
        max_bytes: rotate the file once it grows past this size.
    """
    global _configured
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    # Never hand our records to the root logger: pytest and PyQt both install
    # their own handlers and would duplicate or swallow the output.
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    try:
        target = Path(directory) if directory is not None else log_dir()
        target.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            target / LOG_FILENAME,
            maxBytes=max_bytes,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
            # delay=True: do not touch the disk until something is logged.
            delay=True,
        )
        file_handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))
        logger.addHandler(file_handler)
    except Exception:
        # No writable log location: keep the app alive and silent as before.
        logger.addHandler(logging.NullHandler())

    _configured = True
    return logger


def get_logger(area: str = "") -> logging.Logger:
    """Return a logger for one area of the app, configuring logging on demand.

    ``area`` is a short human-readable tag such as "engine" or "update"; it
    shows up in every line of the log file.
    """
    if not _configured:
        setup()
    if area:
        return logging.getLogger(LOGGER_NAME + "." + area)
    return logging.getLogger(LOGGER_NAME)


def log_startup(version: str) -> None:
    """Write one banner line so every session in the file is easy to find."""
    log = get_logger("start")
    log.info(
        "Zapret GUI %s starting: python %s, platform %s, frozen=%s",
        version or "?",
        sys.version.split()[0],
        sys.platform,
        bool(getattr(sys, "frozen", False)),
    )
