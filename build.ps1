$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PyInstaller = Join-Path $ProjectRoot ".venv\Scripts\pyinstaller.exe"
$Iscc = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"

if (-not (Test-Path $Python)) {
    throw "Не найдено виртуальное окружение: $Python"
}

$Version = & $Python -c "from version import __version__; print(__version__)"
Write-Host "Сборка ChatList $Version"

& $PyInstaller --noconfirm ChatList.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller завершился с ошибкой"
}

if (-not (Test-Path $Iscc)) {
    throw "Не найден Inno Setup: $Iscc"
}

& $Iscc "/DMyAppVersion=$Version" "ChatList.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup завершился с ошибкой"
}

Write-Host "Done: installer\ChatList-Setup-$Version.exe"
