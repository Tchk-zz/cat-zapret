"""Settings tab row frame."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QFrame


class _SettingsRow(QFrame):
    """A settings row whose entire outlined area toggles its checkbox."""

    def __init__(self, checkbox: QCheckBox, parent=None):
        super().__init__(parent)
        self._checkbox = checkbox
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def mouseReleaseEvent(self, event):  # noqa: N802 (Qt naming)
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
            and self._checkbox.isEnabled()
        ):
            self._checkbox.toggle()
            event.accept()
            return
        super().mouseReleaseEvent(event)
