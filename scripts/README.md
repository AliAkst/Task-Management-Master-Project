# scripts

Windows için başlatma ve yedekleme betikleri.

| Betik | Ne yapar |
|---|---|
| `start-app.ps1` / `stop-app.ps1` | Servisleri arka planda başlatır / durdurur |
| `install-shortcut.ps1` | Masaüstü kısayolu |
| `backup.py` | Veritabanlarının ve eklerin yedeğini alır |
| `restore.ps1` | Bir yedeği geri yükler |
| `install-tasks.ps1` | Günlük yedek için Görev Zamanlayıcı görevi kurar |

## Yedek

```powershell
uv run python scripts\backup.py            # elle yedek
uv run python scripts\backup.py --dest D:\yedek
```

Varsayılan kök `%LOCALAPPDATA%\Ajanda\yedek`; her yedek `YYYY-MM-DD_HHMM` klasörüdür:
`task_management.db`, `assistant.db` (çevrimiçi kopya), `attachments.zip`, anahtar dosyaları
(`task-api.secret_key`, `assistant.secret_key`, `task-api.jwt_secret`, varsa `.env`'ler) ve
`manifest.json` (dosya boyutu + sha256, Alembic revizyonları, `ok`).
Her veritabanı kopyasında `PRAGMA integrity_check` çalışır; başarısızsa klasör `_BOZUK` ekini alır
ve o tur eski yedekler silinmez (çıkış kodu 2).

**Döndürme:** son 7 günün her günü, son 4 haftanın her haftası ve son 3 ayın her ayı için en yeni
yedek tutulur; gerisi silinir. Yalnız tarih desenli klasörler silinir (`pre-restore_*` asla).
`_BOZUK` klasörler 14 günden sonra silinir. Log: `backup.log` (1 MB'ta döner).

**OneDrive:** `OneDrive` ortam değişkeni varsa haftada bir, yalnız veritabanları, ekler ve manifest
`<OneDrive>\Ajanda-yedek\` altına kopyalanır (son 4 tutulur). **Anahtar dosyaları ve `.env` buraya
gitmez**; `.secret_key` / `.jwt_secret` içeriğini parola yöneticine elle koy (bunlar olmadan kayıtlı
entegrasyon bağlantıları çözülemez, oturumlar sıfırlanır).

Açılışta `start-app.ps1` günün yedeği yoksa bir kez alır (`--if-missing-today`).

## Zamanlanmış görev

```powershell
scripts\install-tasks.ps1              # "Ajanda Yedek": her gün 13:00 (kapalıysa açılınca)
scripts\install-tasks.ps1 -Uninstall   # kaldır
```

## Geri yükleme

1. `scripts\restore.ps1 -From "$env:LOCALAPPDATA\Ajanda\yedek\2026-11-14_1300"`
2. Betik servisleri durdurur, mevcut veriyi yedek kökünde `pre-restore_<zaman>\` altına **taşır**,
   yedeği kopyalar ve sha256'ları manifest ile karşılaştırır (uyuşmazsa eskiyi geri koyar).
3. Ajanda'yı kısayoldan başlat. Yedek `ok: false` ise yalnız `-Force` ile yüklenir.

## Testler

```powershell
uv run --with pytest pytest -q scripts/tests
```
