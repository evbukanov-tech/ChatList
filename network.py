"""Отправка запросов к API нейросетей."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import httpx

import config
import db
import models

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60.0


def _build_headers(api_key: str, api_url: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if "openrouter.ai" in api_url:
        headers["HTTP-Referer"] = db.get_setting("openrouter_referer", "http://localhost")
        headers["X-Title"] = db.get_setting("openrouter_title", "ChatList")
    return headers


def _get_timeout() -> float:
    db.init_db()
    raw = db.get_setting("request_timeout", str(int(DEFAULT_TIMEOUT)))
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT


def send_openai_compatible(
    api_url: str,
    api_key: str,
    prompt: str,
    model_name: str,
    timeout: float | None = None,
) -> str:
    """
    Отправить промт в OpenAI-совместимый API.
    Подходит для OpenAI, DeepSeek, Groq и аналогичных сервисов.
    """
    timeout = timeout if timeout is not None else _get_timeout()
    headers = _build_headers(api_key, api_url)
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(api_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        return f"Ошибка: превышено время ожидания ({timeout} с)."
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500]
        return f"Ошибка HTTP {exc.response.status_code}: {body}"
    except httpx.RequestError as exc:
        return f"Ошибка сети: {exc}"
    except ValueError:
        return "Ошибка: API вернул невалидный JSON."

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return "Ошибка: неожиданный формат ответа API."


def send_prompt(
    api_url: str,
    api_key: str,
    prompt: str,
    model_name: str,
    timeout: float | None = None,
) -> str:
    """Единая точка входа: url, ключ, промт → текст ответа или сообщение об ошибке."""
    return send_openai_compatible(api_url, api_key, prompt, model_name, timeout)


@dataclass
class ModelResponse:
    model: models.Model
    response_text: str
    error: bool


def send_to_model(model: models.Model, prompt: str) -> ModelResponse:
    api_key = config.get_api_key(model.api_id)
    if api_key is None:
        text = config.missing_api_key_message(model.api_id, model.name)
        logger.warning("Отсутствует API-ключ: %s (%s)", model.name, model.api_id)
        return ModelResponse(model=model, response_text=text, error=True)

    logger.info("Запрос к модели %s (%s)", model.name, model.api_url)
    text = send_prompt(model.api_url, api_key, prompt, model.name)
    is_error = text.startswith("Ошибка")
    if is_error:
        logger.error("Ошибка ответа %s: %s", model.name, text)
    else:
        logger.info("Ответ от %s получен (%d символов)", model.name, len(text))
    return ModelResponse(model=model, response_text=text, error=is_error)


def send_to_all_models(
    model_list: list[models.Model],
    prompt: str,
    parallel: bool = True,
) -> list[ModelResponse]:
    """Отправить промт во все переданные модели."""
    if not model_list:
        return []

    if not parallel or len(model_list) == 1:
        return [send_to_model(model, prompt) for model in model_list]

    results: list[ModelResponse | None] = [None] * len(model_list)
    with ThreadPoolExecutor(max_workers=len(model_list)) as executor:
        future_to_index = {
            executor.submit(send_to_model, model, prompt): index
            for index, model in enumerate(model_list)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            results[index] = future.result()

    return [r for r in results if r is not None]
