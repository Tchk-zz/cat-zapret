"""Strategy editor and HOSTS dialog for :class:`~ui.main_window.MainWindow`.

Split out of ``ui/main_window.py`` verbatim. Two related things live here, both
driven by the Strategy tab:

* **custom strategy editing** -- validate, save and delete user defined
  strategies (``_validate_custom`` ... ``_delete_custom``). Deleting restores
  the previous combo selection on purpose: rebuilding the list would otherwise
  silently fall back to index 0, and a later "run selected" would then launch
  the wrong strategy.
* **domain list files** -- load and save the plain text lists that ship next to
  winws (``_reload_domain_files`` ... ``_save_domain_file``). Note that
  ``_reload_domain_files`` is also called from ``ui/update_flow.py`` whenever a
  list refresh actually changed something, so it must stay free of side effects
  beyond repopulating the two widgets.

``show_hosts_dialog`` is the manual escape hatch for users whose DNS is
poisoned: it shows the generated HOSTS block, copies it to the clipboard, or
applies and removes it in place. Every write goes through ``app.list_manager``,
which keeps the hosts.zapretgui.bak backup and only ever replaces the ZapretGUI
block, never the rest of the file.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from app import editor as editor_mod, list_manager

from .theme import smooth_code_font

_smooth_code_font = smooth_code_font


class EditorFlowMixin:
    """Edit custom strategies and domain lists, and manage the HOSTS block."""

    # -------------------------------------------------------- custom strategies

    def _validate_custom(self) -> None:
        res = editor_mod.validate_args(self.edit_args.toPlainText())
        QMessageBox.information(
            self,
            self._msg_title("Проверка"),
            self._msg_text("\n".join(res.messages)),
        )

    def _save_custom(self) -> None:
        name = self.edit_name.text().strip()
        args = self.edit_args.toPlainText().strip()
        if not name or not args:
            QMessageBox.warning(self, "Zapret", self._msg_text("Укажите название и аргументы."))
            return
        self.manager.save_custom(name, args)
        self.reload_strategies()
        QMessageBox.information(self, "Zapret", self._msg_text("Стратегия сохранена."))

    def _delete_custom(self) -> None:
        name = self.edit_name.text().strip()
        if not name:
            return
        # Remember the current selection so we can restore it after the list is
        # rebuilt — otherwise the combo silently falls back to index 0 and a
        # later "Run selected" would launch the wrong strategy.
        prev_key = self.strategy_combo.currentData()
        if not self.manager.delete_custom(name):
            QMessageBox.warning(self, "Zapret", self._msg_text("Нет такой пользовательской стратегии."))
            return
        self.reload_strategies()
        # Restore the previous selection if it still exists; otherwise fall
        # back to the last working strategy (or the first one).
        new_idx = self.strategy_combo.findData(prev_key) if prev_key else -1
        if new_idx < 0:
            new_idx = self.strategy_combo.findData(self.config.last_working_strategy)
        if new_idx < 0 and self.strategy_combo.count() > 0:
            new_idx = 0
        if new_idx >= 0:
            self.strategy_combo.setCurrentIndex(new_idx)
        QMessageBox.information(self, "Zapret", self._msg_text("Удалено."))

    # ------------------------------------------------------------ domain lists

    def _reload_domain_files(self) -> None:
        self.domain_combo.blockSignals(True)
        self.domain_combo.clear()
        for p in editor_mod.list_domain_files(self.zapret_dir):
            self.domain_combo.addItem(p.name, str(p))
        self.domain_combo.blockSignals(False)
        self._load_domain_file()

    def _load_domain_file(self) -> None:
        path = self.domain_combo.currentData()
        if not path:
            self.domain_text.setPlainText("")
            return
        try:
            self.domain_text.setPlainText(Path(path).read_text(encoding="utf-8", errors="ignore"))
        except OSError as exc:
            self.domain_text.setPlainText(self._localize_runtime(f"# ошибка: {exc}"))

    def _save_domain_file(self) -> None:
        path = self.domain_combo.currentData()
        if not path:
            return
        try:
            Path(path).write_text(self.domain_text.toPlainText(), encoding="utf-8")
            QMessageBox.information(self, "Zapret", self._msg_text("Список сохранён."))
        except OSError as exc:
            QMessageBox.critical(self, "Zapret", self._msg_text(str(exc)))

    # -------------------------------------------------------------- HOSTS block

    def show_hosts_dialog(self) -> None:
        block = list_manager.build_hosts_block(self.zapret_dir, allow_network=True)
        if not block.strip():
            QMessageBox.warning(
                self,
                self._msg_title("HOSTS для Windows"),
                self._msg_text("Не удалось сформировать HOSTS-строки. Обновите списки/IPset и попробуйте снова."),
            )
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(self._t("HOSTS для Windows"))
        dlg.resize(760, 560)
        lay = QVBoxLayout(dlg)
        hosts_current = list_manager.hosts_block_is_current(block)
        info_text = (
            "HOSTS уже содержит актуальный блок ZapretGUI. Повторное применение не нужно."
            if hosts_current else
            "Скопируйте эти строки в Windows HOSTS или нажмите «Применить». "
            "Автоматическое применение создаёт backup и заменяет только блок ZapretGUI."
        )
        info = QLabel(info_text)
        info.setWordWrap(True)
        lay.addWidget(info)
        text = QPlainTextEdit()
        text.setObjectName("cmdPreview")
        text.setPlainText(block)
        text.setFont(_smooth_code_font(11))
        lay.addWidget(text, 1)
        row = QHBoxLayout()
        btn_copy = QPushButton("Копировать")
        btn_apply = QPushButton("Уже применено" if hosts_current else "Применить")
        btn_apply.setEnabled(not hosts_current)
        btn_remove = QPushButton("Удалить блок")
        btn_close = QPushButton("Закрыть")
        for b in (btn_copy, btn_apply, btn_remove, btn_close):
            b.setObjectName("secondaryBtn")
        row.addWidget(btn_copy)
        row.addStretch(1)
        row.addWidget(btn_remove)
        row.addWidget(btn_apply)
        row.addWidget(btn_close)
        lay.addLayout(row)

        def _copy() -> None:
            QApplication.clipboard().setText(text.toPlainText())
            self._log("[hosts] строки скопированы в буфер обмена")

        def _apply() -> None:
            ans = QMessageBox.question(
                dlg,
                self._msg_title("HOSTS для Windows"),
                self._msg_text(
                    "Применить блок ZapretGUI к системному HOSTS?\n\n"
                    "Будет создан backup hosts.zapretgui.bak. Нужны права администратора."
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
            msg = list_manager.apply_hosts_block(text.toPlainText())
            self._log("[hosts] " + msg)
            QMessageBox.information(dlg, self._msg_title("HOSTS для Windows"), self._msg_text(msg))

        def _remove() -> None:
            ans = QMessageBox.question(
                dlg,
                self._msg_title("HOSTS для Windows"),
                self._msg_text("Удалить блок ZapretGUI из системного HOSTS?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
            msg = list_manager.remove_hosts_block()
            self._log("[hosts] " + msg)
            QMessageBox.information(dlg, self._msg_title("HOSTS для Windows"), self._msg_text(msg))

        btn_copy.clicked.connect(_copy)
        btn_apply.clicked.connect(_apply)
        btn_remove.clicked.connect(_remove)
        btn_close.clicked.connect(dlg.accept)
        dlg.exec()
