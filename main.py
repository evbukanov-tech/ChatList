"""Главное окно ChatList — GUI и связывание слоёв."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import app_appearance
import config
import db
import export_utils
import models
import network
import prompt_assistant
import seed
from prompt_assistant import PromptImprovementResult
from session import ResultSession

LOGS_DIR = Path("logs")
APP_ICON = Path(__file__).resolve().parent / "app.ico"
APP_VERSION = "1.0"
RESPONSE_PREVIEW_LINES = 5


def application_icon() -> QIcon | None:
    if APP_ICON.is_file():
        return QIcon(str(APP_ICON))
    return None


def setup_logging() -> None:
    LOGS_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOGS_DIR / "chatlist.log", encoding="utf-8"),
        ],
    )


def show_error(parent: QWidget | None, title: str, message: str) -> None:
    QMessageBox.critical(parent, title, message)


def show_info(parent: QWidget | None, title: str, message: str) -> None:
    QMessageBox.information(parent, title, message)


def response_preview(text: str, max_lines: int = RESPONSE_PREVIEW_LINES) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + "\n…"


def show_markdown_viewer(parent: QWidget | None, title: str, text: str) -> None:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setMinimumSize(720, 520)

    browser = QTextBrowser()
    browser.setMarkdown(text)
    browser.setOpenExternalLinks(True)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dialog.reject)

    layout = QVBoxLayout(dialog)
    layout.addWidget(browser)
    layout.addWidget(buttons)
    dialog.exec()


def add_open_button(table: QTableWidget, row: int, column: int, on_open) -> None:
    btn = QPushButton("Открыть")
    btn.clicked.connect(on_open)
    table.setCellWidget(row, column, btn)


class SendWorker(QThread):
    finished_ok = pyqtSignal(list)
    finished_error = pyqtSignal(str)

    def __init__(self, prompt: str, model_list: list[models.Model]) -> None:
        super().__init__()
        self.prompt = prompt
        self.model_list = model_list

    def run(self) -> None:
        try:
            responses = network.send_to_all_models(self.model_list, self.prompt)
            self.finished_ok.emit(responses)
        except Exception as exc:
            self.finished_error.emit(str(exc))


class ImprovePromptWorker(QThread):
    finished_ok = pyqtSignal(object)
    finished_error = pyqtSignal(str)

    def __init__(self, prompt: str, model: models.Model) -> None:
        super().__init__()
        self.prompt = prompt
        self.model = model

    def run(self) -> None:
        try:
            result = prompt_assistant.improve_prompt(self.prompt, self.model)
            if isinstance(result, str):
                self.finished_error.emit(result)
            else:
                self.finished_ok.emit(result)
        except Exception as exc:
            self.finished_error.emit(str(exc))


class PromptImproveDialog(QDialog):
    """Окно AI-ассистента: выбор модели и запрос к OpenRouter."""

    def __init__(
        self,
        parent: QWidget | None,
        original: str,
        on_apply,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI-ассистент — улучшение промта")
        self.setMinimumSize(640, 520)
        self._on_apply = on_apply
        self._original = original
        self._worker: ImprovePromptWorker | None = None
        self._has_results = False

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Клиент: OpenRouter"))

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Модель:"))
        self._model_combo = QComboBox()
        self._populate_models()
        self._model_combo.currentIndexChanged.connect(self._update_client_info)
        model_row.addWidget(self._model_combo, stretch=1)
        layout.addLayout(model_row)

        self._client_info = QLabel()
        self._client_info.setWordWrap(True)
        layout.addWidget(self._client_info)
        self._update_client_info()

        self._status_label = QLabel("Выберите модель и нажмите «Улучшить».")
        layout.addWidget(self._status_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.hide()
        layout.addWidget(self._progress)

        self._improve_btn = QPushButton("Улучшить")
        self._improve_btn.clicked.connect(self._on_improve_clicked)
        layout.addWidget(self._improve_btn)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.addWidget(
            self._make_section("Исходный", original, readonly=True)
        )
        self._content_layout.addStretch()
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_models(self) -> None:
        all_models = models.list_all()
        default_id = db.get_setting("prompt_assistant_model_id", "").strip()
        default_index = 0
        for index, model in enumerate(all_models):
            label = model.name
            if not model.is_active:
                label += " (неактивна)"
            self._model_combo.addItem(label, model.id)
            if str(model.id) == default_id:
                default_index = index
        if self._model_combo.count():
            self._model_combo.setCurrentIndex(default_index)

    def _selected_model(self) -> models.Model | None:
        model_id = self._model_combo.currentData()
        if model_id is None:
            return None
        return models.get_by_id(int(model_id))

    def _update_client_info(self) -> None:
        model = self._selected_model()
        if model is None:
            self._client_info.setText("Нет доступных моделей.")
            return
        self._client_info.setText(f"URL: {model.api_url}\nКлюч (.env): {model.api_id}")

    def _set_busy(self, busy: bool) -> None:
        self._improve_btn.setEnabled(not busy)
        self._model_combo.setEnabled(not busy)
        if busy:
            self._progress.show()
        else:
            self._progress.hide()

    def _on_improve_clicked(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return

        model = self._selected_model()
        if model is None:
            show_error(self, "Нет модели", "Добавьте модель на вкладке «Модели».")
            return

        api_key = config.get_api_key(model.api_id)
        if api_key is None:
            show_error(
                self,
                "API-ключ",
                config.missing_api_key_message(model.api_id, model.name),
            )
            return

        self._reset_content()
        self._set_busy(True)
        self._status_label.setText(f"Отправка запроса ({model.name})…")

        self._worker = ImprovePromptWorker(self._original, model)
        self._worker.finished_ok.connect(self._on_worker_ok)
        self._worker.finished_error.connect(self._on_worker_err)
        self._worker.start()

    def _reset_content(self) -> None:
        self._has_results = False
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._content_layout.addWidget(
            self._make_section("Исходный", self._original, readonly=True)
        )
        self._content_layout.addStretch()

    def _on_worker_ok(self, result: PromptImprovementResult) -> None:
        self._set_busy(False)
        self._has_results = True
        self.show_results(result)

    def _on_worker_err(self, message: str) -> None:
        self._set_busy(False)
        self.show_error(message)

    def show_results(self, result: PromptImprovementResult) -> None:
        self._status_label.setText("Ответ получен")
        self._progress.hide()

        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if result.partial_parse:
            warning = QLabel(
                "Ответ модели распознан не полностью. Проверьте улучшенный вариант."
            )
            warning.setWordWrap(True)
            self._content_layout.addWidget(warning)

        self._content_layout.addWidget(
            self._make_section("Исходный", result.original, readonly=True)
        )
        self._content_layout.addWidget(
            self._make_section("Улучшенный", result.improved, apply_text=result.improved)
        )

        for index, alternative in enumerate(result.alternatives, start=1):
            self._content_layout.addWidget(
                self._make_section(
                    f"Альтернатива {index}",
                    alternative,
                    apply_text=alternative,
                )
            )

        adaptations = {
            key: result.adaptations[key]
            for key in prompt_assistant.ADAPTATION_LABELS
            if result.adaptations.get(key)
        }
        if adaptations:
            group = QGroupBox("Адаптации")
            group_layout = QVBoxLayout(group)
            for key, text in adaptations.items():
                label = prompt_assistant.ADAPTATION_LABELS[key]
                group_layout.addWidget(
                    self._make_section(label, text, apply_text=text)
                )
            self._content_layout.addWidget(group)

        self._content_layout.addStretch()

    def show_error(self, message: str) -> None:
        self._status_label.setText("Ошибка запроса")
        self._progress.hide()
        error_label = QLabel(message)
        error_label.setWordWrap(True)
        error_label.setStyleSheet("color: #c0392b;")
        self._content_layout.insertWidget(0, error_label)

    def _make_section(
        self,
        title: str,
        text: str,
        *,
        readonly: bool = False,
        apply_text: str | None = None,
    ) -> QWidget:
        box = QGroupBox(title)
        box_layout = QVBoxLayout(box)

        editor = QTextEdit()
        editor.setPlainText(text)
        editor.setReadOnly(readonly)
        editor.setMinimumHeight(80)
        box_layout.addWidget(editor)

        if apply_text is not None:
            apply_btn = QPushButton("Подставить в поле ввода")
            apply_btn.clicked.connect(lambda _checked=False, t=apply_text: self._apply(t))
            box_layout.addWidget(apply_btn)

        return box

    def _apply(self, text: str) -> None:
        self._on_apply(text)
        show_info(self, "Подставлено", "Выбранный вариант подставлен в поле ввода промта.")


class ModelEditDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        model: models.Model | None = None,
    ) -> None:
        super().__init__(parent)
        self._model = model
        self.setWindowTitle("Редактировать модель" if model else "Добавить модель")
        self.setMinimumWidth(480)

        self.name_edit = QLineEdit(model.name if model else "")
        self.url_edit = QLineEdit(model.api_url if model else "https://openrouter.ai/api/v1/chat/completions")
        self.api_id_edit = QLineEdit(model.api_id if model else "OPENROUTER_API_KEY")
        self.active_check = QCheckBox("Активна")
        self.active_check.setChecked(model.is_active if model else True)

        form = QFormLayout()
        form.addRow("Имя / ID модели API:", self.name_edit)
        form.addRow("URL API:", self.url_edit)
        form.addRow("Переменная ключа (.env):", self.api_id_edit)
        form.addRow("", self.active_check)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def get_data(self) -> tuple[str, str, str, bool]:
        return (
            self.name_edit.text(),
            self.url_edit.text(),
            self.api_id_edit.text(),
            self.active_check.isChecked(),
        )


class PromptEditDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        prompt: db.Prompt | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Редактировать промт" if prompt else "Добавить промт")
        self.setMinimumSize(520, 320)

        self.tags_edit = QLineEdit(prompt.tags if prompt else "")
        self.tags_edit.setPlaceholderText("Теги (через запятую)")

        self.text_edit = QTextEdit(prompt.text if prompt else "")
        self.text_edit.setPlaceholderText("Введите текст промта…")
        self.text_edit.setMinimumHeight(160)

        form = QFormLayout()
        form.addRow("Теги:", self.tags_edit)
        form.addRow("Промт:", self.text_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def get_data(self) -> tuple[str, str]:
        return (
            self.text_edit.toPlainText().strip(),
            self.tags_edit.text().strip(),
        )


class RequestTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = ResultSession()
        self._worker: SendWorker | None = None
        self._updating_table = False

        self.prompt_combo = QComboBox()
        self.prompt_combo.setPlaceholderText("Сохранённые промты…")
        self.prompt_combo.currentIndexChanged.connect(self._on_prompt_selected)

        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self._reload_prompts)

        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("Теги (через запятую)")

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("Введите промт…")
        self.prompt_edit.setMinimumHeight(100)

        self.improve_btn = QPushButton("Улучшить промт")
        self.improve_btn.clicked.connect(self._on_improve_prompt)

        self.send_btn = QPushButton("Отправить")
        self.send_btn.clicked.connect(self._on_send)

        self.status_label = QLabel("Готово")

        self.results_table = QTableWidget(0, 4)
        self.results_table.setHorizontalHeaderLabels(["Модель", "Ответ", "Выбрать", ""])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.setWordWrap(True)
        self.results_table.verticalHeader().setMinimumSectionSize(56)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setToolTip("Двойной клик по ответу — просмотр в Markdown")
        self.results_table.itemChanged.connect(self._on_table_item_changed)
        self.results_table.cellDoubleClicked.connect(self._on_result_cell_double_clicked)

        select_all_btn = QPushButton("Выбрать все")
        select_all_btn.clicked.connect(self._select_all)
        deselect_all_btn = QPushButton("Снять все")
        deselect_all_btn.clicked.connect(self._deselect_all)
        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(self._on_save)
        new_btn = QPushButton("Новый запрос")
        new_btn.clicked.connect(self._on_new_request)
        export_md_btn = QPushButton("Экспорт Markdown")
        export_md_btn.clicked.connect(lambda: self._export("md"))
        export_json_btn = QPushButton("Экспорт JSON")
        export_json_btn.clicked.connect(lambda: self._export("json"))

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("История:"))
        top_row.addWidget(self.prompt_combo, stretch=1)
        top_row.addWidget(refresh_btn)

        btn_row = QHBoxLayout()
        btn_row.addWidget(select_all_btn)
        btn_row.addWidget(deselect_all_btn)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(new_btn)
        btn_row.addWidget(export_md_btn)
        btn_row.addWidget(export_json_btn)
        btn_row.addStretch()

        send_row = QHBoxLayout()
        send_row.addWidget(self.improve_btn)
        send_row.addWidget(self.send_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(QLabel("Теги:"))
        layout.addWidget(self.tags_edit)
        layout.addWidget(QLabel("Промт:"))
        layout.addWidget(self.prompt_edit)
        layout.addLayout(send_row)
        layout.addWidget(self.status_label)
        layout.addWidget(self.results_table, stretch=1)
        layout.addLayout(btn_row)

        self._reload_prompts()

    def _reload_prompts(self) -> None:
        self.prompt_combo.blockSignals(True)
        self.prompt_combo.clear()
        self.prompt_combo.addItem("— новый промт —", None)
        for prompt in db.list_prompts(order_by="created_at", order_dir="DESC"):
            label = prompt.text.replace("\n", " ")
            if len(label) > 80:
                label = label[:77] + "…"
            self.prompt_combo.addItem(f"{prompt.created_at[:10]} | {label}", prompt.id)
        self.prompt_combo.blockSignals(False)

    def _on_prompt_selected(self, index: int) -> None:
        if index <= 0:
            self.session.prompt_id = None
            return
        prompt_id = self.prompt_combo.itemData(index)
        if prompt_id is None:
            return
        prompt = db.get_prompt(int(prompt_id))
        if prompt is None:
            return
        self.prompt_edit.setPlainText(prompt.text)
        self.tags_edit.setText(prompt.tags)
        self.session.set_prompt_from_history(prompt.id, prompt.text, prompt.tags)

    def _set_request_buttons_enabled(self, enabled: bool) -> None:
        self.send_btn.setEnabled(enabled)
        self.improve_btn.setEnabled(enabled)

    def _apply_improved_prompt(self, text: str) -> None:
        self.prompt_edit.setPlainText(text)
        self.session.prompt_id = None

    def _on_improve_prompt(self) -> None:
        prompt_text = self.prompt_edit.toPlainText().strip()
        if not prompt_text:
            show_error(self, "Промт пустой", "Введите текст запроса для улучшения.")
            return

        if not models.list_all():
            show_error(
                self,
                "Нет моделей",
                "Добавьте хотя бы одну модель на вкладке «Модели».",
            )
            return

        dialog = PromptImproveDialog(self, prompt_text, self._apply_improved_prompt)
        dialog.exec()
        self.status_label.setText("Готово")

    def _on_send(self) -> None:
        prompt_text = self.prompt_edit.toPlainText().strip()
        if not prompt_text:
            show_error(self, "Промт пустой", "Введите текст запроса.")
            return

        active = models.list_active()
        if not active:
            show_error(
                self,
                "Нет активных моделей",
                "Включите хотя бы одну модель на вкладке «Модели».",
            )
            return

        if self.session.prompt_id is not None:
            stored = db.get_prompt(self.session.prompt_id)
            if stored is None or stored.text != prompt_text:
                self.session.prompt_id = None

        if self.session.prompt_id is None:
            self.session.prepare_new_prompt(prompt_text, self.tags_edit.text().strip())
        else:
            self.session.prompt_text = prompt_text
            self.session.prompt_tags = self.tags_edit.text().strip()

        self.session.rows.clear()
        self._refresh_results_table()

        self._set_request_buttons_enabled(False)
        self.status_label.setText("Отправка запросов…")

        self._worker = SendWorker(prompt_text, active)
        self._worker.finished_ok.connect(self._on_send_finished)
        self._worker.finished_error.connect(self._on_send_error)
        self._worker.start()

    def _on_send_finished(self, responses: list) -> None:
        self._set_request_buttons_enabled(True)
        self.session.fill_from_responses(responses)
        self._refresh_results_table()
        self.status_label.setText(f"Получено ответов: {len(responses)}")

    def _on_send_error(self, message: str) -> None:
        self._set_request_buttons_enabled(True)
        self.status_label.setText("Ошибка отправки")
        show_error(self, "Ошибка", message)

    def _refresh_results_table(self) -> None:
        self._updating_table = True
        self.results_table.setSortingEnabled(False)
        self.results_table.setRowCount(len(self.session.rows))
        for row_idx, row in enumerate(self.session.rows):
            name_item = QTableWidgetItem(row.model_name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self.results_table.setItem(row_idx, 0, name_item)

            preview = response_preview(row.response_text)
            text_item = QTableWidgetItem(preview)
            text_item.setFlags(text_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            text_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            )
            text_item.setData(Qt.ItemDataRole.UserRole, row.response_text)
            text_item.setToolTip("Двойной клик — полный ответ")
            self.results_table.setItem(row_idx, 1, text_item)

            check_item = QTableWidgetItem()
            check_item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            check_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            state = Qt.CheckState.Checked if row.selected else Qt.CheckState.Unchecked
            check_item.setCheckState(state)
            self.results_table.setItem(row_idx, 2, check_item)

            add_open_button(
                self.results_table,
                row_idx,
                3,
                lambda _checked=False, r=row_idx: self._open_result_markdown(r),
            )

        self.results_table.resizeRowsToContents()
        self._updating_table = False

    def _open_result_markdown(self, row: int) -> None:
        if not (0 <= row < len(self.session.rows)):
            return
        item = self.session.rows[row]
        show_markdown_viewer(self, f"Ответ — {item.model_name}", item.response_text)

    def _on_result_cell_double_clicked(self, row: int, column: int) -> None:
        if column != 1 or not (0 <= row < len(self.session.rows)):
            return
        self._open_result_markdown(row)

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_table or item.column() != 2:
            return
        row_idx = item.row()
        selected = item.checkState() == Qt.CheckState.Checked
        self.session.set_selected(row_idx, selected)

    def _select_all(self) -> None:
        self.session.select_all()
        self._refresh_results_table()

    def _deselect_all(self) -> None:
        self.session.deselect_all()
        self._refresh_results_table()

    def _on_save(self) -> None:
        if not self.session.rows:
            show_error(self, "Нет данных", "Сначала отправьте промт и получите ответы.")
            return
        try:
            prompt_id, count = self.session.save_selected()
        except ValueError as exc:
            show_error(self, "Сохранение", str(exc))
            return

        self._refresh_results_table()
        self._reload_prompts()
        show_info(self, "Сохранено", f"Записано результатов: {count} (промт #{prompt_id}).")

    def _on_new_request(self) -> None:
        self.prompt_edit.clear()
        self.tags_edit.clear()
        self.prompt_combo.setCurrentIndex(0)
        self.session.clear()
        self._refresh_results_table()
        self.status_label.setText("Готово")

    def _export(self, fmt: str) -> None:
        if not self.session.rows:
            show_error(self, "Экспорт", "Нет результатов для экспорта.")
            return
        selected = self.session.get_selected_rows()
        if not selected:
            show_error(self, "Экспорт", "Отметьте хотя бы одну строку.")
            return

        prompt_text = self.session.prompt_text or self.prompt_edit.toPlainText()
        if fmt == "md":
            content = export_utils.export_selected_markdown(prompt_text, self.session.rows)
            filter_str = "Markdown (*.md)"
            default_name = "results.md"
        else:
            content = export_utils.export_selected_json(prompt_text, self.session.rows)
            filter_str = "JSON (*.json)"
            default_name = "results.json"

        path, _ = QFileDialog.getSaveFileName(self, "Сохранить файл", default_name, filter_str)
        if not path:
            return
        Path(path).write_text(content, encoding="utf-8")
        show_info(self, "Экспорт", f"Файл сохранён: {path}")


class ModelsTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по имени…")
        self.search_edit.textChanged.connect(self._reload)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Имя (А–Я)", "Имя (Я–А)", "Активные сначала"])
        self.sort_combo.currentIndexChanged.connect(self._reload)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "Имя", "URL", "Ключ (.env)", "Активна"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        add_btn = QPushButton("Добавить")
        add_btn.clicked.connect(self._add)
        edit_btn = QPushButton("Редактировать")
        edit_btn.clicked.connect(self._edit)
        delete_btn = QPushButton("Удалить")
        delete_btn.clicked.connect(self._delete)
        toggle_btn = QPushButton("Вкл/Выкл")
        toggle_btn.clicked.connect(self._toggle)
        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self._reload)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Поиск:"))
        search_row.addWidget(self.search_edit, stretch=1)
        search_row.addWidget(QLabel("Сортировка:"))
        search_row.addWidget(self.sort_combo)

        btn_row = QHBoxLayout()
        btn_row.addWidget(add_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addWidget(toggle_btn)
        btn_row.addWidget(refresh_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(search_row)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(btn_row)

        self._reload()

    def _reload(self) -> None:
        search = self.search_edit.text().strip() or None
        all_models = models.list_all()
        if search:
            needle = search.lower()
            all_models = [m for m in all_models if needle in m.name.lower()]

        sort_idx = self.sort_combo.currentIndex()
        if sort_idx == 0:
            all_models.sort(key=lambda m: m.name.lower())
        elif sort_idx == 1:
            all_models.sort(key=lambda m: m.name.lower(), reverse=True)
        else:
            all_models.sort(key=lambda m: (not m.is_active, m.name.lower()))

        self.table.clearSelection()
        self.table.setRowCount(len(all_models))
        for row_idx, model in enumerate(all_models):
            self.table.setItem(row_idx, 0, QTableWidgetItem(str(model.id)))
            self.table.setItem(row_idx, 1, QTableWidgetItem(model.name))
            self.table.setItem(row_idx, 2, QTableWidgetItem(model.api_url))
            self.table.setItem(row_idx, 3, QTableWidgetItem(model.api_id))
            active_item = QTableWidgetItem("Да" if model.is_active else "Нет")
            self.table.setItem(row_idx, 4, active_item)

    def _selected_model_id(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return int(self.table.item(rows[0].row(), 0).text())

    def _add(self) -> None:
        dialog = ModelEditDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            models.add(*dialog.get_data())
        except models.ValidationError as exc:
            show_error(self, "Ошибка", str(exc))
            return
        self._reload()

    def _edit(self) -> None:
        model_id = self._selected_model_id()
        if model_id is None:
            show_error(self, "Выбор", "Выберите модель в таблице.")
            return
        model = models.get_by_id(model_id)
        if model is None:
            return
        dialog = ModelEditDialog(self, model)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            models.update(model_id, *dialog.get_data())
        except models.ValidationError as exc:
            show_error(self, "Ошибка", str(exc))
            return
        self._reload()

    def _delete(self) -> None:
        model_id = self._selected_model_id()
        if model_id is None:
            show_error(self, "Выбор", "Выберите модель в таблице.")
            return
        answer = QMessageBox.question(
            self,
            "Удаление",
            f"Удалить модель #{model_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            models.delete(model_id)
        except models.ValidationError as exc:
            show_error(self, "Ошибка", str(exc))
            return
        self._reload()

    def _toggle(self) -> None:
        model_id = self._selected_model_id()
        if model_id is None:
            show_error(self, "Выбор", "Выберите модель в таблице.")
            return
        try:
            models.toggle_active(model_id)
        except models.ValidationError as exc:
            show_error(self, "Ошибка", str(exc))
            return
        self._reload()


class PromptsTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по тексту или тегам…")
        self.search_edit.textChanged.connect(self._reload)

        self.order_combo = QComboBox()
        self.order_combo.addItem("Дата (новые)", ("created_at", "DESC"))
        self.order_combo.addItem("Дата (старые)", ("created_at", "ASC"))
        self.order_combo.addItem("Текст (А–Я)", ("text", "ASC"))
        self.order_combo.addItem("Теги (А–Я)", ("tags", "ASC"))
        self.order_combo.currentIndexChanged.connect(self._reload)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Дата", "Промт", "Теги"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)

        add_btn = QPushButton("Добавить")
        add_btn.clicked.connect(self._add)
        view_btn = QPushButton("Просмотр")
        view_btn.clicked.connect(self._view)
        edit_btn = QPushButton("Редактировать")
        edit_btn.clicked.connect(self._edit)
        delete_btn = QPushButton("Удалить")
        delete_btn.clicked.connect(self._delete)
        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self._reload)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Поиск:"))
        search_row.addWidget(self.search_edit, stretch=1)
        search_row.addWidget(QLabel("Сортировка:"))
        search_row.addWidget(self.order_combo)

        btn_row = QHBoxLayout()
        btn_row.addWidget(add_btn)
        btn_row.addWidget(view_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addWidget(refresh_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(search_row)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(btn_row)

        self._reload()

    def _reload(self) -> None:
        search = self.search_edit.text().strip() or None
        order_by, order_dir = self.order_combo.currentData()
        prompts = db.list_prompts(search=search, order_by=order_by, order_dir=order_dir)

        self.table.clearSelection()
        self.table.setRowCount(len(prompts))
        for row_idx, prompt in enumerate(prompts):
            self.table.setItem(row_idx, 0, QTableWidgetItem(str(prompt.id)))
            self.table.setItem(row_idx, 1, QTableWidgetItem(prompt.created_at))
            self.table.setItem(row_idx, 2, QTableWidgetItem(prompt.text))
            self.table.setItem(row_idx, 3, QTableWidgetItem(prompt.tags))
        self.table.resizeRowsToContents()

    def _selected_prompt_id(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return int(self.table.item(rows[0].row(), 0).text())

    def _add(self) -> None:
        dialog = PromptEditDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        text, tags = dialog.get_data()
        if not text:
            show_error(self, "Ошибка", "Текст промта не может быть пустым.")
            return
        db.add_prompt(text, tags)
        self._reload()

    def _view(self) -> None:
        prompt_id = self._selected_prompt_id()
        if prompt_id is None:
            show_error(self, "Выбор", "Выберите промт в таблице.")
            return
        prompt = db.get_prompt(prompt_id)
        if prompt is None:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Промт #{prompt.id}")
        dialog.setMinimumSize(560, 400)

        info = QLabel(f"Дата: {prompt.created_at}  |  Теги: {prompt.tags or '—'}")
        text_view = QTextEdit()
        text_view.setPlainText(prompt.text)
        text_view.setReadOnly(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)

        layout = QVBoxLayout(dialog)
        layout.addWidget(info)
        layout.addWidget(text_view)
        layout.addWidget(buttons)
        dialog.exec()

    def _edit(self) -> None:
        prompt_id = self._selected_prompt_id()
        if prompt_id is None:
            show_error(self, "Выбор", "Выберите промт в таблице.")
            return
        prompt = db.get_prompt(prompt_id)
        if prompt is None:
            return
        dialog = PromptEditDialog(self, prompt)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        text, tags = dialog.get_data()
        if not text:
            show_error(self, "Ошибка", "Текст промта не может быть пустым.")
            return
        db.update_prompt(prompt_id, text, tags)
        self._reload()

    def _delete(self) -> None:
        prompt_id = self._selected_prompt_id()
        if prompt_id is None:
            show_error(self, "Выбор", "Выберите промт в таблице.")
            return
        answer = QMessageBox.question(
            self,
            "Удаление",
            f"Удалить промт #{prompt_id}?\nСвязанные результаты также будут удалены.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        db.delete_prompt(prompt_id)
        self._reload()

    def _on_cell_double_clicked(self, row: int, column: int) -> None:
        if column != 2:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        self.table.selectRow(row)
        self._view()


class ResultsTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск…")
        self.search_edit.textChanged.connect(self._reload)

        self.order_combo = QComboBox()
        self.order_combo.addItem("Дата (новые)", ("created_at", "DESC"))
        self.order_combo.addItem("Дата (старые)", ("created_at", "ASC"))
        self.order_combo.addItem("ID (возр.)", ("id", "ASC"))
        self.order_combo.currentIndexChanged.connect(self._reload)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Дата", "Модель", "Промт", "Ответ", "prompt_id", ""]
        )
        self.table.setColumnHidden(5, True)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setMinimumSectionSize(56)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)

        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self._reload)

        layout = QVBoxLayout(self)
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Поиск:"))
        search_row.addWidget(self.search_edit, stretch=1)
        search_row.addWidget(QLabel("Сортировка:"))
        search_row.addWidget(self.order_combo)
        layout.addLayout(search_row)
        layout.addWidget(self.table, stretch=1)
        layout.addWidget(refresh_btn)

        self._reload()

    def _reload(self) -> None:
        search = self.search_edit.text().strip() or None
        order_by, order_dir = self.order_combo.currentData()
        results = db.list_results(search=search, order_by=order_by, order_dir=order_dir)

        self.table.setRowCount(len(results))
        for row_idx, result in enumerate(results):
            self.table.setItem(row_idx, 0, QTableWidgetItem(str(result.id)))
            self.table.setItem(row_idx, 1, QTableWidgetItem(result.created_at))
            self.table.setItem(row_idx, 2, QTableWidgetItem(result.model_name or ""))
            prompt_preview = result.prompt_text or ""
            if len(prompt_preview) > 120:
                prompt_preview = prompt_preview[:117] + "…"
            self.table.setItem(row_idx, 3, QTableWidgetItem(prompt_preview))
            response_item = QTableWidgetItem(response_preview(result.response_text or ""))
            response_item.setData(Qt.ItemDataRole.UserRole, result.response_text or "")
            response_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            )
            response_item.setToolTip("Двойной клик — просмотр в Markdown")
            self.table.setItem(row_idx, 4, response_item)
            self.table.setItem(row_idx, 5, QTableWidgetItem(str(result.prompt_id)))
            add_open_button(
                self.table,
                row_idx,
                6,
                lambda _checked=False, r=row_idx: self._open_result_markdown(r),
            )
        self.table.resizeRowsToContents()

    def _open_result_markdown(self, row: int) -> None:
        item = self.table.item(row, 4)
        if item is None:
            return
        full_text = item.data(Qt.ItemDataRole.UserRole)
        if not full_text:
            return
        model_item = self.table.item(row, 2)
        model_name = model_item.text() if model_item else "модель"
        show_markdown_viewer(self, f"Ответ — {model_name}", str(full_text))

    def _on_cell_double_clicked(self, row: int, column: int) -> None:
        if column != 4:
            return
        self._open_result_markdown(row)


class AboutDialog(QDialog):
    """Краткая информация о программе."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("О программе")
        self.setMinimumWidth(480)

        icon_label = QLabel()
        icon = application_icon()
        if icon is not None:
            pixmap = icon.pixmap(64, 64)
            if not pixmap.isNull():
                icon_label.setPixmap(pixmap)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel(f"<h2>ChatList {APP_VERSION}</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        description = QLabel(
            "Приложение для отправки одного промта в несколько нейросетей "
            "и сравнения их ответов. Выбранные результаты сохраняются в SQLite."
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)

        stack = QLabel(
            "Python 3.11+ · PyQt6 · SQLite · httpx\n"
            "Лицензия: MIT"
        )
        stack.setAlignment(Qt.AlignmentFlag.AlignCenter)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(icon_label)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(stack)
        layout.addWidget(buttons)


class SettingsTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Светлая", app_appearance.THEME_LIGHT)
        self.theme_combo.addItem("Тёмная", app_appearance.THEME_DARK)

        self.font_size_combo = QComboBox()
        for size in app_appearance.FONT_SIZE_OPTIONS:
            self.font_size_combo.addItem(f"{size} pt", size)

        self.timeout_edit = QLineEdit()
        self.referer_edit = QLineEdit()
        self.title_edit = QLineEdit()
        self.assistant_model_combo = QComboBox()

        appearance_form = QFormLayout()
        appearance_form.addRow("Тема:", self.theme_combo)
        appearance_form.addRow("Размер шрифта:", self.font_size_combo)

        api_form = QFormLayout()
        api_form.addRow("Таймаут запроса (сек):", self.timeout_edit)
        api_form.addRow("OpenRouter Referer:", self.referer_edit)
        api_form.addRow("OpenRouter Title:", self.title_edit)
        api_form.addRow("Модель по умолчанию (ассистент):", self.assistant_model_combo)

        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(self._save)
        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self._load)

        appearance_group = QGroupBox("Внешний вид")
        appearance_group.setLayout(appearance_form)

        api_group = QGroupBox("Сеть и ассистент")
        api_group.setLayout(api_form)

        layout = QVBoxLayout(self)
        layout.addWidget(appearance_group)
        layout.addWidget(api_group)
        btn_row = QHBoxLayout()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(refresh_btn)
        layout.addLayout(btn_row)
        layout.addStretch()

        self._load()

    def _reload_assistant_models(self) -> None:
        self.assistant_model_combo.blockSignals(True)
        self.assistant_model_combo.clear()
        for model in models.list_all():
            label = model.name
            if not model.is_active:
                label += " (неактивна)"
            self.assistant_model_combo.addItem(label, model.id)
        self.assistant_model_combo.blockSignals(False)

    def _set_combo_by_data(self, combo: QComboBox, value) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return

    def _load(self) -> None:
        theme = app_appearance.normalize_theme(
            db.get_setting(app_appearance.SETTING_THEME, app_appearance.DEFAULT_THEME)
        )
        self._set_combo_by_data(self.theme_combo, theme)

        font_size = app_appearance.normalize_font_size(
            db.get_setting(
                app_appearance.SETTING_FONT_SIZE,
                str(app_appearance.DEFAULT_FONT_SIZE),
            )
        )
        self._set_combo_by_data(self.font_size_combo, font_size)

        self.timeout_edit.setText(db.get_setting("request_timeout", "60"))
        self.referer_edit.setText(db.get_setting("openrouter_referer", "http://localhost"))
        self.title_edit.setText(db.get_setting("openrouter_title", "ChatList"))
        self._reload_assistant_models()
        raw = db.get_setting("prompt_assistant_model_id", "").strip()
        if raw:
            for index in range(self.assistant_model_combo.count()):
                if str(self.assistant_model_combo.itemData(index)) == raw:
                    self.assistant_model_combo.setCurrentIndex(index)
                    break

    def _save(self) -> None:
        theme = self.theme_combo.currentData()
        if theme is not None:
            db.set_setting(app_appearance.SETTING_THEME, str(theme))

        font_size = self.font_size_combo.currentData()
        if font_size is not None:
            db.set_setting(app_appearance.SETTING_FONT_SIZE, str(font_size))

        db.set_setting("request_timeout", self.timeout_edit.text().strip())
        db.set_setting("openrouter_referer", self.referer_edit.text().strip())
        db.set_setting("openrouter_title", self.title_edit.text().strip())
        model_id = self.assistant_model_combo.currentData()
        if model_id is not None:
            db.set_setting("prompt_assistant_model_id", str(model_id))

        app_appearance.apply_appearance()
        show_info(self, "Настройки", "Настройки сохранены.")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ChatList")
        self.setMinimumSize(960, 640)
        icon = application_icon()
        if icon is not None:
            self.setWindowIcon(icon)

        self.request_tab = RequestTab()
        tabs = QTabWidget()
        tabs.addTab(self.request_tab, "Запрос")
        tabs.addTab(ModelsTab(), "Модели")
        tabs.addTab(PromptsTab(), "Промты")
        tabs.addTab(ResultsTab(), "Результаты")
        tabs.addTab(SettingsTab(), "Настройки")

        self.setCentralWidget(tabs)

        help_menu = self.menuBar().addMenu("Справка")
        about_action = help_menu.addAction("О программе")
        about_action.triggered.connect(self._show_about)

    def _show_about(self) -> None:
        AboutDialog(self).exec()


def main() -> None:
    setup_logging()
    config.load_env()
    db.init_db()
    seed.seed_if_empty()

    app = QApplication(sys.argv)
    icon = application_icon()
    if icon is not None:
        app.setWindowIcon(icon)
    app_appearance.apply_appearance(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
