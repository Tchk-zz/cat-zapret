"""Render an offline GUI contact sheet for visual audit.

No user configuration, network request, tray icon, or zapret process is touched.
Run from the repository root: python tools/render_gui_audit.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import AppConfig
from ui.main_window import MainWindow
from ui.theme import load_app_fonts
from ui.tray import Tray


def main() -> int:
    output_dir = ROOT / "audit_artifacts"
    output_dir.mkdir(exist_ok=True)
    output = output_dir / "gui-contact-sheet.png"

    app = QApplication.instance() or QApplication(sys.argv)
    family = load_app_fonts()
    if family:
        app.setFont(QFont(family))
    app.setQuitOnLastWindowClosed(False)

    shots: list[tuple[str, QImage]] = []
    with tempfile.TemporaryDirectory(prefix="cat-zapret-gui-audit-") as td:
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": td, "APPDATA": td}), \
                mock.patch.object(MainWindow, "_fitted_window_size", lambda self, w, h: (w, h)), \
                mock.patch.object(MainWindow, "_ensure_ready", lambda self: None), \
                mock.patch.object(MainWindow, "check_updates_async", lambda self: None), \
                mock.patch.object(MainWindow, "_tg_check_updates_async", lambda self: None), \
                mock.patch.object(MainWindow, "_tg_restore_state", lambda self: None), \
                mock.patch.object(Tray, "show", lambda self: None):
            win = MainWindow(AppConfig.load(), start_minimized=False)
            win.show()
            app.processEvents()
            for index in range(win.tabs.count()):
                win.tabs.setCurrentIndex(index)
                app.processEvents()
                image = win.grab().toImage()
                image.save(str(output_dir / f"gui-purple-tab-{index + 1}.png"), "PNG")
                shots.append((f"purple / tab {index + 1}", image))
            win._toggle_theme("light", checked=True)
            win.tabs.setCurrentIndex(0)
            app.processEvents()
            image = win.grab().toImage()
            image.save(str(output_dir / "gui-light-tab-1.png"), "PNG")
            shots.append(("light / tab 1", image))
            win._force_quit = True
            win.hide()
            win.deleteLater()
            app.processEvents()

    thumb_w, thumb_h, caption_h = 620, 450, 28
    columns = 2
    rows = (len(shots) + columns - 1) // columns
    sheet = QImage(thumb_w * columns, (thumb_h + caption_h) * rows, QImage.Format.Format_RGB32)
    sheet.fill(QColor("#17131f"))
    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setPen(QColor("#ffffff"))
    for idx, (caption, image) in enumerate(shots):
        x = (idx % columns) * thumb_w
        y = (idx // columns) * (thumb_h + caption_h)
        scaled = image.scaled(thumb_w, thumb_h, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
        dx = x + (thumb_w - scaled.width()) // 2
        painter.drawImage(dx, y, scaled)
        painter.drawText(x + 8, y + thumb_h, thumb_w - 16, caption_h,
                         Qt.AlignmentFlag.AlignVCenter, caption)
    painter.end()
    if not sheet.save(str(output), "PNG"):
        raise RuntimeError(f"Cannot save {output}")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
