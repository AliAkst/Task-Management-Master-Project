# Faz 8 — Genel Plan

> Kaynak analiz: `analiz-faz8.md` (repo kökü). Ana plan: `g-rev-yapay-zek-dreamy-kahan.md` (§0 ortam/test komutları geçerli).
> Branch: `feature/ai-life-manager`. Her faz **ayrı yeni Sonnet oturumu**; oturum başında yalnız **bu dosya + ilgili faz dosyası** okunur.

## Fazlar ve sıra
| # | Faz | Dosya | Kapsam | Migration | Model |
|---|---|---|---|---|---|
| 1 | 8a | `8a-asistan-kart-araclari.md` | Asistan: checklist + etiket araçları, `create_card` genişletme, `get_card/get_board` genişletme, "bu kart" bağlamı | yok | Sonnet |
| 2 | 8b | `8b-not-editoru.md` | `MarkdownView`/`MarkdownEditor`, çift tıkla düzenle, GFM + kod vurgulama + kopyala, `surface`/`on-ink` belirteçleri | yok | Sonnet |
| 3 | 8c | `8c-ekler.md` | `card_attachments`, yerel depolama, uçlar, imzalı URL, "Ekler" bölümü, nota resim yapıştırma | `card_attachments` | Sonnet |
| 4 | 8d | `8d-teams-toplantilari.md` | Graph `calendarView`, `Calendars.Read`, haftalık pencere, `meeting_url`, "Teams'te katıl", `schedule_day` çakışma kontrolü | `events.meeting_url` | Sonnet |
| 5 | 8e | `8e-surukle-birak.md` | İyimser güncelleme + drop/taşıma animasyonları + liste overlay | yok | Sonnet |
| 6 | 8f | `8f-sesli-dikte.md` | Web Speech dikte (asistan, editör, checklist) | yok | Sonnet |
| 7 | 8g | `8g-tema-dark-mode.md` | Dark mode + uygulama zemini + board arka planı + `bg-white`/`text-white` dönüşümü | `user_settings.theme/background`, `boards.background` | Sonnet |
| — | Push | — | Her fazdan sonra commit + push | — | **Haiku** (yeni kısa oturum) |
| — | Denetim | — | Tüm fazlar bitince plan ↔ kod | — | **Opus** (yeni oturum) |

- **Migration zinciri tek hat:** 8c (`down_revision = e4b8c2f6a9d3`) → 8d (down = 8c'nin revizyonu) → 8g (down = 8d'nin). Her migration öncesi gerçek DB yedeği; upgrade → downgrade → upgrade **DB kopyasında** denenir.
- **Neden bu sıra:** 8b'nin editörünü 8c (ek yapıştırma) ve 8f (mikrofon) kullanır; 8g en sonda ki 8a–8f'de yazılan yeni bileşenler de dönüşsün. 8a, 8d, 8e bağımsızdır ama kullanıcı sıralı yürütmeyi seçti.
- **Opus'a dönüş noktaları (yalnız gerekirse, ayrı oturum):** 8d'de gerçek hesapla çözülemeyen OAuth/kapsam sorunu; 8g sonunda görsel sonuç beğenilmezse tasarım eleştirisi.

## Ortak kurallar (her faz oturumu)
- **Ortam:** Windows, Docker yok, SQLite. uv PATH'te değil: `C:\Users\alium\AppData\Roaming\Python\Python313\Scripts\uv.exe` (bash: `export PATH="/c/Users/alium/AppData/Roaming/Python/Python313/Scripts:$PATH"`). Node 24.
- **Testler:** `services/task-api`: `uv run pytest -q` · `services/assistant-service`: `uv run pytest -q` · `apps/web`: `npm run build` (test koşucusu yok). Önce yeni test dosyası, en sonda bir kez tüm paket.
- **Ruff:** yalnız değiştirilen/yeni dosyalara (`uv run ruff check <dosyalar>`; `ruff format` klasöre **çalıştırılmaz**). Yeni dosyalarda yalnız E501 kabul.
- **Tarayıcı doğrulaması:** kopya portlar (`task-api-alt` 8001 / `web-alt` 5175, oturum kökündeki `.claude/launch.json`). Gerçek uygulama 8000/5173'te gerçek DB ile çalışıyor — ona dokunma. Test hesabı: `apps/web/README.md`. Eski sahipsiz sunucular portları tutuyorsa `Get-CimInstance Win32_Process` ile `Task-Management` komut satırlı uv/uvicorn süreçlerini bul.
- **Bulut modele gerçek istek atılmaz** (kullanıcı kuralı). Gerçek-model kabul adımları local (qwen3.5:4b, gemma4:26b) ve kullanıcıyla.
- **`apps/web/src/lib/api-schema.d.ts`** elle güncellenir (`npm run gen:api` çalışan sunucu ister; çıktı aynı olmalı).
- **Yeni bileşen kuralı (8b'den itibaren):** zemin için `bg-white` değil `bg-surface`, koyu düğme üstü yazı için `text-white` değil `text-on-ink`.
- **Subagent açma**, tek oturum sırayla yapar. Oturum uzarsa yeni oturuma geç.
- **Faz sonu:** faz dosyasının sonundaki "İlerleme" bölümünü doldur (yapılanlar, sapmalar, doğrulanmayanlar) + ana plan §0 tablosundaki satırı güncelle. Commit/push **yapma** — ayrı Haiku oturumu.
- **Uygulama güncellemesi kuralı:** kod değişince kullanıcı "Ajanda - Durdur" → "Ajanda" (migration + `.env` eşitlemesi bununla çalışır).

## Haiku push oturumu (her faz sonrası, aynı şablon)
1. `git status` → yalnız fazın dosyaları mı? Beklenmeyen dosya varsa kullanıcıya sor.
2. Tüm testler bir kez (`task-api`, `assistant-service`, `npm run build`) — kırmızıysa commit yok, kullanıcıya bildir.
3. Commit mesajı: `feat(faz8x): <kısa özet>` + gövdede faz dosyasındaki yapılanların 3–5 maddesi + `Co-Authored-By` satırı.
4. `git push origin feature/ai-life-manager`; faz dosyası ve ana plan §0'daki commit hash'ini güncelle (aynı commit'e `--amend` değil, küçük ikinci commit `docs: faz8x commit hash`).

## Denetim (Opus, en son)
Her faz dosyasının adımları ve kabul ölçütleri ↔ kod; sapmalar tablosu; test sayıları; güvenlik (ekler: yetki, XSS başlıkları, yol geçişi), gizlilik (yeni araçlar local_only'ye uyuyor mu), dark mode'da kalan `bg-white`/`#fff`. Bulgular ana plana "Faz 8 denetimi" bölümü olarak.
