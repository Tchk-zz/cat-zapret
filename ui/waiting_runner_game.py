"""Lightweight pixel-art waiting game shown during dark-theme autoselect."""
from __future__ import annotations

import math
import os
import random
import time
from pathlib import Path

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import QApplication, QWidget


class WaitingRunnerGame(QWidget):
    """Small isolated endless runner whose lifecycle follows strategy search."""

    # Qt may dispatch virtual events from inside QWidget.__init__. Class-level
    # defaults make these fields available before the instance init completes.
    _searching = False
    _filter_installed = False
    roundEnded = pyqtSignal()

    VISUAL_SCALE = 1.12
    INITIAL_SPEED = 205.0
    MAX_SPEED = 400.0
    # Explicit score-based speed stages keep progression predictable.
    SPEED_STAGES = (
        (0, 205.0),
        (150, 220.0),
        (300, 240.0),
        (500, 260.0),
        (750, 285.0),
        (1000, 310.0),
        (1300, 340.0),
        (1650, 370.0),
        (2000, 400.0),
    )
    GRAVITY = 1080.0
    JUMP_VELOCITY = -425.0
    CAT_X = 72.0

    def __init__(self, best_score_path: Path, parent=None):
        super().__init__(parent)
        self._best_score_path = Path(best_score_path)
        assets_dir = Path(__file__).resolve().parent / "assets"
        self._obstacle_pixmaps = {
            "standard": QPixmap(str(assets_dir / "discord_obstacle_standard.png")),
            "tall": QPixmap(str(assets_dir / "discord_obstacle_tall.png")),
            "wide": QPixmap(str(assets_dir / "discord_obstacle_wide.png")),
        }
        self._cat_pixmaps = {
            "standard": QPixmap(str(assets_dir / "runner_cat_standard.png")),
            "crouch": QPixmap(str(assets_dir / "runner_cat_crouch.png")),
        }
        self._rng = random.Random()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._searching = False
        self._filter_installed = False
        self._last_time = 0.0
        self._reduced_motion = os.environ.get("QT_REDUCE_MOTION", "0") == "1"
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.setAccessibleName("Мини-игра ожидания автоподбора")
        self.setAccessibleDescription(
            "Пиксельный кот бежит автоматически. Пробел или стрелка вверх — прыжок, "
            "стрелка вниз — пригнуться. Клик или касание также выполняет прыжок."
        )
        self._best = self._load_best()
        self._clouds = [
            {"x": 130.0, "y": 44.0, "scale": 1.0},
            {"x": 360.0, "y": 72.0, "scale": 0.78},
            {"x": 580.0, "y": 38.0, "scale": 1.18},
        ]
        self._reset_round()

    # ------------------------------ lifecycle
    def set_searching(self, searching: bool) -> None:
        searching = bool(searching)
        if searching == bool(getattr(self, "_searching", False)):
            return
        self._searching = searching
        if searching:
            self._reset_round()
            self._last_time = time.monotonic()
            app = QApplication.instance()
            if app is not None and not self._filter_installed:
                app.installEventFilter(self)
                self._filter_installed = True
            self._timer.start()
            self.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            self._timer.stop()
            app = QApplication.instance()
            if app is not None and self._filter_installed:
                app.removeEventFilter(self)
            self._filter_installed = False
            self._down_held = False
            self._crouch_scan_code = None
            self.update()

    def shutdown(self) -> None:
        self.set_searching(False)

    def is_user_playing(self) -> bool:
        return bool(
            getattr(self, "_searching", False)
            and getattr(self, "_has_interacted", False)
            and not getattr(self, "_game_over", False)
        )

    def hideEvent(self, event) -> None:  # noqa: N802
        # Pause rendering and release the global key filter while the app/card
        # is hidden, but keep the round state so it can resume on show.
        if bool(getattr(self, "_searching", False)):
            self._timer.stop()
            app = QApplication.instance()
            if app is not None and self._filter_installed:
                app.removeEventFilter(self)
            self._filter_installed = False
        super().hideEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if bool(getattr(self, "_searching", False)):
            app = QApplication.instance()
            if app is not None and not self._filter_installed:
                app.installEventFilter(self)
                self._filter_installed = True
            self._last_time = time.monotonic()
            self._timer.start()

    # ------------------------------ input
    def eventFilter(self, watched, event):  # noqa: N802
        if not bool(getattr(self, "_searching", False)):
            return False
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            text = (event.text() or "").lower()
            if key in (Qt.Key.Key_Space, Qt.Key.Key_Up):
                if not event.isAutoRepeat():
                    self._jump_or_restart()
                return True
            crouch_key = key in (Qt.Key.Key_Down, Qt.Key.Key_S) or text in ("s", "ы")
            if crouch_key:
                self._has_interacted = True
                self._down_held = True
                self._crouch_scan_code = int(event.nativeScanCode())
                return True
        elif event.type() == QEvent.Type.KeyRelease:
            key = event.key()
            text = (event.text() or "").lower()
            scan_code = int(event.nativeScanCode())
            crouch_key = key in (Qt.Key.Key_Down, Qt.Key.Key_S) or text in ("s", "ы")
            same_physical_key = bool(
                self._down_held
                and getattr(self, "_crouch_scan_code", None) is not None
                and scan_code == self._crouch_scan_code
            )
            if crouch_key or same_physical_key:
                self._down_held = False
                self._crouch_scan_code = None
                return True
        return False

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if bool(getattr(self, "_searching", False)) and event.button() == Qt.MouseButton.LeftButton:
            self._jump_or_restart()
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            event.accept()
            return
        super().mousePressEvent(event)

    def event(self, event):
        if bool(getattr(self, "_searching", False)) and event.type() == QEvent.Type.TouchBegin:
            self._jump_or_restart()
            event.accept()
            return True
        return super().event(event)

    def _jump_or_restart(self) -> None:
        self._has_interacted = True
        if self._game_over:
            self._reset_round()
            self._has_interacted = True
            self._last_time = time.monotonic()
            return
        if abs(self._jump_y) < 0.01:
            self._jump_velocity = self.JUMP_VELOCITY
            self._trail.clear()

    # ------------------------------ state and physics
    def _reset_round(self) -> None:
        self._score = 0.0
        self._distance = 0.0
        self._speed = self.INITIAL_SPEED
        self._jump_y = 0.0
        self._jump_velocity = 0.0
        self._down_held = False
        self._crouch_scan_code = None
        self._game_over = False
        self._has_interacted = False
        self._blink_time = 0.0
        self._run_time = 0.0
        self._spawn_in = 1.35
        self._obstacles: list[dict] = []
        self._trail: list[dict] = []
        self._trail_emit = 0.0
        self._ground_scroll = 0.0
        self.update()

    def _tick(self) -> None:
        if not bool(getattr(self, "_searching", False)):
            return
        now = time.monotonic()
        dt = max(0.001, min(0.035, now - self._last_time))
        self._last_time = now

        if self._game_over:
            # Static game-over screen: no blinking/defeat animation.
            return

        self._run_time += dt
        self._distance += self._speed * dt
        self._score += self._speed * dt * 0.065
        self._speed = self._speed_for_score(self._score)
        self._ground_scroll = (self._ground_scroll + self._speed * dt) % 36.0

        if self._jump_y < 0.0 or self._jump_velocity < 0.0:
            self._jump_velocity += self.GRAVITY * dt
            self._jump_y += self._jump_velocity * dt
            if self._down_held and self._jump_velocity > 0:
                self._jump_velocity += self.GRAVITY * 0.8 * dt
            if self._jump_y >= 0.0:
                self._jump_y = 0.0
                self._jump_velocity = 0.0
                self._trail.clear()
            else:
                self._trail_emit -= dt
                if self._trail_emit <= 0.0 and not self._reduced_motion:
                    self._trail_emit = 0.075
                    self._trail.append({"x": self.CAT_X + 8.0, "y": self._cat_top() + 28.0, "life": 1.0})

        for dot in self._trail:
            dot["x"] -= self._speed * dt * 0.72
            dot["life"] -= dt * 1.55
        self._trail = [dot for dot in self._trail if dot["life"] > 0.0]

        for cloud in self._clouds:
            cloud["x"] -= self._speed * dt * 0.075
            if cloud["x"] < -90:
                cloud["x"] = self.width() + self._rng.uniform(80, 220)
                cloud["y"] = self._rng.uniform(30, 86)

        for obstacle in self._obstacles:
            obstacle["x"] -= self._speed * dt
        self._obstacles = [o for o in self._obstacles if o["x"] + o["w"] > -10]

        self._spawn_in -= dt
        if self._spawn_in <= 0.0:
            self._spawn_obstacle()

        cat_hit = self._cat_hitbox()
        for obstacle in self._obstacles:
            if cat_hit.intersects(self._obstacle_hitbox(obstacle)):
                self._finish_round()
                break
        self.update()

    def _speed_for_score(self, score: float) -> float:
        speed = self.INITIAL_SPEED
        for threshold, stage_speed in self.SPEED_STAGES:
            if score < threshold:
                break
            speed = stage_speed
        return min(self.MAX_SPEED, speed)

    def _spawn_obstacle(self) -> None:
        difficulty = min(1.0, self._score / 900.0)
        roll = self._rng.random()
        x = float(max(self.width() + 20, 640))
        if self._score > 90 and roll < 0.18:
            self._obstacles.append({"kind": "plane", "x": x, "w": 52.0, "h": 23.0})
            extra_delay = 0.30
        elif roll < 0.38:
            self._obstacles.append({"kind": "wide", "x": x, "w": 72.0, "h": 32.0})
            extra_delay = 0.24
        elif roll < 0.52 and self._speed >= 240.0:
            self._obstacles.extend([
                {"kind": "standard", "x": x, "w": 46.0, "h": 37.0},
                {"kind": "standard", "x": x + 62.0, "w": 46.0, "h": 37.0},
            ])
            extra_delay = 0.52
        elif roll < 0.70:
            self._obstacles.append({"kind": "tall", "x": x, "w": 56.0, "h": 60.0})
            extra_delay = 0.36
        else:
            self._obstacles.append({"kind": "standard", "x": x, "w": 46.0, "h": 37.0})
            extra_delay = 0.20
        minimum = 1.05 - 0.22 * difficulty
        maximum = 1.85 - 0.38 * difficulty
        self._spawn_in = self._rng.uniform(minimum, maximum) + extra_delay

    def _finish_round(self) -> None:
        self._game_over = True
        score = int(self._score)
        if score > self._best:
            self._best = score
            self._save_best()
        self.roundEnded.emit()

    # ------------------------------ geometry/collisions
    def _ground_y(self) -> float:
        return float(max(110, self.height() - 42))

    def _cat_height(self) -> float:
        return 41.0 if self._down_held and self._jump_y == 0.0 else 51.0

    def _cat_top(self) -> float:
        return self._ground_y() - self._cat_height() + self._jump_y

    def _cat_hitbox(self) -> QRectF:
        # The sprite tail extends left of CAT_X, but collision starts at the
        # torso. This keeps the visible tail completely outside the hitbox.
        crouching = bool(self._down_held and self._jump_y == 0.0)
        top = self._cat_top()
        if crouching:
            return QRectF(self.CAT_X + 4, top + 7, 54, 29)
        return QRectF(self.CAT_X + 5, top + 8, 54, 38)

    def _obstacle_hitbox(self, obstacle: dict) -> QRectF:
        if obstacle["kind"] == "plane":
            y = self._ground_y() - 58.0
            return QRectF(obstacle["x"] + 6, y + 4, obstacle["w"] - 12, obstacle["h"] - 8)
        kind = obstacle["kind"]
        y = self._ground_y() - obstacle["h"]
        if kind == "tall":
            # Ignore the decorative side pixels; collide with the central body.
            return QRectF(obstacle["x"] + 12, y + 10, obstacle["w"] - 24, obstacle["h"] - 13)
        if kind == "wide":
            return QRectF(obstacle["x"] + 9, y + 7, obstacle["w"] - 18, obstacle["h"] - 9)
        # Standard model: compact, slightly forgiving central hitbox.
        return QRectF(obstacle["x"] + 6, y + 5, obstacle["w"] - 12, obstacle["h"] - 7)

    # ------------------------------ painting
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
        outer = QRectF(self.rect()).adjusted(0, 0, -1, -1)
        bg_path = QPainterPath()
        bg_path.addRoundedRect(outer, 15, 15)
        painter.fillPath(bg_path, QColor("#f5f5f3"))
        painter.setClipPath(bg_path)

        self._draw_clouds(painter)
        self._draw_score(painter)
        self._draw_ground(painter)
        self._draw_trail(painter)
        for obstacle in self._obstacles:
            if obstacle["kind"] == "plane":
                self._draw_plane(painter, obstacle)
            else:
                self._draw_blob(painter, obstacle)
        self._draw_cat(painter)
        if self._game_over:
            self._draw_game_over(painter)
        painter.end()

    def _draw_clouds(self, painter: QPainter) -> None:
        pen = QPen(QColor("#a3a3a0"), 3)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for cloud in self._clouds:
            x, y, s = int(cloud["x"]), int(cloud["y"]), cloud["scale"] * self.VISUAL_SCALE
            points = [
                QPointF(x, y + 15*s), QPointF(x + 10*s, y + 15*s),
                QPointF(x + 10*s, y + 9*s), QPointF(x + 17*s, y + 9*s),
                QPointF(x + 22*s, y + 2*s), QPointF(x + 31*s, y + 2*s),
                QPointF(x + 38*s, y + 10*s), QPointF(x + 48*s, y + 10*s),
                QPointF(x + 56*s, y + 17*s), QPointF(x, y + 17*s),
            ]
            painter.drawPolyline(QPolygonF(points))

    def _draw_score(self, painter: QPainter) -> None:
        font = QFont("Courier New", 17)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#292929"))
        current = f"{min(99999, int(self._score)):05d}"
        best = f"BEST {min(99999, int(self._best)):05d}"
        painter.drawText(QRectF(self.width()-190, 15, 170, 24), Qt.AlignmentFlag.AlignRight, current)
        painter.setPen(QColor("#676765"))
        small = QFont("Courier New", 10)
        small.setBold(True)
        painter.setFont(small)
        painter.drawText(QRectF(self.width()-210, 40, 190, 18), Qt.AlignmentFlag.AlignRight, best)

    def _draw_ground(self, painter: QPainter) -> None:
        gy = int(self._ground_y())
        painter.setPen(QPen(QColor("#303030"), 3))
        painter.drawLine(0, gy, self.width(), gy)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#494947"))
        start = int(-self._ground_scroll)
        for x in range(start, self.width()+36, 36):
            painter.drawRect(x + 5, gy + 13 + (x//36 % 2)*4, 5, 5)
            painter.drawRect(x + 22, gy + 21 - (x//36 % 2)*3, 4, 4)

    def _draw_trail(self, painter: QPainter) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        for dot in self._trail:
            alpha = int(125 * max(0.0, dot["life"]))
            painter.setBrush(QColor(110, 110, 108, alpha))
            size = 3 if dot["life"] > 0.55 else 2
            painter.drawRect(int(dot["x"]), int(dot["y"]), size, size)

    def _draw_cat(self, painter: QPainter) -> None:
        crouching = bool(self._down_held and self._jump_y == 0.0)
        kind = "crouch" if crouching else "standard"
        pixmap = getattr(self, "_cat_pixmaps", {}).get(kind)
        grounded = abs(self._jump_y) < 0.01
        run_frame = int(self._run_time * 10.0) % 2 if grounded else 0

        if crouching:
            # The crouch sprite is wider/lower; alternate one pixel of squash
            # for a subtle two-frame running animation.
            width = 100.0 + run_frame
            height = 41.0 - run_frame
            left = self.CAT_X - 29.0 - run_frame * 0.5
            top = self._ground_y() - height + run_frame
        else:
            width = 100.0 + run_frame * 2.0
            height = 51.0 - run_frame
            left = self.CAT_X - 26.0 - run_frame
            bob = float(run_frame) if grounded else 0.0
            top = self._ground_y() - height + self._jump_y + bob

        if pixmap is not None and not pixmap.isNull():
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.drawPixmap(
                QRectF(left, top, width, height),
                pixmap,
                QRectF(pixmap.rect()),
            )
            painter.restore()
            return

        # Minimal static fallback if a sprite asset is unavailable.
        painter.setPen(QPen(QColor("#292929"), 2))
        painter.setBrush(QColor("#696979"))
        painter.drawRect(QRectF(self.CAT_X, top + 4, 54, max(20.0, height - 8)))

    def _draw_blob(self, painter: QPainter, obstacle: dict) -> None:
        x = float(obstacle["x"])
        h, w = float(obstacle["h"]), float(obstacle["w"])
        y = self._ground_y() - h
        pixmap = getattr(self, "_obstacle_pixmaps", {}).get(obstacle["kind"])
        if pixmap is not None and not pixmap.isNull():
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.drawPixmap(
                QRectF(x, y, w, h),
                pixmap,
                QRectF(pixmap.rect()),
            )
            painter.restore()
            return

        # Minimal fallback if an asset is unexpectedly unavailable.
        painter.setPen(QPen(QColor("#292929"), 2))
        painter.setBrush(QColor("#686866"))
        painter.drawRect(QRectF(x + 3, y + 3, w - 6, h - 4))

    def _draw_plane(self, painter: QPainter, obstacle: dict) -> None:
        x = float(obstacle["x"])
        y = self._ground_y() - 58.0
        sx = float(obstacle["w"]) / 46.0
        sy = float(obstacle["h"]) / 20.0
        painter.save()
        painter.translate(x, y)
        painter.scale(sx, sy)
        dark = QColor("#303030")
        painter.setPen(QPen(dark, 3))
        painter.setBrush(QColor("#efefed"))
        poly = QPolygonF([
            QPointF(0, 8), QPointF(44, 0), QPointF(25, 18),
            QPointF(17, 12), QPointF(8, 17),
        ])
        painter.drawPolygon(poly)
        painter.drawLine(17, 12, 44, 0)
        painter.drawLine(25, 18, 23, 9)
        painter.drawLine(-10, 17, -20, 22)
        painter.drawLine(-5, 24, -15, 30)
        painter.restore()

    def _draw_game_over(self, painter: QPainter) -> None:
        painter.fillRect(QRectF(0, 0, self.width(), self.height()), QColor(245, 245, 243, 190))
        painter.setPen(QColor("#262626"))
        title = QFont("Courier New", 14)
        title.setBold(True)
        painter.setFont(title)
        cy = self.height() / 2 - 28
        painter.drawText(QRectF(0, cy, self.width(), 24), Qt.AlignmentFlag.AlignCenter, "ПОИСК ПРОДОЛЖАЕТСЯ")
        painter.drawText(QRectF(0, cy+26, self.width(), 24), Qt.AlignmentFlag.AlignCenter, "ИГРА ОКОНЧЕНА")
        hint = QFont("Courier New", 10)
        hint.setBold(True)
        painter.setFont(hint)
        painter.setPen(QColor("#666664"))
        painter.drawText(
            QRectF(0, cy+58, self.width(), 22), Qt.AlignmentFlag.AlignCenter,
            "ПРОБЕЛ ИЛИ КЛИК — ЕЩЁ РАЗ",
        )

    # ------------------------------ persistence
    def _load_best(self) -> int:
        try:
            return max(0, int(self._best_score_path.read_text(encoding="utf-8").strip()))
        except Exception:
            return 0

    def _save_best(self) -> None:
        try:
            self._best_score_path.parent.mkdir(parents=True, exist_ok=True)
            self._best_score_path.write_text(str(int(self._best)), encoding="utf-8")
        except OSError:
            pass
