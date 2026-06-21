"""Тестовая программа: просмотр SQLite-файла, список таблиц и CRUD с пагинацией."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

PAGE_SIZE = 50
ROWID_COLUMN = "__rowid__"


def show_error(parent: QWidget | None, title: str, message: str) -> None:
    QMessageBox.critical(parent, title, message)


def show_info(parent: QWidget | None, title: str, message: str) -> None:
    QMessageBox.information(parent, title, message)


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class SqliteDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def list_tables(self) -> list[str]:
        cur = self.conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
        return [row[0] for row in cur.fetchall()]

    def table_columns(self, table: str) -> list[dict[str, Any]]:
        cur = self.conn.execute(f"PRAGMA table_info({quote_identifier(table)})")
        return [
            {
                "name": row["name"],
                "type": row["type"],
                "notnull": bool(row["notnull"]),
                "pk": bool(row["pk"]),
                "default": row["dflt_value"],
            }
            for row in cur.fetchall()
        ]

    def primary_key_columns(self, table: str) -> list[str]:
        return [col["name"] for col in self.table_columns(table) if col["pk"]]

    def uses_rowid(self, table: str) -> bool:
        return not self.primary_key_columns(table)

    def count_rows(self, table: str) -> int:
        cur = self.conn.execute(f"SELECT COUNT(*) FROM {quote_identifier(table)}")
        return int(cur.fetchone()[0])

    def fetch_page(self, table: str, offset: int, limit: int) -> tuple[list[str], list[sqlite3.Row]]:
        columns = self.table_columns(table)
        col_names = [col["name"] for col in columns]
        if self.uses_rowid(table):
            select_sql = f"SELECT rowid AS {ROWID_COLUMN}, * FROM {quote_identifier(table)}"
            display_columns = [ROWID_COLUMN, *col_names]
        else:
            select_sql = f"SELECT * FROM {quote_identifier(table)}"
            display_columns = col_names

        cur = self.conn.execute(
            f"{select_sql} LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return display_columns, cur.fetchall()

    def insert_row(self, table: str, values: dict[str, Any]) -> None:
        if not values:
            raise ValueError("Нет данных для вставки")
        columns = ", ".join(quote_identifier(name) for name in values)
        placeholders = ", ".join("?" for _ in values)
        sql = f"INSERT INTO {quote_identifier(table)} ({columns}) VALUES ({placeholders})"
        self.conn.execute(sql, tuple(values.values()))
        self.conn.commit()

    def update_row(
        self,
        table: str,
        key_values: dict[str, Any],
        values: dict[str, Any],
    ) -> None:
        if not values:
            raise ValueError("Нет данных для обновления")
        if not key_values:
            raise ValueError("Не указан ключ строки")

        set_clause = ", ".join(f"{quote_identifier(name)} = ?" for name in values)
        where_clause, where_params = self._where_clause(key_values)
        sql = (
            f"UPDATE {quote_identifier(table)} SET {set_clause} "
            f"WHERE {where_clause}"
        )
        self.conn.execute(sql, (*values.values(), *where_params))
        self.conn.commit()

    def delete_row(self, table: str, key_values: dict[str, Any]) -> None:
        if not key_values:
            raise ValueError("Не указан ключ строки")
        where_clause, where_params = self._where_clause(key_values)
        sql = f"DELETE FROM {quote_identifier(table)} WHERE {where_clause}"
        self.conn.execute(sql, where_params)
        self.conn.commit()

    @staticmethod
    def _where_clause(key_values: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
        parts: list[str] = []
        params: list[Any] = []
        for name, value in key_values.items():
            if name == ROWID_COLUMN:
                parts.append("rowid = ?")
            else:
                parts.append(f"{quote_identifier(name)} = ?")
            params.append(value)
        return " AND ".join(parts), tuple(params)


class RowEditDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        columns: list[dict[str, Any]],
        values: dict[str, Any] | None = None,
        read_only_keys: set[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(480)

        self._fields: dict[str, QLineEdit] = {}
        read_only_keys = read_only_keys or set()
        form = QFormLayout()

        for column in columns:
            name = column["name"]
            if name == ROWID_COLUMN:
                continue

            field = QLineEdit()
            hint_parts = [column["type"] or "TEXT"]
            if column["pk"]:
                hint_parts.append("PK")
            if column["notnull"]:
                hint_parts.append("NOT NULL")
            field.setPlaceholderText(", ".join(hint_parts))

            if values and name in values and values[name] is not None:
                field.setText(str(values[name]))

            if name in read_only_keys:
                field.setReadOnly(True)

            self._fields[name] = field
            form.addRow(name, field)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def get_values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, field in self._fields.items():
            text = field.text().strip()
            if text:
                result[name] = text
        return result


class TableViewTab(QWidget):
    def __init__(self, database: SqliteDatabase, table_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.table_name = table_name
        self.page = 0
        self.page_size = PAGE_SIZE
        self.columns_meta = database.table_columns(table_name)
        self.pk_columns = database.primary_key_columns(table_name)
        self.uses_rowid = database.uses_rowid(table_name)

        title = QLabel(f"Таблица: {table_name}")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")

        self.table = QTableWidget(0, 0)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.page_label = QLabel()
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.valueChanged.connect(self._on_page_spin_changed)

        self.page_size_spin = QSpinBox()
        self.page_size_spin.setRange(10, 500)
        self.page_size_spin.setValue(PAGE_SIZE)
        self.page_size_spin.setSuffix(" строк")
        self.page_size_spin.valueChanged.connect(self._on_page_size_changed)

        prev_btn = QPushButton("← Назад")
        prev_btn.clicked.connect(self._prev_page)
        next_btn = QPushButton("Вперёд →")
        next_btn.clicked.connect(self._next_page)

        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self.reload)

        add_btn = QPushButton("Добавить")
        add_btn.clicked.connect(self._add_row)
        edit_btn = QPushButton("Изменить")
        edit_btn.clicked.connect(self._edit_row)
        delete_btn = QPushButton("Удалить")
        delete_btn.clicked.connect(self._delete_row)

        pagination_row = QHBoxLayout()
        pagination_row.addWidget(prev_btn)
        pagination_row.addWidget(self.page_label)
        pagination_row.addWidget(next_btn)
        pagination_row.addStretch()
        pagination_row.addWidget(QLabel("Страница:"))
        pagination_row.addWidget(self.page_spin)
        pagination_row.addWidget(QLabel("Размер:"))
        pagination_row.addWidget(self.page_size_spin)

        crud_row = QHBoxLayout()
        crud_row.addWidget(add_btn)
        crud_row.addWidget(edit_btn)
        crud_row.addWidget(delete_btn)
        crud_row.addStretch()
        crud_row.addWidget(refresh_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(self.table)
        layout.addLayout(pagination_row)
        layout.addLayout(crud_row)

        self.reload()

    def _total_pages(self) -> int:
        total = self.database.count_rows(self.table_name)
        if total == 0:
            return 1
        return (total + self.page_size - 1) // self.page_size

    def _row_key_values(self, row_data: dict[str, Any]) -> dict[str, Any]:
        if self.uses_rowid:
            return {ROWID_COLUMN: row_data[ROWID_COLUMN]}
        return {name: row_data[name] for name in self.pk_columns}

    def _selected_row_data(self) -> dict[str, Any] | None:
        row_idx = self.table.currentRow()
        if row_idx < 0:
            return None
        data: dict[str, Any] = {}
        for col_idx in range(self.table.columnCount()):
            header = self.table.horizontalHeaderItem(col_idx).text()
            item = self.table.item(row_idx, col_idx)
            data[header] = item.text() if item else ""
        return data

    def reload(self) -> None:
        try:
            total = self.database.count_rows(self.table_name)
            total_pages = self._total_pages()
            if self.page >= total_pages:
                self.page = max(0, total_pages - 1)

            columns, rows = self.database.fetch_page(
                self.table_name,
                self.page * self.page_size,
                self.page_size,
            )

            self.table.setColumnCount(len(columns))
            self.table.setHorizontalHeaderLabels(columns)
            self.table.setRowCount(len(rows))

            for row_idx, row in enumerate(rows):
                for col_idx, col_name in enumerate(columns):
                    value = row[col_name]
                    text = "" if value is None else str(value)
                    self.table.setItem(row_idx, col_idx, QTableWidgetItem(text))

            self.page_label.setText(
                f"Страница {self.page + 1} из {total_pages} (всего записей: {total})"
            )

            self.page_spin.blockSignals(True)
            self.page_spin.setMaximum(total_pages)
            self.page_spin.setValue(self.page + 1)
            self.page_spin.blockSignals(False)
        except sqlite3.Error as exc:
            show_error(self, "Ошибка чтения", str(exc))

    def _prev_page(self) -> None:
        if self.page > 0:
            self.page -= 1
            self.reload()

    def _next_page(self) -> None:
        if self.page + 1 < self._total_pages():
            self.page += 1
            self.reload()

    def _on_page_spin_changed(self, value: int) -> None:
        new_page = value - 1
        if new_page != self.page:
            self.page = new_page
            self.reload()

    def _on_page_size_changed(self, value: int) -> None:
        if value != self.page_size:
            self.page_size = value
            self.page = 0
            self.reload()

    def _add_row(self) -> None:
        dialog = RowEditDialog(self, f"Добавить — {self.table_name}", self.columns_meta)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.database.insert_row(self.table_name, dialog.get_values())
            self.reload()
            show_info(self, "Готово", "Запись добавлена.")
        except sqlite3.Error as exc:
            show_error(self, "Ошибка добавления", str(exc))

    def _edit_row(self) -> None:
        row_data = self._selected_row_data()
        if row_data is None:
            show_error(self, "Изменение", "Выберите строку для редактирования.")
            return

        read_only = set(self.pk_columns)
        if self.uses_rowid:
            read_only.add(ROWID_COLUMN)

        dialog = RowEditDialog(
            self,
            f"Изменить — {self.table_name}",
            self.columns_meta,
            values=row_data,
            read_only_keys=read_only,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_values = dialog.get_values()
        for key in read_only:
            new_values.pop(key, None)
        if not new_values:
            show_error(self, "Изменение", "Нет полей для обновления.")
            return

        try:
            self.database.update_row(
                self.table_name,
                self._row_key_values(row_data),
                new_values,
            )
            self.reload()
            show_info(self, "Готово", "Запись обновлена.")
        except sqlite3.Error as exc:
            show_error(self, "Ошибка изменения", str(exc))

    def _delete_row(self) -> None:
        row_data = self._selected_row_data()
        if row_data is None:
            show_error(self, "Удаление", "Выберите строку для удаления.")
            return

        answer = QMessageBox.question(
            self,
            "Удаление",
            "Удалить выбранную запись?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.database.delete_row(self.table_name, self._row_key_values(row_data))
            self.reload()
            show_info(self, "Готово", "Запись удалена.")
        except sqlite3.Error as exc:
            show_error(self, "Ошибка удаления", str(exc))


class MainWindow(QMainWindow):
    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Тест SQLite")
        self.resize(960, 640)

        self.database: SqliteDatabase | None = None
        self.db_path_label = QLabel("Файл базы не выбран")
        self.tables_widget = QTableWidget(0, 2)
        self.tables_widget.setHorizontalHeaderLabels(["Таблица", ""])
        self.tables_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tables_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tables_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        open_file_btn = QPushButton("Открыть файл SQLite…")
        open_file_btn.clicked.connect(self._open_file_dialog)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)

        tables_tab = QWidget()
        tables_layout = QVBoxLayout(tables_tab)
        tables_layout.addWidget(self.db_path_label)
        tables_layout.addWidget(open_file_btn)
        tables_layout.addWidget(self.tables_widget)
        self.tabs.addTab(tables_tab, "Таблицы")

        self.setCentralWidget(self.tabs)

        if db_path and db_path.is_file():
            self.open_database(db_path)

    def _open_file_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите файл SQLite",
            str(Path.cwd()),
            "SQLite (*.db *.sqlite *.sqlite3);;Все файлы (*.*)",
        )
        if path:
            self.open_database(Path(path))

    def open_database(self, path: Path) -> None:
        if self.database is not None:
            self.database.close()

        try:
            self.database = SqliteDatabase(path)
        except sqlite3.Error as exc:
            show_error(self, "Ошибка", f"Не удалось открыть базу:\n{exc}")
            self.database = None
            return

        self.db_path_label.setText(f"Файл: {path}")
        self.setWindowTitle(f"Тест SQLite — {path.name}")
        self._reload_tables_list()

    def _reload_tables_list(self) -> None:
        self.tables_widget.setRowCount(0)
        if self.database is None:
            return

        try:
            tables = self.database.list_tables()
        except sqlite3.Error as exc:
            show_error(self, "Ошибка", str(exc))
            return

        self.tables_widget.setRowCount(len(tables))
        for row_idx, table_name in enumerate(tables):
            self.tables_widget.setItem(row_idx, 0, QTableWidgetItem(table_name))

            open_btn = QPushButton("Открыть")
            open_btn.clicked.connect(lambda _checked=False, name=table_name: self._open_table(name))
            self.tables_widget.setCellWidget(row_idx, 1, open_btn)

    def _open_table(self, table_name: str) -> None:
        if self.database is None:
            show_error(self, "Ошибка", "Сначала откройте файл базы данных.")
            return

        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if isinstance(widget, TableViewTab) and widget.table_name == table_name:
                self.tabs.setCurrentIndex(index)
                return

        tab = TableViewTab(self.database, table_name)
        index = self.tabs.addTab(tab, table_name)
        self.tabs.setCurrentIndex(index)

    def _close_tab(self, index: int) -> None:
        if index == 0:
            return
        self.tabs.removeTab(index)

    def closeEvent(self, event) -> None:
        if self.database is not None:
            self.database.close()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    db_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    window = MainWindow(db_arg)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
