<#
.SYNOPSIS
  Ajanda zamanlanmis gorevlerini kurar (su an: gunluk yedek).

.DESCRIPTION
  "Ajanda Yedek": her gun 13:00'te scripts\backup.py calisir; bilgisayar o saatte
  kapaliysa acilinca (StartWhenAvailable) calisir. Yonetici hakki gerekmez.

  -Logon: ayrica Baslangic klasorune "Ajanda Arka Plan.lnk" koyar; Windows
  oturumu acilinca task-api + asistan (+ Ollama) tarayicisiz baslar, boylece
  bildirim zamanlayicisi (Telegram / Windows bildirimi) calisir. Yonetici hakki
  gerekmez.

  Kurulum : scripts\install-tasks.ps1            (yedek gorevi)
            scripts\install-tasks.ps1 -Logon     (yedek gorevi + oturum acilisi)
  Kaldirma: scripts\install-tasks.ps1 -Uninstall (ikisini de siler)
#>
param([switch]$Uninstall, [switch]$Logon)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

$taskName = "Ajanda Yedek"
$root = Get-RepoRoot
$logonLink = Join-Path ([Environment]::GetFolderPath("Startup")) "Ajanda Arka Plan.lnk"

function Install-LogonShortcut {
    $startApp = Join-Path $PSScriptRoot "start-app.ps1"
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($logonLink)
    $lnk.TargetPath = (Get-Command powershell.exe).Source
    $lnk.Arguments = "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startApp`" -Background"
    $lnk.WorkingDirectory = $root
    $lnk.WindowStyle = 7  # kucultulmus
    $lnk.Description = "Ajanda arka plan servisleri (bildirim zamanlayicisi)"
    $lnk.Save()
    Write-Host "Oturum acilisi kisayolu kuruldu: $logonLink"
}

try {
    if ($Uninstall) {
        if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
            Write-Host "'$taskName' gorevi silindi."
        } else {
            Write-Host "'$taskName' gorevi zaten yok."
        }
        if (Test-Path $logonLink) {
            Remove-Item $logonLink -Force
            Write-Host "Oturum acilisi kisayolu silindi."
        }
        return
    }

    $uv = Find-Uv
    if (-not $uv) { throw "uv bulunamadi. Once Ajanda'yi bir kez baslat (uv'yi kurar)." }
    $backup = Join-Path $PSScriptRoot "backup.py"
    $action = New-ScheduledTaskAction -Execute $uv `
        -Argument "run --no-project python `"$backup`"" -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -Daily -At "13:00"
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries
    $principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) `
        -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Force | Out-Null
    Write-Host "'$taskName' gorevi kuruldu (her gun 13:00)."
    if ($Logon) { Install-LogonShortcut }
    Write-Host "Deneme: Start-ScheduledTask -TaskName '$taskName'  (sonuc: %LOCALAPPDATA%\Ajanda\yedek\backup.log)"
} catch [System.UnauthorizedAccessException] {
    Write-Error "Gorev kurulamadi: erisim reddedildi. Elle komut: schtasks /Create /TN `"$taskName`" /SC DAILY /ST 13:00 /TR `"\`"$uv\`" run --no-project python \`"$backup\`"`""
} catch {
    if ($_.Exception.Message -match "denied|reddedildi") {
        Write-Error "Gorev kurulamadi: erisim reddedildi. Elle komut: schtasks /Create /TN `"$taskName`" /SC DAILY /ST 13:00 /TR `"\`"$uv\`" run --no-project python \`"$backup\`"`""
    } else {
        Write-Error "Gorev kurulamadi: $($_.Exception.Message)"
    }
}
