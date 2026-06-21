"""Экспорт выбранных результатов в Markdown и JSON."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from session import TempResultRow


def export_markdown(prompt_text: str, rows: list[TempResultRow]) -> str:
    lines = [
        f"# Промт\n\n{prompt_text}\n",
        f"_Экспорт: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_\n",
    ]
    for row in rows:
        lines.append(f"## {row.model_name}\n\n{row.response_text}\n")
    return "\n".join(lines)


def export_json(prompt_text: str, rows: list[TempResultRow]) -> str:
    payload = {
        "prompt": prompt_text,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "results": [
            {
                "model_id": row.model_id,
                "model_name": row.model_name,
                "response_text": row.response_text,
                "selected": row.selected,
            }
            for row in rows
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def export_selected_markdown(prompt_text: str, rows: list[TempResultRow]) -> str:
    selected = [row for row in rows if row.selected]
    return export_markdown(prompt_text, selected)


def export_selected_json(prompt_text: str, rows: list[TempResultRow]) -> str:
    selected = [row for row in rows if row.selected]
    return export_json(prompt_text, selected)
