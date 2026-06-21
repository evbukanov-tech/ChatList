"""Логика работы с нейросетями (CRUD, активация, валидация)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from urllib.parse import urlparse

import db


class ValidationError(ValueError):
    """Ошибка валидации полей модели."""


@dataclass
class Model:
    id: int
    name: str
    api_url: str
    api_id: str
    is_active: bool

    @classmethod
    def from_row(cls, row: db.ModelRow) -> Model:
        return cls(
            id=row.id,
            name=row.name,
            api_url=row.api_url,
            api_id=row.api_id,
            is_active=row.is_active,
        )


def _validate_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValidationError("Имя модели не может быть пустым.")
    return name


def _validate_api_url(api_url: str) -> str:
    api_url = api_url.strip()
    parsed = urlparse(api_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValidationError("Укажите корректный URL API (http или https).")
    return api_url


def _validate_api_id(api_id: str) -> str:
    api_id = api_id.strip()
    if not api_id:
        raise ValidationError("Имя переменной API-ключа (api_id) не может быть пустым.")
    if not api_id.replace("_", "").isalnum():
        raise ValidationError(
            "api_id должен содержать только буквы, цифры и подчёркивания "
            "(например OPENAI_API_KEY)."
        )
    return api_id


def _check_name_unique(name: str, exclude_id: int | None = None) -> None:
    existing = db.get_model_by_name(name)
    if existing and (exclude_id is None or existing.id != exclude_id):
        raise ValidationError(f"Модель с именем «{name}» уже существует.")


def _ensure_db() -> None:
    db.init_db()


def list_all() -> list[Model]:
    _ensure_db()
    return [Model.from_row(row) for row in db.list_models()]


def list_active() -> list[Model]:
    _ensure_db()
    return [Model.from_row(row) for row in db.list_active_models()]


def get_by_id(model_id: int) -> Model | None:
    _ensure_db()
    row = db.get_model(model_id)
    return Model.from_row(row) if row else None


def add(
    name: str,
    api_url: str,
    api_id: str,
    is_active: bool = True,
) -> Model:
    _ensure_db()
    name = _validate_name(name)
    api_url = _validate_api_url(api_url)
    api_id = _validate_api_id(api_id)
    _check_name_unique(name)

    model_id = db.add_model(name, api_url, api_id, is_active)
    row = db.get_model(model_id)
    assert row is not None
    return Model.from_row(row)


def update(
    model_id: int,
    name: str,
    api_url: str,
    api_id: str,
    is_active: bool,
) -> Model:
    _ensure_db()
    existing = db.get_model(model_id)
    if existing is None:
        raise ValidationError(f"Модель с id={model_id} не найдена.")

    name = _validate_name(name)
    api_url = _validate_api_url(api_url)
    api_id = _validate_api_id(api_id)
    _check_name_unique(name, exclude_id=model_id)

    db.update_model(model_id, name, api_url, api_id, is_active)
    row = db.get_model(model_id)
    assert row is not None
    return Model.from_row(row)


def delete(model_id: int) -> None:
    _ensure_db()
    if db.get_model(model_id) is None:
        raise ValidationError(f"Модель с id={model_id} не найдена.")
    try:
        db.delete_model(model_id)
    except sqlite3.IntegrityError as exc:
        raise ValidationError(
            "Нельзя удалить модель: в базе есть сохранённые ответы этой модели. "
            "Сначала удалите связанные результаты на вкладке «Результаты»."
        ) from exc


def toggle_active(model_id: int) -> Model:
    _ensure_db()
    row = db.get_model(model_id)
    if row is None:
        raise ValidationError(f"Модель с id={model_id} не найдена.")
    db.set_model_active(model_id, not row.is_active)
    updated = db.get_model(model_id)
    assert updated is not None
    return Model.from_row(updated)


def set_active(model_id: int, is_active: bool) -> Model:
    _ensure_db()
    if db.get_model(model_id) is None:
        raise ValidationError(f"Модель с id={model_id} не найдена.")
    db.set_model_active(model_id, is_active)
    updated = db.get_model(model_id)
    assert updated is not None
    return Model.from_row(updated)


def get_prompt_assistant_model() -> Model | None:
    """Модель для AI-ассистента улучшения промтов (из settings)."""
    _ensure_db()
    raw = db.get_setting("prompt_assistant_model_id", "").strip()
    if raw:
        try:
            model = get_by_id(int(raw))
            if model is not None:
                return model
        except ValueError:
            pass

    active = list_active()
    if active:
        return active[0]
    all_models = list_all()
    return all_models[0] if all_models else None
