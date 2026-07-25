"""TelegramTabMixin — part of MainWindow, kept in its own file.

These methods were moved out of ui/main_window.py unchanged. They are
mixed into MainWindow, so ``self`` still refers to the window and every
attribute they use lives there as before.
"""
from __future__ import annotations

import sys

from PyQt6.QtCore import (
    Qt, QThread, QTimer,
)
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
    QWidget,
)

from app import tg_proxy
from .i18n import (  # noqa: E402
    _TRANSLATIONS,
    _TRANSLATIONS_REVERSE,
    localize_runtime_text,
    tr_text,
)
from .widgets_custom import (  # noqa: E402
    POPUP_DARK_QSS,
    POPUP_LIGHT_QSS,
    POPUP_QSS,
    AnimatedGradientProgressBar,
    AutoSelectProgressPopup,
    BypassTestPopup,
    GamesColumnIcon,
    PowerButton,
    StyledPopup,
    _Dark3DButton,
    _Dark3DPanel,
    _DarkAnimatedProgressBar,
    _GlassNav,
    _HomeAutoSelectPanel,
    _paint_dark_3d_surface,
    _SettingsRow,
    _ShimmerPlate,
    _SleepZWidget,
)


class TelegramTabMixin:
    """Mixin: see module docstring."""

    def _build_tg_tab(self) -> QWidget:
        """Telegram MTProto proxy tab (Flowseal/tg-ws-proxy).

        The proxy engine is embedded as a Python module and runs as an
        asyncio task inside our own process. Telegram Desktop connects to its
        local MTProto endpoint (127.0.0.1:1443 by default); the proxy then
        tunnels traffic through WebSocket to Telegram DCs, bypassing blocks.
        """
        w = QWidget()
        w.setObjectName("tgRoot")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(46, 14, 46, 16)
        lay.setSpacing(8)

        title = QLabel("Telegram прокси")
        self.tg_title = title
        title.setObjectName("gamesTitle")
        lay.addWidget(title)

        sub = QLabel(
            "Лок��льный MTProto-прокси для Telegram Desktop. Telegram подключается к нему, "
            "а прокси туннелирует трафик через WebSocket к серверам Telegram — обход блокировок "
            "без сторонних серверов."
        )
        self.tg_subtitle = sub
        sub.setObjectName("gamesSubtitle")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        # --- status pill + power button ---
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(12)
        self.tg_status_dot = QLabel("●")
        self.tg_status_dot.setStyleSheet("color: #ff5c6c; font-size: 18px; padding-top: 2px;")
        self.tg_status_label = QLabel(self._t("Прокси выключен"))
        self.tg_status_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        status_row.addWidget(self.tg_status_dot)
        status_row.addWidget(self.tg_status_label)
        status_row.addStretch(1)
        # Power button uses the same "secondaryBtn" style as the other action
        # buttons on this tab so it has a visible border (matches the rest of
        # the UI; "primaryBtn" was a full-fill button that looked out of place
        # here next to the other bordered buttons).
        self.btn_tg_toggle = QPushButton(self._t("Запустить прокси"))
        self.btn_tg_toggle.setObjectName("secondaryBtn")
        self.btn_tg_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tg_toggle.clicked.connect(self.tg_toggle)
        status_row.addWidget(self.btn_tg_toggle)
        lay.addLayout(status_row)

        # --- connection card ---
        card = QFrame()
        card.setObjectName("gamesCard")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(21, 22, 21, 18)
        card_lay.setSpacing(10)

        # --- Info grid (Server / Port / Secret) ---
        info_grid = QGridLayout()
        info_grid.setHorizontalSpacing(16)
        info_grid.setVerticalSpacing(10)
        info_grid.setColumnStretch(1, 1)
        info_grid.setContentsMargins(0, 0, 0, 0)
        lbl_srv = QLabel(self._t("Сервер"))
        lbl_srv.setStyleSheet("color: rgba(255,255,255,0.65); font-size: 12px;")
        self.tg_srv_value = QLabel(tg_proxy.DEFAULT_HOST)
        self.tg_srv_value.setStyleSheet("font-size: 14px; font-weight: 600;")
        info_grid.addWidget(lbl_srv, 0, 0)
        info_grid.addWidget(self.tg_srv_value, 0, 1)
        lbl_port = QLabel(self._t("Порт"))
        lbl_port.setStyleSheet("color: rgba(255,255,255,0.65); font-size: 12px;")
        self.tg_port_value = QLabel(str(tg_proxy.DEFAULT_PORT))
        self.tg_port_value.setStyleSheet("font-size: 14px; font-weight: 600;")
        info_grid.addWidget(lbl_port, 1, 0)
        info_grid.addWidget(self.tg_port_value, 1, 1)
        lbl_secret = QLabel("Secret")
        lbl_secret.setStyleSheet("color: rgba(255,255,255,0.65); font-size: 12px;")
        self.tg_secret_value = QLabel(self._t("Секрет появится после первого запуска прокси."))
        self.tg_secret_value.setStyleSheet(
            "font-size: 13px; font-family: 'Cascadia Mono', 'Consolas', 'Liberation Mono', monospace;"
        )
        self.tg_secret_value.setWordWrap(False)
        self.tg_secret_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info_grid.addWidget(lbl_secret, 2, 0)
        info_grid.addWidget(self.tg_secret_value, 2, 1)
        card_lay.addLayout(info_grid)

        # --- Connection link block ---
        # Wrap the label + field in a QFrame with explicit top margin so the
        # "Ссылка для подключения" label is clearly separated from the
        # info_grid above (the parent's setSpacing(10) wasn't enough on its
        # own — QLabel with a stylesheet doesn't always honour margin-top in
        # the way one would expect).
        link_block_widget = QFrame()
        link_block_widget.setObjectName("tgLinkBlock")
        link_block = QVBoxLayout(link_block_widget)
        link_block.setContentsMargins(0, 14, 0, 0)
        link_block.setSpacing(4)
        lbl_link = QLabel(self._t("Ссылка для ��одклю��ения"))
        lbl_link.setObjectName("tgLinkLabel")
        lbl_link.setStyleSheet(
            "QLabel#tgLinkLabel { color: rgba(255,255,255,0.65); font-size: 12px; }"
        )
        link_block.addWidget(lbl_link)
        self.tg_link_field = QLineEdit()
        self.tg_link_field.setReadOnly(True)
        self.tg_link_field.setObjectName("gamesInput")
        self.tg_link_field.setPlaceholderText("tg://proxy?server=...&port=...&secret=...")
        self.tg_link_field.setCursor(Qt.CursorShape.IBeamCursor)
        link_block.addWidget(self.tg_link_field)
        card_lay.addWidget(link_block_widget)

        # --- Action buttons row ---
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_tg_copy = QPushButton(self._t("Скопировать ссылку"))
        self.btn_tg_copy.setObjectName("secondaryBtn")
        self.btn_tg_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tg_copy.clicked.connect(self.tg_copy_link)
        btn_row.addWidget(self.btn_tg_copy)
        self.btn_tg_open = QPushButton(self._t("Открыть в Telegram"))
        self.btn_tg_open.setObjectName("secondaryBtn")
        self.btn_tg_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tg_open.clicked.connect(self.tg_open_in_telegram)
        btn_row.addWidget(self.btn_tg_open)
        btn_row.addStretch(1)
        self.btn_tg_rotate = QPushButton(self._t("Сгенерировать новый secret"))
        self.btn_tg_rotate.setObjectName("secondaryBtn")
        self.btn_tg_rotate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tg_rotate.setToolTip(
            "Создаёт новый случайный secret и сохраняет его. Старая ссылка "
            "tg://proxy перестанет работать — нужно будет переподключить "
            "Telegram Desktop по новой ссылке. Если прокси запущен, он "
            "перезапустится автоматически."
        )
        self.btn_tg_rotate.clicked.connect(self.tg_rotate_secret)
        btn_row.addWidget(self.btn_tg_rotate)
        self.btn_tg_update = QPushButton(self._t("Проверить обновления tg-ws-proxy"))
        self.btn_tg_update.setObjectName("secondaryBtn")
        self.btn_tg_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tg_update.clicked.connect(self.tg_force_update)
        btn_row.addWidget(self.btn_tg_update)
        card_lay.addLayout(btn_row)

        lay.addWidget(card, 1)

        # Autostart-with-zapret checkbox
        self.cb_tg_autostart = QCheckBox(self._t("Запускать вместе с zapret"))
        self.cb_tg_autostart.setChecked(bool(getattr(self.config, "tg_proxy_autostart_with_zapret", False)))
        self.cb_tg_autostart.toggled.connect(self._toggle_tg_autostart)
        lay.addWidget(self.cb_tg_autostart)

        # --- Advanced: DC IP / fallback overrides ---
        # Since tg-ws-proxy v1.8.x an EMPTY DC->IP field is meaningful: it
        # lets the new fronting/CF/direct fallback chain work around stale or
        # unreachable Telegram IPs. We therefore show examples as placeholder
        # only and do not auto-fill defaults.
        adv_card = QFrame()
        adv_card.setObjectName("gamesCard")
        adv_lay = QVBoxLayout(adv_card)
        adv_lay.setContentsMargins(21, 16, 21, 16)
        adv_lay.setSpacing(6)
        adv_title = QLabel(self._t("Дополнительно: DC IP-адреса"))
        adv_title.setObjectName("gamesCardTitle")
        adv_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        adv_lay.addWidget(adv_title)
        adv_hint = QLabel(
            self._t(
                "Необязательно. Оставьте пустым — это лучший режим для tg-ws-proxy v1.8+. "
                "Если в логах постоянные fronting failed: TimeoutError или WS connect timed out, "
                "очистите это поле. Заполняйте только для ручного DC->IP override."
            )
        )
        adv_hint.setWordWrap(True)
        adv_hint.setStyleSheet("color: rgba(255,255,255,0.62); font-size: 12px;")
        adv_lay.addWidget(adv_hint)
        self.tg_dc_edit = QLineEdit()
        self.tg_dc_edit.setObjectName("gamesInput")
        self.tg_dc_edit.setPlaceholderText("например: 2:149.154.167.220, 4:149.154.167.220")
        cur_dc = list(getattr(self.config, "tg_proxy_dc_ips", []) or [])
        if cur_dc:
            self.tg_dc_edit.setText(", ".join(cur_dc))
        self.tg_dc_edit.editingFinished.connect(self._on_tg_dc_ips_edited)
        adv_lay.addWidget(self.tg_dc_edit)

        cf_title = QLabel(self._t("Дополнительно: Cloudflare fallback"))
        cf_title.setObjectName("gamesCardTitle")
        cf_title.setStyleSheet("font-size: 14px; font-weight: 600; margin-top: 8px;")
        adv_lay.addWidget(cf_title)
        cf_hint = QLabel(
            self._t(
                "Оставьте пустым для автоматического списка Flowseal. П��ля нужны только если у вас есть "
                "свои CF Proxy / CF Worker домены. Несколько доменов — через запятую."
            )
        )
        cf_hint.setWordWrap(True)
        cf_hint.setStyleSheet("color: rgba(255,255,255,0.62); font-size: 12px;")
        adv_lay.addWidget(cf_hint)
        self.tg_cfproxy_edit = QLineEdit()
        self.tg_cfproxy_edit.setObjectName("gamesInput")
        self.tg_cfproxy_edit.setPlaceholderText("CF Proxy domains (пусто = auto)")
        cur_cf = list(getattr(self.config, "tg_proxy_cfproxy_domains", []) or [])
        if cur_cf:
            self.tg_cfproxy_edit.setText(", ".join(cur_cf))
        self.tg_cfproxy_edit.editingFinished.connect(self._on_tg_cf_domains_edited)
        adv_lay.addWidget(self.tg_cfproxy_edit)
        self.tg_cfworker_edit = QLineEdit()
        self.tg_cfworker_edit.setObjectName("gamesInput")
        self.tg_cfworker_edit.setPlaceholderText("CF Worker domains (пус��о = выкл)")
        cur_worker = list(getattr(self.config, "tg_proxy_cfworker_domains", []) or [])
        if cur_worker:
            self.tg_cfworker_edit.setText(", ".join(cur_worker))
        self.tg_cfworker_edit.editingFinished.connect(self._on_tg_cf_domains_edited)
        adv_lay.addWidget(self.tg_cfworker_edit)
        lay.addWidget(adv_card)

        return w

    def _on_tg_dc_ips_edited(self) -> None:
        """Persist user DC->IP overrides. Empty means no forced override."""
        text = self.tg_dc_edit.text().strip()
        items = []
        for chunk in text.replace(",", " ").replace(";", " ").split():
            s = chunk.strip()
            if s:
                items.append(s)
        self.config.tg_proxy_dc_ips = items
        self.config.save()
        self.tg_runner.set_dc_ips(items)
        if items:
            self._log(f"[TG] DC->IP overrides updated: {len(items)} entries")
        else:
            self._log("[TG] DC->IP overrides cleared; fallback chain enabled")

    def _on_tg_cf_domains_edited(self) -> None:
        """Persist optional Cloudflare proxy / worker domain overrides."""
        def _items(edit):
            out = []
            for chunk in edit.text().replace(",", " ").replace(";", " ").split():
                s = chunk.strip()
                if s:
                    out.append(s)
            return out
        cfproxy = _items(self.tg_cfproxy_edit)
        cfworker = _items(self.tg_cfworker_edit)
        self.config.tg_proxy_cfproxy_domains = cfproxy
        self.config.tg_proxy_cfworker_domains = cfworker
        self.config.save()
        self.tg_runner.set_cf_domains(cfproxy, cfworker)
        self._log(f"[TG] CF fallback domains updated: proxy={len(cfproxy)}, worker={len(cfworker)}")

    def _toggle_tg_autostart(self, on: bool) -> None:
        self.config.tg_proxy_autostart_with_zapret = bool(on)
        self.config.save()

    def _tg_restore_state(self) -> None:
        """On launch, if the user previously enabled the TG proxy, bring it back."""
        if not getattr(self.config, "tg_proxy_enabled", False):
            return
        # Make sure the exe is present (download if missing), then start.
        self._tg_ensure_installed_then(start_after=True)

    def _tg_ensure_installed_then(self, start_after: bool) -> None:
        """Engine is embedded as Python code — always 'installed'. Just start
        the proxy if requested. Kept as a thin wrapper so callers don't need
        to know about the architecture change."""
        if start_after:
            self._tg_start_safe()

    def tg_toggle(self) -> None:
        """Power button: stop if running, otherwise bootstrap+start.

        Stop is now non-blocking — the UI updates immediately and a background
        daemon thread joins the engine. The button is disabled for ~0.3s so
        the user can't double-click it during the stop transition.
        """
        if self.tg_runner.is_running():
            self._tg_set_buttons_enabled(False)
            self.tg_stop()
            # Re-enable shortly after — by then is_running() is False.
            QTimer.singleShot(400, lambda: self._tg_set_buttons_enabled(True))
            return
        self._tg_set_buttons_enabled(False)
        self.config.tg_proxy_enabled = True
        self.config.save()
        # Make sure the exe exists, then start.
        self._tg_ensure_installed_then(start_after=True)
        QTimer.singleShot(400, lambda: self._tg_set_buttons_enabled(True))

    def _tg_set_buttons_enabled(self, enabled: bool) -> None:
        """Enable/disable all TG tab buttons to prevent rapid double-clicks
        during async start/stop transitions."""
        for attr in (
            "btn_tg_toggle", "btn_tg_copy", "btn_tg_open",
            "btn_tg_rotate", "btn_tg_update",
        ):
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setEnabled(enabled)

    def _tg_start_safe(self) -> None:
        """Start the proxy and update the UI. Surfaces failures as a popup.

        ``start()`` is non-blocking — the engine may fail to bind to the port
        asynchronously (the error is logged via _run_async, not raised). We
        schedule a deferred verification 1.5s later; if the engine died, we
        show a popup so the user knows the start failed.
        """
        try:
            self.tg_runner.start()
        except Exception as exc:  # noqa: BLE001
            StyledPopup(
                "Telegram",
                "Не удалось запустить tg-ws-proxy.\n\n" + str(exc),
                self,
                error_style=True,
            ).exec()
            self.config.tg_proxy_enabled = False
            self.config.save()
            self._tg_set_buttons_enabled(True)
            return
        # Refresh the link shortly after start — by then the engine has
        # loaded our persisted config and we know the secret for sure.
        QTimer.singleShot(1500, self._tg_refresh_link)
        # Verify the engine is still alive 1.5s after start (the engine
        # might have died from a bind error that was only logged).
        QTimer.singleShot(1500, self._tg_verify_started)
        self._tg_refresh_status()

    def _tg_verify_started(self) -> None:
        """Check the engine is still running 1.5s after start. If it died
        (port busy, firewall block, etc.), surface a popup."""
        self._tg_set_buttons_enabled(True)
        if not self.tg_runner.is_running():
            self.config.tg_proxy_enabled = False
            self.config.save()
            self._tg_refresh_status()
            StyledPopup(
                "Telegram",
                "Прокси не удалось запустить. Возможные причины:\n\n"
                "• Порт 1443 уже занят другим приложением.\n"
                "• Брандмауэр блокирует локальные подключения.\n"
                "• Антивирус заблокировал запуск.\n\n"
                "Проверьте лог на вкладке «Стратегия → Логи».",
                self,
                error_style=True,
            ).exec()

    def tg_stop(self) -> None:
        """Non-blocking stop. is_running() flips to False immediately so the
        UI updates without freezing; a daemon thread reaps the engine."""
        self.tg_runner.stop()
        self.config.tg_proxy_enabled = False
        self.config.save()
        self._tg_refresh_status()

    def tg_rotate_secret(self) -> None:
        """Generate a new random MTProto secret and restart the proxy if it
        was running. The old tg://proxy link becomes invalid immediately."""
        was_running = self.tg_runner.is_running()
        # Confirm: rotating the secret invalidates the existing link.
        ans = QMessageBox.question(
            self, self._msg_title("Telegram"),
            "Сгенерировать новый secret?\n\n"
            "Старая ссылка tg://proxy перестанет работать — нужно будет "
            "переподключить Telegram Desktop по новой ссылке.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        # Disable buttons during the rotate+restart sequence.
        self._tg_set_buttons_enabled(False)
        # Stop the proxy first so the engine releases the port cleanly.
        if was_running:
            self.tg_runner.stop()
            # Wait for the engine to fully stop before regenerating the
            # secret and restarting — otherwise the new engine can fail to
            # bind to port 1443 (TIME_WAIT / still-in-use). This typically
            # takes <500ms; we cap at 5s to be safe.
            self.tg_runner.wait_for_stop(timeout=5.0)
            self._tg_refresh_status()
        try:
            cfg = tg_proxy.regenerate_secret(self._tg_data_dir)
            self._log(f"[TG] new secret generated: {cfg.secret[:8]}...")
        except Exception as exc:  # noqa: BLE001
            self._tg_set_buttons_enabled(True)
            StyledPopup(
                "Telegram",
                "Не удалось сгенерировать новый secret:\n" + str(exc),
                self,
                error_style=True,
            ).exec()
            return
        # Refresh the link field immediately so the new secret is visible.
        self._tg_refresh_link()
        # Restart the proxy if it was running before. Use a short timer to
        # let the OS finish releasing the socket (TIME_WAIT can linger
        # briefly even after the engine thread exits).
        if was_running:
            QTimer.singleShot(300, self._tg_restart_after_rotate)
        else:
            self._tg_set_buttons_enabled(True)
            StyledPopup(
                "Telegram",
                "Новый secret сгенерирован. Запустите прокси и переподключите "
                "Telegram Desktop по новой ссылке.",
                self,
            ).exec()

    def _tg_restart_after_rotate(self) -> None:
        """Restart the proxy after a secret rotation, then verify it bound."""
        try:
            self.tg_runner.start()
        except Exception as exc:  # noqa: BLE001
            self._tg_set_buttons_enabled(True)
            StyledPopup(
                "Telegram",
                "Прокси не удалось перезапустить после ротации secret:\n" + str(exc),
                self,
                error_style=True,
            ).exec()
            return
        # Refresh the link field after a short delay so the new secret shows.
        QTimer.singleShot(800, self._tg_refresh_link)
        self._tg_refresh_status()
        # Verify the engine actually started. ``start()`` is non-blocking —
        # the engine may fail to bind to the port asynchronously (the error
        # is logged via _run_async, not raised). Check is_running() after a
        # short delay and surface a popup if the engine died.
        QTimer.singleShot(1500, self._tg_verify_started_after_rotate)

    def _tg_verify_started_after_rotate(self) -> None:
        """Check that the engine is still running 1.5s after start, and
        surface an error popup if it failed to bind to the port."""
        self._tg_set_buttons_enabled(True)
        if not self.tg_runner.is_running():
            StyledPopup(
                "Telegram",
                "Прокси не удалось пе����езапустить — возможно, порт 1443 всё ещё "
                "занят. Подождите 10–20 секунд и попробуйте снова кнопкой "
                "«Запустить прокси».",
                self,
                error_style=True,
            ).exec()
            return
        StyledPopup(
            "Telegram",
            "Новый secret сгенерирован, прокси перезапущен.\n\n"
            "Переподключите Telegram Desktop по новой ссылке — кнопкой "
            "«Открыть в Telegram».",
            self,
        ).exec()

    def _on_tg_engine_exited(self, code: int) -> None:
        """The proxy stopped on its own (crash / external kill)."""
        self._log("[TG] engine exited (code " + str(code) + ")")
        self.config.tg_proxy_enabled = self.tg_runner.is_running()
        self.config.save()
        self._tg_refresh_status()

    def _tg_refresh_status(self) -> None:
        running = self.tg_runner.is_running()
        if running:
            self.tg_status_dot.setStyleSheet("color: #37c871; font-size: 18px; padding-top: 2px;")
            self.tg_status_label.setText(self._t("Прокси запущен"))
            self.btn_tg_toggle.setText(self._t("Остановить прокси"))
        else:
            self.tg_status_dot.setStyleSheet("color: #ff5c6c; font-size: 18px; padding-top: 2px;")
            self.tg_status_label.setText(self._t("Прокси выключен"))
            self.btn_tg_toggle.setText(self._t("Запустить прокси"))
        self._tg_refresh_link()
        # Update tray state too.
        if hasattr(self, "tray"):
            self.tray.set_tg_running(running)

    def _tg_refresh_link(self) -> None:
        """Re-read the proxy config and update the link field + secret display."""
        cfg = tg_proxy.read_config(self._tg_data_dir)
        self.tg_srv_value.setText(cfg.host)
        self.tg_port_value.setText(str(cfg.port))
        if cfg.secret:
            # Full secret is selectable; the QLineEdit below shows the
            # complete tg:// link anyway, so just show it verbatim.
            self.tg_secret_value.setText(cfg.secret)
        else:
            self.tg_secret_value.setText(self._t("Секрет появится после первого запуска прокси."))
        link = tg_proxy.proxy_link(cfg)
        self.tg_link_field.setText(link)

    def tg_copy_link(self) -> None:
        link = self.tg_link_field.text().strip()
        if not link:
            StyledPopup(
                "Telegram",
                self._t("Ссылка ещё не готова — запустите прокси."),
                self,
            ).exec()
            return
        QApplication.clipboard().setText(link)
        StyledPopup("Telegram", self._t("Ссылка скопирована в буфер обмена."), self).exec()

    def tg_open_in_telegram(self) -> None:
        """Open the tg://proxy URL — Telegram Desktop picks it up."""
        link = self.tg_link_field.text().strip()
        if not link:
            StyledPopup(
                "Telegram",
                self._t("Ссылка ещё не готова — запустите прокси."),
                self,
            ).exec()
            return
        try:
            # On Windows this hands the URL to the OS default handler for tg://
            import os
            if sys.platform.startswith("win"):
                os.startfile(link)  # type: ignore[attr-defined]
            else:
                import subprocess as _sp
                _sp.Popen(["xdg-open", link])
        except Exception as exc:  # noqa: BLE001
            StyledPopup(
                "Telegram",
                "Не удалось открыть ссылку:\n" + str(exc) + "\n\nСкопируйте её вручную.",
                self,
                error_style=True,
            ).exec()

    def tg_force_update(self) -> None:
        """Manually check and apply upstream tg-ws-proxy updates.

        Previous builds only *reported* that an update existed, which made the
        button feel dead. Now manual click downloads and refreshes the embedded
        Python proxy modules when a newer upstream release is found.
        """
        if self._tg_update_thread is not None:
            return
        self.btn_tg_update.setText(self._t("Проверяю..."))
        self.btn_tg_update.setEnabled(False)
        self.btn_tg_update.repaint()
        QApplication.processEvents()
        self._tg_run_update_check(manual=True, apply_update=True)

    def _tg_check_updates_async(self) -> None:
        """Auto-check on launch and silently apply a newer proxy engine.

        If the proxy modules were already imported in this process, the update
        is written to disk and a popup asks the user to restart ZapretGUI. If
        not, the next proxy start uses the refreshed files.
        """
        if self._tg_update_thread is not None:
            return
        self._tg_run_update_check(manual=False, apply_update=True)

    def _tg_run_update_check(self, manual: bool, apply_update: bool = False) -> None:
        """Run the tg-ws-proxy update check in a worker thread.

        ``manual=True`` always reports the result. ``manual=False`` stays quiet
        when everything is current, but logs/applies real updates.
        """
        from .workers import TGProxyUpdateWorker
        worker = TGProxyUpdateWorker(self._tg_data_dir, apply_update=apply_update)
        thread = QThread(self)
        self._tg_update_thread = thread
        self._tg_update_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        self._tg_update_manual = manual
        self._tg_update_apply = apply_update
        worker.progress.connect(self._append_log)
        worker.finished.connect(self._on_tg_update_finished)
        thread.start()

    def _on_tg_update_finished(self, res) -> None:
        """Called on the GUI thread when the TG update worker finishes."""
        if self._tg_update_thread is not None:
            self._tg_update_thread.quit()
            self._tg_update_thread.wait()
            self._tg_update_thread = None
            self._tg_update_worker = None
        manual = getattr(self, "_tg_update_manual", False)
        status = getattr(res, "status", "error")
        msg = getattr(res, "message", str(res))
        ok = bool(getattr(res, "ok", False))
        if hasattr(self, "btn_tg_update"):
            self.btn_tg_update.setText(self._t("Проверить обновления tg-ws-proxy"))
            self.btn_tg_update.setEnabled(True)
            self.btn_tg_update.repaint()
        self._log("[TG] " + msg)
        if status == "updated":
            if self.tg_runner.is_running():
                self.tg_runner.stop()
                self.config.tg_proxy_enabled = False
                self.config.save()
            self._tg_refresh_status()
            if manual or getattr(res, "needs_restart", False):
                StyledPopup(
                    "Telegram",
                    msg + "\n\nЕсли прокси уже запускался в этой сессии, перезапустите ZapretGUI, чтобы точно загрузилась новая версия.",
                    self,
                ).exec()
        elif status == "available":
            if manual:
                StyledPopup("Telegram", msg, self).exec()
        elif manual:
            if ok:
                StyledPopup("Telegram", msg, self).exec()
            else:
                StyledPopup("Telegram", msg, self, error_style=True).exec()
        self._tg_refresh_status()
