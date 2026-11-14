<#
.SYNOPSIS
  Bir yedek klasorunu geri yukler (scripts\backup.py'nin urettigi klasor).

.DESCRIPTION
  Adimlar: manifest oku -> servisleri durdur -> mevcut veriyi yedek kokunde
  pre-restore_<zaman>\ altina TASI -> yedegi kopyala -> sha256 dogrula
  (uyusmazsa pre-restore'dan geri alir) -> ekleri ac.
  Ajanda'yi otomatik baslatmaz.

  Ornek: scripts\restore.ps1 -From "$env:LOCALAPPDATA\Ajanda\yedek\2026-11-14_1300"
#>
param(
    [Parameter(Mandatory = $true)][string]$From,
    [switch]$Force
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")
$root = Get-RepoRoot

$From = (Resolve-Path -LiteralPath $From).Path
$manifestPath = Join-Path $From "manifest.json"
if (-not (Test-Path $manifestPath)) { throw "manifest.json yok: $From" }
$manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
if (-not $manifest.ok -and -not $Force) {
    throw "Bu yedek bozuk isaretli (ok=false). Yine de yuklemek icin -Force kullan."
}

# yedek dosyasi -> repo icindeki hedef
$map = [ordered]@{
    "task_management.db"   = "services\task-api\task_management.db"
    "assistant.db"         = "services\assistant-service\assistant.db"
    "task-api.secret_key"  = "services\task-api\.secret_key"
    "assistant.secret_key" = "services\assistant-service\.secret_key"
    "task-api.jwt_secret"  = "services\task-api\.jwt_secret"
    "task-api.env"         = "services\task-api\.env"
    "assistant.env"        = "services\assistant-service\.env"
}

# dosya butunlugu: kopyalamadan once yedegin kendisini dogrula
foreach ($f in $manifest.files) {
    $p = Join-Path $From $f.name
    if (-not (Test-Path $p)) { throw "Yedekte dosya yok: $($f.name)" }
    if ((Get-FileHash -Algorithm SHA256 $p).Hash.ToLower() -ne $f.sha256) {
        throw "Yedek dosyasi bozulmus (sha256): $($f.name)"
    }
}

Write-Host "Servisler durduruluyor..."
& (Join-Path $PSScriptRoot "stop-app.ps1")

$backupRoot = Split-Path -Parent $From
$pre = Join-Path $backupRoot ("pre-restore_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Force $pre | Out-Null
$moved = @()
$restored = @()

function Undo-Restore {
    foreach ($t in $restored) { Remove-Item -LiteralPath $t -Force -ErrorAction SilentlyContinue }
    foreach ($m in $moved) { Move-Item -LiteralPath $m.Saved -Destination $m.Target -Force }
}

try {
    # 1) mevcut dosyalari pre-restore'a TASI
    foreach ($name in $map.Keys) {
        $target = Join-Path $root $map[$name]
        if (Test-Path -LiteralPath $target) {
            $saved = Join-Path $pre $name
            Move-Item -LiteralPath $target -Destination $saved -Force
            $moved += [pscustomobject]@{ Saved = $saved; Target = $target }
        }
        # SQLite yan dosyalari (cokme artigi): yeni DB'ye eski gunluk uygulanmasin.
        # pre-restore'a tasinir, geri kopyalanmaz (Undo'da eski yerine doner).
        if ($name -like "*.db") {
            foreach ($suffix in "-journal", "-wal", "-shm") {
                $side = $target + $suffix
                if (Test-Path -LiteralPath $side) {
                    $sideSaved = Join-Path $pre ($name + $suffix)
                    Move-Item -LiteralPath $side -Destination $sideSaved -Force
                    $moved += [pscustomobject]@{ Saved = $sideSaved; Target = $side }
                }
            }
        }
    }
    $attDir = Join-Path $root "services\task-api\data\attachments"
    $attSaved = $null
    if (Test-Path -LiteralPath $attDir) {
        $attSaved = Join-Path $pre "attachments"
        Move-Item -LiteralPath $attDir -Destination $attSaved -Force
    }

    # 2) yedekten kopyala (adlari geri esle) + sha256 karsilastir
    foreach ($f in $manifest.files) {
        if (-not $map.Contains($f.name)) { continue }
        $target = Join-Path $root $map[$f.name]
        New-Item -ItemType Directory -Force (Split-Path -Parent $target) | Out-Null
        Copy-Item -LiteralPath (Join-Path $From $f.name) -Destination $target -Force
        $restored += $target
        if ((Get-FileHash -Algorithm SHA256 $target).Hash.ToLower() -ne $f.sha256) {
            throw "Kopya dogrulanamadi (sha256): $($f.name)"
        }
    }

    # 3) ekler
    $zip = Join-Path $From "attachments.zip"
    if (Test-Path $zip) {
        New-Item -ItemType Directory -Force $attDir | Out-Null
        Expand-Archive -LiteralPath $zip -DestinationPath $attDir -Force
    }
} catch {
    Write-Warning "Geri yukleme basarisiz: $($_.Exception.Message) - eski veri geri aliniyor."
    Undo-Restore
    if ($attSaved -and (Test-Path -LiteralPath $attSaved)) {
        Remove-Item -LiteralPath $attDir -Recurse -Force -ErrorAction SilentlyContinue
        Move-Item -LiteralPath $attSaved -Destination $attDir -Force
    }
    throw
}

Write-Host "Geri yukleme tamam. Onceki veri: $pre"
Write-Host "Ajanda'yi baslat: Ajanda kisayolu."
