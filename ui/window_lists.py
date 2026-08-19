"""User lists, per-service toggles and runner rebuilds."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from app.process_runner import ProcessRunner

from .widgets_custom import GamesColumnIcon


class ListsMixin:
    """Custom domain lists, service checkboxes and engine restarts."""

    # ------------------------------------------------------------- runner
    def _make_runner(self) -> ProcessRunner:
        """Build a ProcessRunner whose callbacks marshal back to the GUI thread."""
        return ProcessRunner(
            self.manager.winws_path(),
            log_cb=lambda m: self.engine_log.emit(m),
            on_exit=lambda code, tail: self.engine_exited.emit(code, tail),
            args_filter=self._engine_args_filter,
        )

    def _apply_user_lists(self) -> None:
        """Write include/exclude user lists from the saved selections."""
        try:
            from app import exclusions

            exclusions.apply_lists(
                self.zapret_dir,
                include_presets=self.config.include_presets or [],
                include_custom=self.config.include_custom or [],
                exclude_presets=self.config.exclude_presets or [],
                exclude_custom=self.config.exclude_custom or [],
            )
        except Exception:
            pass

    def _restart_engine_if_running(self) -> None:
        """Reload winws so changed user lists take effect immediately."""
        try:
            if self.runner.is_running():
                strat = self.runner.current_strategy or self._current_strategy()
                if strat is not None:
                    self._user_stop = False
                    self.runner.start(strat)
                    self._refresh_status()
        except Exception:
            pass

    def _toggle_service(self, kind: str, sid: str, enabled: bool) -> None:
        if kind == "include" and sid == "roblox":
            # The Roblox entry under "\u041f\u0440\u0438\u043c\u0435\u043d\u044f\u0442\u044c \u043e\u0431\u0445\u043e\u0434" is special: instead of only
            # adding domains to a hostlist, it merges the full Roblox bypass
            # profile (game UDP servers + ipset) into whatever strategy is
            # selected -- exactly what is needed to join places.
            self._toggle_roblox_combine(enabled)
            return
        field_name = "include_presets" if kind == "include" else "exclude_presets"
        cur = list(getattr(self.config, field_name) or [])
        if enabled and sid not in cur:
            cur.append(sid)
        elif not enabled and sid in cur:
            cur.remove(sid)
        setattr(self.config, field_name, cur)
        self.config.save()
        self._apply_user_lists()
        self._restart_engine_if_running()

    def _set_custom_domains(self, kind: str, text: str) -> None:
        field_name = "include_custom" if kind == "include" else "exclude_custom"
        domains = [p for p in text.replace(",", " ").replace(";", " ").split() if p]
        setattr(self.config, field_name, domains)
        self.config.save()
        self._apply_user_lists()
        self._restart_engine_if_running()

    def _service_display_name(self, name: str) -> str:
        """Short labels for the compact Games/Services layout."""
        mapping = {
            "Valorant / Riot Games": "Riot Games",
            "Battle.net / Blizzard": "Battle.net/Blizzard",
        }
        return mapping.get(name, name)

    def _build_list_group(self, kind: str, title_text: str):
        from app import exclusions

        box = QFrame()
        box.setObjectName("gamesColumn")
        gl = QVBoxLayout(box)
        # Raise the column header (icon + title) by 2pt without changing the
        # element order or divider behavior.
        gl.setContentsMargins(0, -2, 0, 0)
        gl.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)
        icon = GamesColumnIcon(kind)
        title = QLabel(title_text)
        title.setObjectName("gamesColumnTitle")
        title_row.addWidget(icon)
        title_row.addWidget(title)
        title_row.addStretch(1)
        gl.addLayout(title_row)

        sel = set(
            (
                self.config.include_presets
                if kind == "include"
                else self.config.exclude_presets
            )
            or []
        )
        for svc in exclusions.SERVICES:
            cb = QCheckBox(self._service_display_name(svc.name))
            cb.setObjectName("gamesCheck")
            if kind == "include" and svc.id == "roblox":
                # Under "Применять обход", Roblox drives the full combine
                # toggle (UDP place-join + ipset), not just a domain hostlist.
                cb.setChecked(bool(getattr(self.config, "roblox_combine", False)))
                cb.setToolTip(
                    "Объединяет выбранную стратегию с обходом для Roblox "
                    "(игровые UDP-серверы 49152-65535 + ipset + домены) — "
                    "нужно для входа на плейсы. Работает с любой стратегией."
                )
            else:
                cb.setChecked(svc.id in sel)
                cb.setToolTip(svc.description)
            cb.toggled.connect(
                lambda checked, k=kind, sid=svc.id: self._toggle_service(k, sid, checked)
            )
            gl.addWidget(cb)

        gl.addSpacing(8)
        domain_block = QWidget()
        domain_block.setObjectName("gamesDomainBlock")
        domain_lay = QVBoxLayout(domain_block)
        domain_lay.setContentsMargins(0, 0, 0, 0)
        domain_lay.setSpacing(0)
        lbl = QLabel("Свои домены (через запятую)")
        lbl.setObjectName("gamesDomainLabel")
        lbl.setContentsMargins(10, 0, 0, 0)
        lbl.setFixedHeight(18)
        domain_lay.addWidget(lbl)
        edit = QLineEdit()
        edit.setObjectName("gamesInput")
        edit.setFixedHeight(32)
        custom = (
            self.config.include_custom
            if kind == "include"
            else self.config.exclude_custom
        ) or []
        edit.setText(", ".join(custom))
        edit.setPlaceholderText("example.com, site.org")
        edit.editingFinished.connect(
            lambda e=edit, k=kind: self._set_custom_domains(k, e.text())
        )
        domain_lay.addWidget(edit)
        gl.addWidget(domain_block)
        # Lower the bottom separator by 2pt while keeping the center divider
        # inside the gap between the domain inputs (not over the inputs).
        gl.addSpacing(2)
        return box
