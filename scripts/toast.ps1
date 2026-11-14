<#
.SYNOPSIS
  Windows bildirimi (toast) gosterir. assistant-service zamanlayicisi cagirir.

.DESCRIPTION
  Kullanim: powershell -NoProfile -ExecutionPolicy Bypass -File toast.ps1 -Title "Baslik" -Body "Govde"
  Yeni bagimlilik yok: Windows.UI.Notifications (WinRT) + ToastText02 sablonu.
  Metinler XML kacislidir. Bildirim merkezi/"Rahatsiz etme" ayarina saygi duyar.
#>
param(
    [Parameter(Mandatory = $true)][string]$Title,
    [string]$Body = ""
)
$ErrorActionPreference = "Stop"

# Windows PowerShell'in kayitli uygulama kimligi (bildirim bu adla gorunur)
$appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'

[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
[void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]

function ConvertTo-XmlText([string]$text) {
    return [System.Security.SecurityElement]::Escape($text)
}

$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml(@"
<toast>
  <visual>
    <binding template="ToastText02">
      <text id="1">$(ConvertTo-XmlText $Title)</text>
      <text id="2">$(ConvertTo-XmlText $Body)</text>
    </binding>
  </visual>
</toast>
"@)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
