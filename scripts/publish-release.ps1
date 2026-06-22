# Публикация GitHub Release для ChatList.
# Использование:
#   .\scripts\publish-release.ps1              # интерактивно
#   .\scripts\publish-release.ps1 -SkipBuild   # если installer уже собран
#   .\scripts\publish-release.ps1 -DryRun      # только проверки, без tag/release

param(
    [switch]$SkipBuild,
    [switch]$DryRun,
    [string]$Branch = "estai-tech"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Команда '$Name' не найдена. Установите её и повторите."
    }
}

Require-Command "git"
Require-Command "gh"

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Не найдено виртуальное окружение: $Python"
}

$Version = & $Python -c "from version import __version__; print(__version__)"
$Tag = "v$Version"
$Installer = Join-Path $ProjectRoot "installer\ChatList-Setup-$Version.exe"
$NotesFile = Join-Path $ProjectRoot "release-notes-$Version.md"

Write-Host "=== ChatList Release $Tag ===" -ForegroundColor Cyan

if (-not $SkipBuild) {
    Write-Host "Сборка установщика..."
    & (Join-Path $ProjectRoot "build.ps1")
}

if (-not (Test-Path $Installer)) {
    throw "Не найден установщик: $Installer`nЗапустите .\build.ps1 или уберите -SkipBuild."
}

$InstallerSize = [math]::Round((Get-Item $Installer).Length / 1MB, 2)
Write-Host "Установщик: $Installer ($InstallerSize MB)"

if (-not (Test-Path $NotesFile)) {
    Write-Host "Создание release-notes из шаблона..."
    $Template = Get-Content (Join-Path $ProjectRoot ".github\release-notes-template.md") -Raw
    $Template `
        -replace '\{\{VERSION\}\}', $Version `
        -replace '\{\{DATE\}\}', (Get-Date -Format "yyyy-MM-dd") `
        | Set-Content $NotesFile -Encoding utf8
    Write-Host "Отредактируйте $NotesFile и запустите скрипт снова с -SkipBuild" -ForegroundColor Yellow
    exit 0
}

$Dirty = git status --porcelain
if ($Dirty) {
    Write-Host "Предупреждение: есть незакоммиченные изменения:" -ForegroundColor Yellow
    git status --short
    $Confirm = Read-Host "Продолжить публикацию? (y/N)"
    if ($Confirm -ne "y") { exit 1 }
}

if (git tag -l $Tag) {
    throw "Тег $Tag уже существует. Обновите version.py или удалите тег."
}

if ($DryRun) {
    Write-Host "[DryRun] Тег: $Tag" -ForegroundColor Green
    Write-Host "[DryRun] Файл: $Installer"
    Write-Host "[DryRun] Notes: $NotesFile"
    exit 0
}

Write-Host "Создание тега $Tag..."
git tag -a $Tag -m "ChatList $Version"
git push origin $Tag

Write-Host "Публикация GitHub Release..."
gh release create $Tag `
    --title "ChatList $Version" `
    --notes-file $NotesFile `
    $Installer

Write-Host ""
Write-Host "Готово!" -ForegroundColor Green
Write-Host "Release: https://github.com/evbukanov-tech/ChatList/releases/tag/$Tag"
Write-Host "Pages:   https://evbukanov-tech.github.io/ChatList/"
