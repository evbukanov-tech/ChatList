"""Загрузка переменных окружения и получение API-ключей."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_DIR = Path(__file__).resolve().parent
_ENV_LOADED = False


def load_env(env_path: str | Path | None = None) -> None:
    """Загрузить переменные из .env и .env.local (локальный файл имеет приоритет)."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    if env_path is not None:
        load_dotenv(env_path)
    else:
        load_dotenv(_PROJECT_DIR / ".env")
        load_dotenv(_PROJECT_DIR / ".env.local", override=True)

    _ENV_LOADED = True


def get_api_key(api_id: str) -> str | None:
    """
    Получить API-ключ по имени переменной окружения.
    api_id — значение поля api_id из таблицы models (например OPENROUTER_API_KEY).
    """
    load_env()
    value = os.getenv(api_id)
    if value is None or not value.strip():
        return None
    return value.strip().strip("[]")


def missing_api_key_message(api_id: str, model_name: str) -> str:
    """Сообщение об отсутствующем ключе для отображения в интерфейсе."""
    return (
        f"API-ключ не найден для модели «{model_name}». "
        f"Добавьте переменную {api_id} в файл .env или .env.local "
        f"(см. .env.example)."
    )
