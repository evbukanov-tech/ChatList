# Публикация ChatList: GitHub Release и GitHub Pages

Пошаговая инструкция для выпуска Windows-установщика и лендинга проекта.

**Репозиторий:** https://github.com/evbukanov-tech/ChatList  
**Страница проекта (Pages):** https://evbukanov-tech.github.io/ChatList/

---

## Часть 1. Первоначальная настройка (один раз)

### 1.1. Инструменты на вашем ПК

```powershell
# GitHub CLI (если ещё не установлен)
winget install GitHub.cli

# Авторизация
gh auth login
```

Проверка:

```powershell
gh auth status
gh repo view evbukanov-tech/ChatList
```

### 1.2. Включить GitHub Pages

1. Откройте **Settings → Pages** в репозитории.
2. **Build and deployment → Source:** Deploy from a branch.
3. **Branch:** `estai-tech` (или ваша основная ветка) → папка **`/docs`** → Save.
4. Через 1–2 минуты сайт будет доступен по адресу  
   `https://evbukanov-tech.github.io/ChatList/`.

Лендинг лежит в [`docs/index.html`](index.html), стили — в [`docs/style.css`](style.css).

### 1.3. Файлы, которые должны быть в git

| Файл | Назначение |
|------|------------|
| `version.py` | Единый номер версии |
| `ChatList.spec` | Спецификация PyInstaller |
| `ChatList.iss` | Скрипт Inno Setup |
| `build.ps1` | Локальная сборка exe + installer |
| `docs/` | Лендинг для GitHub Pages |
| `.github/release-notes-template.md` | Шаблон описания релиза |
| `scripts/publish-release.ps1` | Скрипт публикации |

Установщики (`installer/*.exe`) и артефакты сборки (`build/`, `dist/`) **не коммитятся** — только загружаются в Release.

---

## Часть 2. Выпуск новой версии

Семантическое версионирование: `MAJOR.MINOR.PATCH` (например `1.0.1`).

### Шаг 1. Обновить версию

Отредактируйте [`version.py`](../version.py):

```python
__version__ = "1.0.1"
```

### Шаг 2. Собрать установщик

```powershell
cd C:\Work\ChatList
.\build.ps1
```

Результат: `installer\ChatList-Setup-1.0.1.exe`

Проверьте установку локально перед публикацией.

### Шаг 3. Подготовить описание релиза

```powershell
$Version = "1.0.1"
$NotesFile = "release-notes-$Version.md"

(Get-Content ".github\release-notes-template.md" -Raw) `
  -replace '\{\{VERSION\}\}', $Version `
  -replace '\{\{DATE\}\}', (Get-Date -Format "yyyy-MM-dd") `
  | Set-Content $NotesFile -Encoding utf8
```

Отредактируйте `$NotesFile`: добавьте список изменений в раздел «Что нового».

### Шаг 4. Закоммитить изменения версии

```powershell
git add version.py docs/
git commit -m "Выпуск версии $Version"
git push origin estai-tech
```

### Шаг 5. Создать тег и GitHub Release

**Вариант А — автоматический скрипт (рекомендуется):**

```powershell
.\scripts\publish-release.ps1
```

Скрипт проверит сборку, создаст тег `v{версия}`, загрузит exe и опубликует Release.

**Вариант Б — вручную через gh:**

```powershell
$Version = "1.0.1"
$Tag = "v$Version"
$Installer = "installer\ChatList-Setup-$Version.exe"

git tag -a $Tag -m "ChatList $Version"
git push origin $Tag

gh release create $Tag `
  --title "ChatList $Version" `
  --notes-file "release-notes-$Version.md" `
  $Installer
```

### Шаг 6. Проверить результат

1. **Releases:** https://github.com/evbukanov-tech/ChatList/releases  
   — установщик скачивается, описание корректное.
2. **Pages:** https://evbukanov-tech.github.io/ChatList/  
   — кнопка «Скачать» ведёт на актуальный exe (через GitHub API).
3. В приложении: **Справка → О программе** — номер версии совпадает.

---

## Часть 3. Именование и соглашения

| Элемент | Формат | Пример |
|---------|--------|--------|
| Версия в коде | `X.Y.Z` | `1.0.1` |
| Git-тег | `vX.Y.Z` | `v1.0.1` |
| Установщик | `ChatList-Setup-X.Y.Z.exe` | `ChatList-Setup-1.0.1.exe` |
| Заголовок Release | `ChatList X.Y.Z` | `ChatList 1.0.1` |

**Не меняйте** шаблон имени установщика — лендинг ищет файл `ChatList-Setup-*.exe` в assets последнего релиза.

---

## Часть 4. GitHub Actions (опционально)

Workflow [`.github/workflows/release.yml`](../.github/workflows/release.yml) собирает установщик на `windows-latest` при push тега `v*`.

Если используете CI:

1. Закоммитьте `ChatList.spec` в репозиторий.
2. Push тега — workflow создаст Release и прикрепит exe автоматически.

Локальная сборка через `build.ps1` остаётся основным способом для отладки.

---

## Часть 5. Чек-лист перед каждым релизом

- [ ] Версия обновлена в `version.py`
- [ ] `.\build.ps1` завершился без ошибок
- [ ] Установщик протестирован на чистой машине / VM
- [ ] Release notes заполнены
- [ ] Тег `vX.Y.Z` создан и запушен
- [ ] Exe прикреплён к Release
- [ ] GitHub Pages показывает актуальную версию
- [ ] README при необходимости обновлён

---

## Часть 6. Откат и hotfix

```powershell
# Удалить ошибочный тег локально и на GitHub
git tag -d v1.0.1
git push origin :refs/tags/v1.0.1
gh release delete v1.0.1 --yes
```

Затем исправьте код, увеличьте patch-версию и повторите процесс выпуска.

---

## Полезные ссылки

- [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github)
- [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages)
- [GitHub CLI release create](https://cli.github.com/manual/gh_release_create)
