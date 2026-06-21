"""AI-ассистент для улучшения промтов."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import models
import network

ADAPTATION_LABELS = {
    "code": "Код",
    "analysis": "Анализ",
    "creative": "Креатив",
}


@dataclass
class PromptImprovementResult:
    original: str
    improved: str
    alternatives: list[str] = field(default_factory=list)
    adaptations: dict[str, str] = field(default_factory=dict)
    partial_parse: bool = False


def _build_meta_prompt(user_prompt: str) -> str:
    return f"""Ты — ассистент по улучшению промтов для нейросетей.

Пользователь прислал исходный промт. Твоя задача:
1. Улучшить промт: сделать его яснее, конкретнее и структурированнее, сохранив смысл и язык исходного текста.
2. Предложить 2–3 альтернативные переформулировки того же запроса.
3. Дать адаптации промта под разные типы задач: код (code), анализ (analysis), креатив (creative).

Ответь ТОЛЬКО валидным JSON без markdown-обёртки, в таком формате:
{{
  "improved": "улучшенная версия",
  "alternatives": ["вариант 1", "вариант 2", "вариант 3"],
  "adaptations": {{
    "code": "адаптация для задач с кодом",
    "analysis": "адаптация для аналитических задач",
    "creative": "адаптация для креативных задач"
  }}
}}

Если какой-то блок адаптации не применим — оставь пустую строку для этого ключа.

Исходный промт:
---
{user_prompt}
---"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    block_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if block_match:
        data = json.loads(block_match.group(1).strip())
        if isinstance(data, dict):
            return data

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        data = json.loads(text[start : end + 1])
        if isinstance(data, dict):
            return data

    raise json.JSONDecodeError("Не удалось извлечь JSON из ответа модели.", text, 0)


def _parse_response(original: str, response_text: str) -> PromptImprovementResult:
    try:
        data = _extract_json(response_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return PromptImprovementResult(
            original=original,
            improved=response_text.strip(),
            partial_parse=True,
        )

    improved = str(data.get("improved", "")).strip()
    if not improved:
        improved = response_text.strip()

    alternatives_raw = data.get("alternatives", [])
    alternatives: list[str] = []
    if isinstance(alternatives_raw, list):
        alternatives = [str(item).strip() for item in alternatives_raw if str(item).strip()]

    adaptations: dict[str, str] = {}
    adaptations_raw = data.get("adaptations", {})
    if isinstance(adaptations_raw, dict):
        for key in ADAPTATION_LABELS:
            value = adaptations_raw.get(key, "")
            if value:
                adaptations[key] = str(value).strip()

    partial = not improved or (not alternatives and not adaptations)
    return PromptImprovementResult(
        original=original,
        improved=improved,
        alternatives=alternatives,
        adaptations=adaptations,
        partial_parse=partial,
    )


def improve_prompt(text: str, model: models.Model) -> PromptImprovementResult | str:
    """Улучшить промт через указанную модель. При ошибке возвращает строку."""
    user_prompt = text.strip()
    if not user_prompt:
        return "Промт пустой."

    meta_prompt = _build_meta_prompt(user_prompt)
    response = network.send_to_model(model, meta_prompt)
    if response.error:
        return response.response_text

    return _parse_response(user_prompt, response.response_text)
