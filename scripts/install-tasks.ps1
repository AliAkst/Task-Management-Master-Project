<#
.SYNOPSIS
  Ajanda zamanlanmis gorevlerini kurar (su an: gunluk yedek).

.DESCRIPTION
  "Ajanda Yedek": her gun 13:00'te scripts\backup.py calisir; bilgisayar o saatte
  kapaliysa acilinca (StartWhenAvailable) calisir. Yonetici hakki gerekmez.

  Kurulum : scripts\install-tasks.ps1
  Kaldirma: scripts\install-tasks.ps1 -Uninstall
#>
param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

$taskName = "Ajanda Yedek"
$root = Get-RepoRoot

try {
    if ($Uninstall) {
        if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
            Write-Host "'$taskName' gorevi silindi."
        } else {
            Write-Host "'$taskName' gorevi zaten yok."
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
