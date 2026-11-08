# Faz 8d — Teams/Outlook toplantıları → takvim

**Önerilen model: Sonnet.** Google takvim deseni hazır, kararlar burada. Gerçek hesapla bağlanırken çözülemeyen bir OAuth/kapsam/Graph hatası çıkarsa **yalnız o iş için** ayrı Opus hata ayıklama oturumu.

**Ön koşul (kullanıcı, kod için şart değil):** Azure → App registrations → uygulama → API permissions → Microsoft Graph → Delegated → **Calendars.Read** ekle. Kişisel Microsoft hesabı (consumers).

## Kararlar
- Kaynak: `GET https://graph.microsoft.com/v1.0/me/calendarView` (tekrarları örneklere açar), başlık `Prefer: outlook.timezone="UTC"`, `$top=100`, `$select=id,subject,start,end,isAllDay,isCancelled,isOnlineMeeting,onlineMeetingProvider,onlineMeeting,webLink,location,changeKey`, `@odata.nextLink` takip.
- **Pencere:** kullanıcının yerel saatinde bu haftanın başı (`user_settings.week_start`) 00:00 → `+ (weeks_ahead + 1) × 7 gün`. Varsayılan `weeks_ahead = 2`. Delta yok; her tur pencerenin tamamı çekilir (idempotent).
- **Filtre:** varsayılan `teams_only = true`. Teams tespiti: `isOnlineMeeting` ve (`onlineMeetingProvider ∈ {teamsForBusiness, skypeForConsumer, skypeForBusiness}` veya `onlineMeeting.joinUrl` `teams.live.com`/`teams.microsoft.com` içeriyor). Görülen `onlineMeetingProvider` değerleri DEBUG log'a (gerçek hesapta doğrulama için).
- **Veri:** `events` (salt okunur, `created_by="integration"`), `external_links` provider `microsoft`, `entity_type="event"`, `external_id = item.id`, `external_parent_id = "calendar"`, `etag = changeKey`, `url = webLink`. Yeni sütun `events.meeting_url` (String(1000), nullable).
- **Silme:** `isCancelled` → sil; pencere içinde başlayıp artık dönmeyen → sil; pencereden önceki (geçmiş) etkinliklere dokunulmaz. Takvim kapatılınca / bağlantı kesilince Microsoft etkinlikleri silinir (To Do kartları kalır). Hedef board değişince taşınır.
- **Hesap ayarları:** `account.settings["calendar"] = {enabled: false, teams_only: true, board_id: null, weeks_ahead: 2}`; izin verilince kullanıcı açar.
- **Kapsam:** `oauth.PROVIDERS["microsoft"]` kapsamına `Calendars.Read`. Kayıtlı `scope`'ta yoksa takvim senkronu **hesabı error'a almadan** `CALENDAR_CONSENT_REQUIRED` döner (To Do çalışmaya devam eder); UI "Teams toplantıları için izin ver".
- **Ortak kod:** `google_calendar.py`'deki sağlayıcıdan bağımsız mantık **fonksiyon düzeyinde** `app/integrations/calendar_common.py`'ye çıkarılır, `provider` parametreli: `delete_linked_event`, `purge_events(user_id, provider, parent_id=None)`, `rehome_events(user_id, provider, board_id)`, `upsert_external_event(...)` (oluştur/güncelle/etag aynıysa atla; `_fill` dahil), `delete_unseen_in_window(...)`. `GoogleCalendarService` bunları çağırır; **Google testleri (34) hiç değiştirilmeden yeşil kalmalı.** Çıkarma karmaşıklaşırsa (ör. Google'a özgü sync token akışına dolanırsa) yalnız gereken kısmı ortaklaştır, kalanını kopyala ve sapmalar tablosuna yaz.

## Adımlar (task-api)
1. Migration `<rev>_event_meeting_url.py` (`down_revision` = 8c'nin revizyonu). `EventEntity.meeting_url`; `EventResponse`/`CalendarItem` → `meeting_url`. Yedek + kopyada upgrade/downgrade/upgrade.
2. `calendar_common.py` çıkarımı + Google'ı ona bağla → `uv run pytest -q tests/integration/test_integrations_google.py` yeşil.
3. `oauth.py`: kapsama `Calendars.Read`. Bağlan akışında Microsoft için yeniden onay gerektiğinde `prompt=consent` (mevcut parametreleri kontrol et). Hesap yanıtına `calendar_consent: bool` + `calendar` ayarları.
4. `app/integrations/microsoft_calendar.py`: `week_window(now, tz, week_start, weeks_ahead)`, `is_teams(item)`, `map_event(item, tz)` (subject boşsa "(Başlıksız toplantı)"; tüm gün → yerel gece yarısı, bitiş hariç — Google kuralı; tarih ayrıştırma `microsoft_todo.py`'deki 7 haneli kesir/zaman dilimi yardımcısını kullan; `location.displayName`; `meeting_url = onlineMeeting.joinUrl`), `MicrosoftCalendarService.sync(user)` (kullanıcı/sağlayıcı `asyncio.Lock` — To Do ile aynı kilit), `sync_all_accounts()`. `GraphClient`'a gerekirse sayfalı GET yardımcısı.
5. API (`app/api/v1/integrations.py`): `PUT /integrations/microsoft/calendar` {enabled, teams_only, board_id?, weeks_ahead 1–8} (kayıttan sonra senkron; `enabled=false` → etkinlikleri sil; board sahipliği), `POST /integrations/microsoft/calendar/sync` → `SyncResult` (eklendi/güncellendi/silindi). `DELETE /integrations/microsoft` → takvim etkinliklerini de sil.
6. `scheduler.run_once`: Google → Microsoft To Do → **Microsoft takvim** (her biri kendi try/except).

## Adımlar (assistant-service)
7. `schedule_day` çakışma kontrolü: `_prepare_schedule_day` zaman çizelgesini kurduktan sonra o günün `/calendar?start&end`'ini okur; saatli (tüm gün değil) bir etkinlikle çakışan yeni blok varsa `PrepareError`: "«Haftalık toplantı» 14:00–15:00 ile çakışıyor; bu bloğu toplantıdan sonraya kaydır." (odaklı planlayıcının 3 denemeli geri bildirim döngüsü bunu kullanır). Aynı kartın zaten var olan bloğu çakışma sayılmaz. Test: `tests/test_schedule_day.py`'ye 3 test (çakışma reddi, tüm gün yok sayılır, çakışmasız geçer).

## Adımlar (frontend)
8. `IntegrationsSettings.tsx` Microsoft satırına "Teams toplantıları" alt bölümü: izin yoksa "Teams toplantıları için izin ver" (connect akışı); varsa aç/kapa, "Sadece Teams toplantıları" kutusu, hedef board, "Kaç hafta ileri" (1–4), **"Bu haftanın toplantılarını çek"** + sonuç özeti, son senkron.
9. `OAuthSetup.tsx` Microsoft sihirbazına adım: "API permissions → Add → Microsoft Graph → Delegated → Calendars.Read".
10. `CalendarPage.tsx`: Microsoft takvimi açıksa başlıkta "Toplantıları çek" düğmesi; `meeting_url`'li etkinlikte video ikonu (lucide `Video`).
11. `EventDialog.tsx`: Microsoft dış etkinliğinde "Outlook'ta aç" bağlantısı + `meeting_url` varsa birincil **"Teams'te katıl"** düğmesi (yeni sekme).
12. `Reminders.tsx`: `meeting_url`'li etkinlik 5 dk sonra başlıyorsa bildirim + şeritte "Katıl" (mevcut hatırlatıcı yolu etkinlikleri kapsamıyorsa bugünün `/calendar`'ını kullanarak ekle).
13. `api-schema.d.ts` elle (`meeting_url`, hesap alanları).

## Testler (`tests/integration/test_integrations_microsoft_calendar.py`, `HTTP_TRANSPORT` sahte ağ; `test_integrations_microsoft.py` deseni)
Pencere hesabı (pazartesi/pazar hafta başı, saat dilimi, weeks_ahead); sayfalama; Teams filtresi (3 tespit yolu + teams_only=false); `isCancelled`; pencereden düşen silinir, geçmişe dokunulmaz; tüm gün; tekrar örnekleri ayrı satır; changeKey aynı → atla; board taşıma; `enabled=false` ve bağlantı kesme → silme (To Do kartları kalır); kapsam eksik → `CALENDAR_CONSENT_REQUIRED`, hesap error'a düşmez; salt okunur 409; `meeting_url` yanıtta; kullanıcı yalıtımı; zamanlayıcı sırası; Google testleri değişmeden yeşil.

## Kabul ölçütleri
- task-api mevcut + ≥18 yeni, assistant mevcut + 3; `npm run build` temiz.
- **Gerçek hesap (kullanıcıda):** Azure'da izin ekle → Ayarlar → "Teams toplantıları için izin ver" → aç → Teams'te gelecek hafta için toplantı oluştur → "Bu haftanın toplantılarını çek" → `/calendar`'da video ikonlu görünür, "Teams'te katıl" Teams'i açar; toplantıyı iptal et → sonraki senkronda kaybolur. Asistana o güne "planla" de → toplantı saatine blok koymaz.
- **Risk:** kişisel hesapta Teams toplantısı `isOnlineMeeting=false` dönerse ama `joinUrl` gövdede/konumda geçiyorsa tespit genişletilir; hiç görünmüyorsa **ICS aboneliği yedeği** ayrı küçük alt faz (8d-ek, Sonnet) olarak planlanır.

## İlerleme
_(oturum sonunda doldurulur)_
