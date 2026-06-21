"""Временная таблица результатов в памяти."""

from __future__ import annotations

from dataclasses import dataclass

import db
import network


@dataclass
class TempResultRow:
    model_id: int
    model_name: str
    response_text: str
    selected: bool = False


class ResultSession:
    """Сессия текущего запроса: промт и временные ответы моделей."""

    def __init__(self) -> None:
        self.clear()

    def clear(self) -> None:
        self.rows: list[TempResultRow] = []
        self.prompt_text: str = ""
        self.prompt_id: int | None = None
        self.prompt_tags: str = ""

    def prepare_new_prompt(self, text: str, tags: str = "") -> None:
        self.clear()
        self.prompt_text = text
        self.prompt_tags = tags

    def set_prompt_from_history(
        self,
        prompt_id: int,
        text: str,
        tags: str = "",
    ) -> None:
        self.clear()
        self.prompt_id = prompt_id
        self.prompt_text = text
        self.prompt_tags = tags

    def fill_from_responses(self, responses: list[network.ModelResponse]) -> None:
        self.rows = [
            TempResultRow(
                model_id=item.model.id,
                model_name=item.model.name,
                response_text=item.response_text,
                selected=False,
            )
            for item in responses
        ]

    def select_all(self) -> None:
        for row in self.rows:
            row.selected = True

    def deselect_all(self) -> None:
        for row in self.rows:
            row.selected = False

    def set_selected(self, index: int, selected: bool) -> None:
        if 0 <= index < len(self.rows):
            self.rows[index].selected = selected

    def get_selected_rows(self) -> list[TempResultRow]:
        return [row for row in self.rows if row.selected]

    def save_selected(self) -> tuple[int, int]:
        """Сохранить выбранные строки в БД. Возвращает (prompt_id, количество)."""
        selected = self.get_selected_rows()
        if not selected:
            raise ValueError("Нет выбранных результатов для сохранения.")

        if self.prompt_id is None:
            self.prompt_id = db.add_prompt(self.prompt_text, self.prompt_tags)

        items = [(row.model_id, row.response_text) for row in selected]
        db.save_results(self.prompt_id, items)
        count = len(items)
        saved_prompt_id = self.prompt_id
        self.clear()
        return saved_prompt_id, count
