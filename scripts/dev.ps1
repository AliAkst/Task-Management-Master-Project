<#
.SYNOPSIS
  Gelistirme ortamini tek komutla baslatir.

.DESCRIPTION
  1. Docker varsa: Postgres + Redis + RabbitMQ container'larini kaldirir.
     Docker yoksa: task-api SQLite ile calisir; Redis/RabbitMQ yoksa cache ve
     event'ler devre disi kalir (uygulama yine calisir - graceful degradation).
  2. task-api migration'larini uygular ve 8000 portunda baslatir.
  3. assistant-service'i (AI) 8100 portunda baslatir (Ollama gerekir).
  4. RabbitMQ ayaktaysa notification-service consumer'ini baslatir.
  5. Frontend'i (Vite) 5173 portunda baslatir.

.EXAMPLE
  ./scripts/dev.ps1
  ./scripts/dev.ps1 -NoDocker
#>
param(
    [switch]$NoDocker
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$taskApi = Join-Path $root "services/task-api"
$notification = Join-Path $root "services/notification-service"
$web = Join-Path $root "apps/web"
$assistant = Join-Path $root "services/assistant-service"

function Test-Command($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }

if (-not (Test-Command "uv")) {
    Write-Error "uv bulunamadi. Kurulum: py -m pip install --user uv (ve Scripts klasorunu PATH'e ekle)"
}

$useDocker = (-not $NoDocker) -and (Test-Command "docker")
if ($useDocker) {
    Write-Host "Docker servisleri baslatiliyor..." -ForegroundColor Cyan
    docker compose -f (Join-Path $root "infrastructure/docker/docker-compose.yml") up -d
} else {
    Write-Host "Docker kullanilmiyor: SQLite + (varsa) yerel Redis/RabbitMQ." -ForegroundColor Yellow
    # .env'deki Postgres URL'ini ezmek icin SQLite'a zorla
    $env:DATABASE_URL = "sqlite+aiosqlite:///./task_management.db"
}

Write-Host "Migration'lar uygulaniyor..." -ForegroundColor Cyan
Push-Location $taskApi
try { uv run alembic upgrade head } finally { Pop-Location }

$jobs = @()

Write-Host "task-api -> http://localhost:8000/docs" -ForegroundColor Green
$jobs += Start-Process -PassThru -NoNewWindow -WorkingDirectory $taskApi `
    -FilePath "uv" -ArgumentList "run", "uvicorn", "app.main:app", "--reload", "--port", "8000"

Write-Host "assistant-service -> http://localhost:8100/docs" -ForegroundColor Green
Push-Location $assistant
try { uv run alembic upgrade head } finally { Pop-Location }
$jobs += Start-Process -PassThru -NoNewWindow -WorkingDirectory $assistant `
    -FilePath "uv" -ArgumentList "run", "uvicorn", "app.main:app", "--reload", "--port", "8100"
if (-not (Test-Command "ollama")) {
    Write-Host "Ollama bulunamadi: local modeller calismaz (https://ollama.com)." -ForegroundColor Yellow
}

$rabbitUp = $false
try { $rabbitUp = (Test-NetConnection localhost -Port 5672 -WarningAction SilentlyContinue).TcpTestSucceeded } catch {}
if ($rabbitUp) {
    Write-Host "notification-service consumer baslatiliyor" -ForegroundColor Green
    $jobs += Start-Process -PassThru -NoNewWindow -WorkingDirectory $notification `
        -FilePath "uv" -ArgumentList "run", "python", "-m", "app.consumer"
} else {
    Write-Host "RabbitMQ yok: notification-service atlandi." -ForegroundColor Yellow
}

if (-not (Test-Path (Join-Path $web "node_modules"))) {
    Push-Location $web
    try { npm install } finally { Pop-Location }
}
Write-Host "web -> http://localhost:5173" -ForegroundColor Green
$jobs += Start-Process -PassThru -NoNewWindow -WorkingDirectory $web `
    -FilePath "npm.cmd" -ArgumentList "run", "dev"

Write-Host "`nDurdurmak icin Ctrl+C." -ForegroundColor Cyan
try {
    Wait-Process -Id ($jobs | ForEach-Object { $_.Id })
} finally {
    $jobs | ForEach-Object { if (-not $_.HasExited) { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } }
}
