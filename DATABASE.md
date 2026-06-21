# Схема базы данных ChatList

База данных: **SQLite** (файл, например `chatlist.db` в корне проекта или в каталоге данных приложения).

Доступ к БД — только через модуль `db.py`.

---

## Диаграмма связей

```
prompts (1) ──────< results >────── (N) models
                      │
                      └── prompt_id, model_id, response_text, created_at

settings — ключ/значение (без связей с другими таблицами)
```

---

## Таблица `prompts`

Хранение запросов пользователя для повторного использования.

| Поле         | Тип SQLite | Ограничения              | Описание                          |
|--------------|------------|--------------------------|-----------------------------------|
| `id`         | INTEGER    | PRIMARY KEY AUTOINCREMENT| Уникальный идентификатор          |
| `created_at` | TEXT       | NOT NULL                 | Дата и время создания (ISO 8601)  |
| `text`       | TEXT       | NOT NULL                 | Текст промта                      |
| `tags`       | TEXT       | DEFAULT ''               | Теги через запятую или JSON-массив|

**Индексы:**
- `idx_prompts_created_at` — сортировка по дате
- `idx_prompts_text` — полнотекстовый или LIKE-поиск (опционально)

**Пример записи:**

| id | created_at           | text                    | tags        |
|----|----------------------|-------------------------|-------------|
| 1  | 2026-06-21T10:00:00  | Объясни квантовую физику| обучение,наука |

---

## Таблица `models`

Справочник нейросетей. API-ключи **не хранятся** в БД — только имя переменной окружения.

| Поле        | Тип SQLite | Ограничения              | Описание                                      |
|-------------|------------|--------------------------|-----------------------------------------------|
| `id`        | INTEGER    | PRIMARY KEY AUTOINCREMENT| Уникальный идентификатор                      |
| `name`      | TEXT       | NOT NULL UNIQUE          | Отображаемое имя модели                       |
| `api_url`   | TEXT       | NOT NULL                 | URL endpoint API                              |
| `api_id`    | TEXT       | NOT NULL                 | Имя переменной в `.env` (например `OPENAI_API_KEY`) |
| `is_active` | INTEGER    | NOT NULL DEFAULT 1       | 1 — участвует в рассылке, 0 — отключена       |

**Индексы:**
- `idx_models_is_active` — быстрый отбор активных моделей

**Пример записи:**

| id | name           | api_url                                      | api_id           | is_active |
|----|----------------|----------------------------------------------|------------------|-----------|
| 1  | GPT-4o         | https://api.openai.com/v1/chat/completions   | OPENAI_API_KEY   | 1         |
| 2  | DeepSeek Chat  | https://api.deepseek.com/v1/chat/completions | DEEPSEEK_API_KEY | 1         |
| 3  | Groq Llama     | https://api.groq.com/openai/v1/chat/completions | GROQ_API_KEY  | 0         |

**Соответствие `.env`:**

```env
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=sk-...
GROQ_API_KEY=gsk_...
```

---

## Таблица `results`

Постоянное хранение ответов, которые пользователь отметил и сохранил. Временная таблица результатов в GUI в SQLite **не** записывается.

| Поле           | Тип SQLite | Ограничения              | Описание                              |
|----------------|------------|--------------------------|---------------------------------------|
| `id`           | INTEGER    | PRIMARY KEY AUTOINCREMENT| Уникальный идентификатор              |
| `prompt_id`    | INTEGER    | NOT NULL, FK → prompts(id) | Связь с промтом                   |
| `model_id`     | INTEGER    | NOT NULL, FK → models(id)  | Связь с моделью                   |
| `response_text`| TEXT       | NOT NULL                 | Текст ответа нейросети                |
| `created_at`   | TEXT       | NOT NULL                 | Дата и время сохранения (ISO 8601)    |

**Внешние ключи:**
- `prompt_id` → `prompts(id)` ON DELETE CASCADE
- `model_id` → `models(id)` ON DELETE RESTRICT (или SET NULL — по решению при реализации)

**Индексы:**
- `idx_results_prompt_id`
- `idx_results_model_id`
- `idx_results_created_at`

**Пример записи:**

| id | prompt_id | model_id | response_text      | created_at           |
|----|-----------|----------|--------------------|----------------------|
| 1  | 1         | 1        | Квантовая физика…  | 2026-06-21T10:05:00  |
| 2  | 1         | 2        | Другой вариант…    | 2026-06-21T10:05:00  |

При сохранении из GUI: для текущего промта создаётся или находится запись в `prompts`, затем для каждой отмеченной строки добавляется запись в `results`.

---

## Таблица `settings`

Ключ–значение для настроек приложения.

| Поле   | Тип SQLite | Ограничения              | Описание                    |
|--------|------------|--------------------------|-----------------------------|
| `key`  | TEXT       | PRIMARY KEY              | Имя настройки               |
| `value`| TEXT       | NOT NULL DEFAULT ''      | Значение (строка или JSON)  |

**Примеры настроек:**

| key              | value                    | Назначение                          |
|------------------|--------------------------|-------------------------------------|
| `db_path`        | `chatlist.db`            | Путь к файлу БД                     |
| `request_timeout`| `60`                     | Таймаут HTTP-запроса (секунды)    |
| `default_tags`   | `[]`                     | Теги по умолчанию для новых промтов |
| `window_geometry`| `{"w":1200,"h":800}`     | Размер/позиция окна (опционально) |

---

## SQL: создание схемы

```sql
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
```

---

## Временная таблица результатов (не в SQLite)

Используется только в памяти во время сессии. Структура для справки:

| Поле            | Тип    | Описание                          |
|-----------------|--------|-----------------------------------|
| `model_id`      | int    | ID из таблицы `models`            |
| `model_name`    | str    | Имя для отображения               |
| `response_text` | str    | Ответ или текст ошибки            |
| `selected`      | bool   | Отмечен ли чекбокс пользователем  |

Жизненный цикл: создаётся после отправки промта → отображается в GUI → при «Сохранить» выбранные строки переносятся в `results` → таблица очищается. При новом промте — полная очистка и пересоздание.

---

## Миграции

На первом этапе достаточно `CREATE TABLE IF NOT EXISTS` при старте приложения. При изменении схемы в будущем — отдельный номер версии в `settings` (`schema_version`) и пошаговые миграции в `db.py`.
