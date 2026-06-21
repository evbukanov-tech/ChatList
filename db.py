"""Доступ к SQLite. Единственный модуль, работающий с базой данных напрямую."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = "chatlist.db"

_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS prompts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,
    text        TEXT    NOT NULL,
    tags        TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS models (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    api_url     TEXT    NOT NULL,
    api_id      TEXT    NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id     INTEGER NOT NULL,
    model_id      INTEGER NOT NULL,
    response_text TEXT    NOT NULL,
    created_at    TEXT    NOT NULL,
    FOREIGN KEY (prompt_id) REFERENCES prompts(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id)  REFERENCES models(id)  ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_prompts_created_at ON prompts(created_at);
CREATE INDEX IF NOT EXISTS idx_models_is_active    ON models(is_active);
CREATE INDEX IF NOT EXISTS idx_results_prompt_id   ON results(prompt_id);
CREATE INDEX IF NOT EXISTS idx_results_model_id    ON results(model_id);
CREATE INDEX IF NOT EXISTS idx_results_created_at  ON results(created_at);
"""


@dataclass
class Prompt:
    id: int
    created_at: str
    text: str
    tags: str


@dataclass
class ModelRow:
    id: int
    name: str
    api_url: str
    api_id: str
    is_active: bool


@dataclass
class Result:
    id: int
    prompt_id: int
    model_id: int
    response_text: str
    created_at: str
    prompt_text: str | None = None
    model_name: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()


def _row_to_prompt(row: sqlite3.Row) -> Prompt:
    return Prompt(
        id=row["id"],
        created_at=row["created_at"],
        text=row["text"],
        tags=row["tags"],
    )


def _row_to_model(row: sqlite3.Row) -> ModelRow:
    return ModelRow(
        id=row["id"],
        name=row["name"],
        api_url=row["api_url"],
        api_id=row["api_id"],
        is_active=bool(row["is_active"]),
    )


def _row_to_result(row: sqlite3.Row) -> Result:
    keys = row.keys()
    return Result(
        id=row["id"],
        prompt_id=row["prompt_id"],
        model_id=row["model_id"],
        response_text=row["response_text"],
        created_at=row["created_at"],
        prompt_text=row["prompt_text"] if "prompt_text" in keys else None,
        model_name=row["model_name"] if "model_name" in keys else None,
    )


# --- prompts ---


def add_prompt(
    text: str,
    tags: str = "",
    created_at: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    ts = created_at or _utc_now()
    with _connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO prompts (created_at, text, tags) VALUES (?, ?, ?)",
            (ts, text, tags),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_prompt(prompt_id: int, db_path: str | Path = DEFAULT_DB_PATH) -> Prompt | None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
    return _row_to_prompt(row) if row else None


def list_prompts(
    search: str | None = None,
    order_by: str = "created_at",
    order_dir: str = "DESC",
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[Prompt]:
    allowed_order = {"created_at", "text", "tags", "id"}
    if order_by not in allowed_order:
        order_by = "created_at"
    order_dir = "ASC" if order_dir.upper() == "ASC" else "DESC"

    query = "SELECT * FROM prompts"
    params: list[Any] = []
    if search:
        query += " WHERE text LIKE ? OR tags LIKE ?"
        pattern = f"%{search}%"
        params.extend([pattern, pattern])
    query += f" ORDER BY {order_by} {order_dir}"

    with _connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_prompt(row) for row in rows]


def update_prompt(
    prompt_id: int,
    text: str,
    tags: str = "",
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE prompts SET text = ?, tags = ? WHERE id = ?",
            (text, tags, prompt_id),
        )
        conn.commit()


def delete_prompt(prompt_id: int, db_path: str | Path = DEFAULT_DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
        conn.commit()


# --- models ---


def add_model(
    name: str,
    api_url: str,
    api_id: str,
    is_active: bool = True,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO models (name, api_url, api_id, is_active)
            VALUES (?, ?, ?, ?)
            """,
            (name, api_url, api_id, int(is_active)),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_model(model_id: int, db_path: str | Path = DEFAULT_DB_PATH) -> ModelRow | None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
    return _row_to_model(row) if row else None


def get_model_by_name(name: str, db_path: str | Path = DEFAULT_DB_PATH) -> ModelRow | None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM models WHERE name = ?", (name,)).fetchone()
    return _row_to_model(row) if row else None


def list_models(
    active_only: bool = False,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[ModelRow]:
    query = "SELECT * FROM models"
    params: list[Any] = []
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY name ASC"

    with _connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_model(row) for row in rows]


def list_active_models(db_path: str | Path = DEFAULT_DB_PATH) -> list[ModelRow]:
    return list_models(active_only=True, db_path=db_path)


def update_model(
    model_id: int,
    name: str,
    api_url: str,
    api_id: str,
    is_active: bool,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE models
            SET name = ?, api_url = ?, api_id = ?, is_active = ?
            WHERE id = ?
            """,
            (name, api_url, api_id, int(is_active), model_id),
        )
        conn.commit()


def set_model_active(
    model_id: int,
    is_active: bool,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE models SET is_active = ? WHERE id = ?",
            (int(is_active), model_id),
        )
        conn.commit()


def delete_model(model_id: int, db_path: str | Path = DEFAULT_DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM models WHERE id = ?", (model_id,))
        conn.commit()


# --- results ---


def add_result(
    prompt_id: int,
    model_id: int,
    response_text: str,
    created_at: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    ts = created_at or _utc_now()
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO results (prompt_id, model_id, response_text, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (prompt_id, model_id, response_text, ts),
        )
        conn.commit()
        return int(cursor.lastrowid)


def save_results(
    prompt_id: int,
    items: list[tuple[int, str]],
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[int]:
    """Сохранить несколько результатов: список пар (model_id, response_text)."""
    ts = _utc_now()
    ids: list[int] = []
    with _connect(db_path) as conn:
        for model_id, response_text in items:
            cursor = conn.execute(
                """
                INSERT INTO results (prompt_id, model_id, response_text, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (prompt_id, model_id, response_text, ts),
            )
            ids.append(int(cursor.lastrowid))
        conn.commit()
    return ids


def list_results(
    search: str | None = None,
    prompt_id: int | None = None,
    model_id: int | None = None,
    order_by: str = "created_at",
    order_dir: str = "DESC",
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[Result]:
    allowed_order = {"created_at", "id", "response_text"}
    if order_by not in allowed_order:
        order_by = "created_at"
    order_dir = "ASC" if order_dir.upper() == "ASC" else "DESC"

    query = """
        SELECT r.*, p.text AS prompt_text, m.name AS model_name
        FROM results r
        JOIN prompts p ON p.id = r.prompt_id
        JOIN models m ON m.id = r.model_id
        WHERE 1=1
    """
    params: list[Any] = []

    if prompt_id is not None:
        query += " AND r.prompt_id = ?"
        params.append(prompt_id)
    if model_id is not None:
        query += " AND r.model_id = ?"
        params.append(model_id)
    if search:
        query += " AND (r.response_text LIKE ? OR p.text LIKE ? OR m.name LIKE ?)"
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])

    query += f" ORDER BY r.{order_by} {order_dir}"

    with _connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_result(row) for row in rows]


# --- settings ---


def get_setting(key: str, default: str = "", db_path: str | Path = DEFAULT_DB_PATH) -> str:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str, db_path: str | Path = DEFAULT_DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        conn.commit()


def delete_setting(key: str, db_path: str | Path = DEFAULT_DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        conn.commit()


def list_settings(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, str]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
    return {row["key"]: row["value"] for row in rows}
