<#
.SYNOPSIS
  start-app.ps1 ile baslatilan Ajanda servislerini durdurur (8000, 8100, 5173).
  Ollama'ya dokunmaz.
#>
foreach ($port in 8000, 8100, 5173) {
    $owners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $owners) {
        # uv/npm ust surecleriyle birlikte kapat
        & taskkill.exe /PID $procId /T /F | Out-Null
        Write-Host "Port $port durduruldu (PID $procId)"
    }
}

# Port tablosunda gorunmeyen ama bu projeden baslatilmis kalan surecler
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*Task-Management-Master-Project*" -and
                   $_.CommandLine -match "uvicorn|vite|npm" } |
    ForEach-Object {
        & taskkill.exe /PID $_.ProcessId /T /F | Out-Null
        Write-Host "Durduruldu: PID $($_.ProcessId)"
    }

