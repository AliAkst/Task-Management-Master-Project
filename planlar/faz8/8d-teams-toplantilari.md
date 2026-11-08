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
**Durum: ✅ Kod tamam, commit YOK (2026-11-09; commit/push ayrı Haiku oturumu).** Migration `b6d2f8a4c1e9_event_meeting_url.py` (down = `a5c9e1b3d7f2`).

### Yapılanlar
- **Migration/model:** `events.meeting_url` (String(1000), nullable); `EventEntity.meeting_url`, `EventResponse.meeting_url`, `CalendarItem.meeting_url`. Salt okunur 409 mesajı sağlayıcıya göre ("…Outlook/Teams takviminden geliyor…"; Google metni aynen).
- **`app/integrations/calendar_common.py` (yeni):** `MappedEvent` (+`meeting_url`), `fill_event`, `delete_linked_event`, `purge_events(user, provider, parent_id=None)`, `rehome_events(user, provider, board_id, parent_ids=None)`, `upsert_external_event(...)` (oluştur/güncelle/etag+board aynıysa atla), `delete_unseen_in_window(..., window_start=None)`. `GoogleCalendarService` bunlara bağlandı (sync token akışı Google'da kaldı); **Google testleri (34) değişmeden yeşil**.
- **OAuth:** `oauth.PROVIDERS["microsoft"]` kapsamına `Calendars.Read`; zaten bağlı ama takvim izni olmayan hesapta `connect_url` `prompt=consent` ekler. `IntegrationResponse.calendar_consent` (yalnız Microsoft) + `settings.calendar` varsayılanları (`enabled:false, teams_only:true, board_id:null, weeks_ahead:2`). `accounts.has_calendar_scope()` ("Calendars.Read"/"…ReadWrite", `https://…/` önekli de olur).
- **`app/integrations/microsoft_calendar.py` (yeni):** `week_window`, `is_teams`, `map_event`, `MicrosoftCalendarService` (`update_settings`, `disconnect`, `sync`), `sync_all_accounts()`. `GraphClient.get_all()` (sayfalı GET, `@odata.nextLink`). `calendarView` isteği: `Prefer: outlook.timezone="UTC"`, `$top=100`, `$select=…`; her tur pencerenin tamamı; iptal edilen silinir, pencerede dönmeyen silinir, pencereden önce başlayan (geçmiş) dokunulmaz; To Do ile aynı kilit (`lock_for(user, "microsoft")`). Görülen `onlineMeetingProvider` değerleri DEBUG log'a.
- **API:** `PUT /integrations/microsoft/calendar` (kayıt + `enabled` ise hemen senkron; kapatınca etkinlikler silinir; yabancı board → 404/403; izin yoksa 409 `CALENDAR_CONSENT_REQUIRED`), `POST /integrations/microsoft/calendar/sync` → `SyncSummary`, `DELETE /integrations/microsoft` takvim etkinliklerini de siler (To Do kartları kalır). `scheduler.run_once`: Google → Microsoft To Do → Microsoft takvim (her biri kendi try/except).
- **assistant-service:** `schedule_day.find_conflict()` + `WriteTools._check_calendar_conflicts` — `_prepare_schedule_day` zaman çizelgesini kurduktan sonra günün (+ertesi gün, gece yarısını aşan bloklar için) `/calendar`'ını okur; saatli bir etkinlikle çakışan blok `ValueError`: «Haftalık toplantı» 14:00–15:00 ile çakışıyor; 'Blok' bloğunu toplantıdan sonraya kaydır.
- **Frontend:** `IntegrationsSettings` Microsoft satırı "Microsoft To Do ve Teams" + `MicrosoftTeams` alt bölümü (izin yoksa "Teams toplantıları için izin ver"; varsa aç/kapa, Sadece Teams, kaç hafta ileri 1–4, board, Kaydet, "Bu haftanın toplantılarını çek" + özet, son senkron/hata); `OAuthSetup` Microsoft sihirbazına Calendars.Read adımı; `CalendarPage` başlıkta "Toplantıları çek" (Microsoft takvimi açıksa) + `meeting_url`'li etkinlikte `Video` ikonu (`eventContent`); `EventDialog` dış etkinlikte "Teams'te katıl" (yalnız https) + "Outlook'ta aç"; `Reminders` bugünün `/calendar`'ından (60 sn'de bir) toplantı başlamasına ≤5 dk kalınca şerit + "Katıl" + tarayıcı bildirimi. Yeni UI'da `text-on-ink` kuralı uygulandı.
- `api-schema.d.ts`: uygulamanın `app.openapi()` çıktısından `openapi-typescript` ile üretildi (diff yalnız 8d eklemeleri).

### Sapmalar
| Planda | Yapılan | Neden |
|---|---|---|
| `PrepareError` | `ValueError` | assistant-service'te `PrepareError` yok; tüm `_prepare_*` `ValueError` fırlatıyor (odaklı planlayıcının geri bildirim döngüsü onu yakalıyor) |
| Çakışma: "aynı kartın zaten var olan bloğu çakışma sayılmaz" | Mevcut etkinliğin başlığı yeni bloğunkiyle aynıysa (büyük/küçük harf duyarsız) çakışma sayılmaz | `schedule_day` blokları kart id'si taşımıyor; aynı planı yeniden vermek (kart bloğu ya da sabit etkinlik) kendiyle çakışmasın |
| `schedule_day` testleri: 3 | 4 (ek: bulutta gizli board etkinliğinin başlığı sızmıyor — «Başka bir etkinlik») | `local_only` kuralı |
| Çakışma sorgusu yalnız o gün | Gün + ertesi gün (48 sa) | Bloklar gece yarısını aşabiliyor (mevcut `build_timeline` davranışı) |
| `rehome_events(user, provider, board_id)` | + isteğe bağlı `parent_ids` | Google yalnız seçili takvimleri taşıyordu (davranış korunsun) |
| `delete_unseen_in_window` | `window_start` isteğe bağlı; Google `None` geçer (eski davranış: görünmeyen hepsi silinir), Microsoft hafta başını geçer | Plan: Microsoft'ta geçmişe dokunulmaz; Google'ın tam senkron davranışı değişmesin |
| Graph 403 → "To Do izin vermedi" (ortak `_request`) | Takvimde Graph 403'ü `CALENDAR_CONSENT_REQUIRED` olarak yeniden eşlenir | Mesaj To Do'ya özgüydü; kayıtlı kapsam yanlış olsa bile kullanıcıya doğru yönlendirme |
| Takvim son senkron/hata durumu | `account.settings["calendar"].last_synced_at / last_error` (hesabın `last_synced_at/last_error` alanı değil) | To Do `_finish`'i aynı alanları ezerdi |
| Tüm gün tarihi `microsoft_todo` yardımcısıyla | Tüm gün için `start/end.dateTime`'ın **tarih kısmı** alınır; saatliler `_parse_graph_dt` ile | Graph `Prefer: UTC` ile tüm gün etkinliğini gece yarısı UTC döndürür; tarih kısmı etkinliğin günüdür (gerçek hesapta doğrulanmadı) |
| Google testleri "hiç değişmeden" | `test_loop_survives_failures`a 1 satır (takvim işini sahtele) | Sahtelenmezse döngü gerçek DB'ye sürekli istek atıp takılıyordu |
| Eski `test_integrations_microsoft.py::TestScheduler` | Sıra beklentisi `["google","microsoft","takvim"]` (üçüncü iş sahte) | `run_once`'a yeni iş eklendi; sahte olmazsa gerçek DB'ye bakardı |
| Tarayıcı doğrulaması (8001/5175 kopya) | **Yapılmadı**; migration yalnız `%TEMP%\f8d\copy.db` kopyasında denendi | Arayüz bölümü izinli Microsoft hesabı gerektiriyor (gerçek hesap yasak); kopya DB'ye hesap tohumlamak kapsam dışı bırakıldı |
| Yönlendirme sonrası bildirim metni | "Microsoft bağlandı. To Do listelerini seçip kaydet; Teams toplantıları için aşağıdaki bölümden aç." | Metin artık takvimi de kapsıyor |

### Doğrulanmayanlar
- **Gerçek Microsoft hesabı:** Azure'da `Calendars.Read` eklenmesi, "Teams toplantıları için izin ver" akışı (`prompt=consent`), gerçek `calendarView` yanıtları, `onlineMeetingProvider` değerleri (kişisel hesapta `teamsForBusiness` mı `skypeForConsumer` mı?), `isOnlineMeeting=false` dönme riski, tüm gün etkinliğin tarihi, "Teams'te katıl" bağlantısının Teams'i açması — hepsi kullanıcıda. Risk gerçekleşirse (hiç toplantı görünmezse) plandaki **ICS aboneliği yedeği** ayrı küçük alt faz (8d-ek).
- **Arayüz tarayıcıda görülmedi** (Ayarlar alt bölümü, takvimde video ikonu, EventDialog düğmesi, Reminders şeridi): yalnız `tsc -b && vite build` temiz.
- Gerçek modelle `schedule_day` çakışma geri bildirim döngüsü (3 deneme) denenmedi; yalnız birim/entegrasyon testleri.
- Microsoft token yenilemede kapsam değişimi: yenileme kayıtlı `scopes`'u güncellemez; izin yalnız yeniden bağlanınca kaydedilir.

### Test sayıları
- task-api: 333 geçti (önceki 298 + 35 yeni: `tests/integration/test_integrations_microsoft_calendar.py`; Google 34 test aynı, yalnız `test_loop_survives_failures`a takvim işi için bir `monkeypatch` satırı eklendi). assistant-service: 152 geçti (önceki 148 + 4: `tests/test_schedule_day.py`). `npm run build` temiz.
- Migration (DB kopyasında): `upgrade` → `downgrade -1` → `upgrade`, `alembic current` = `b6d2f8a4c1e9 (head)`.
- Ruff: yeni/değişen dosyalarda yalnız E501.
