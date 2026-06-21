"""Начальные данные при первом запуске."""

from __future__ import annotations

import db

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

DEFAULT_MODELS: list[tuple[str, str, str, bool]] = [
    ("openai/gpt-4o-mini", OPENROUTER_URL, "OPENROUTER_API_KEY", True),
    ("google/gemini-2.0-flash-001", OPENROUTER_URL, "OPENROUTER_API_KEY", True),
    ("anthropic/claude-3.5-sonnet", OPENROUTER_URL, "OPENROUTER_API_KEY", True),
    ("meta-llama/llama-3.3-70b-instruct", OPENROUTER_URL, "OPENROUTER_API_KEY", False),
]

DEFAULT_SETTINGS: dict[str, str] = {
    "request_timeout": "60",
    "openrouter_referer": "http://localhost",
    "openrouter_title": "ChatList",
    "ui_theme": "light",
    "ui_font_size": "10",
}


def seed_if_empty() -> None:
    """Заполнить БД примерами моделей OpenRouter и настройками по умолчанию."""
    db.init_db()

    if not db.list_models():
        for name, api_url, api_id, is_active in DEFAULT_MODELS:
            db.add_model(name, api_url, api_id, is_active)

    for key, value in DEFAULT_SETTINGS.items():
        if not db.get_setting(key):
            db.set_setting(key, value)

    if not db.get_setting("prompt_assistant_model_id"):
        active = db.list_active_models()
        if active:
            db.set_setting("prompt_assistant_model_id", str(active[0].id))
        else:
            all_models = db.list_models()
            if all_models:
                db.set_setting("prompt_assistant_model_id", str(all_models[0].id))
