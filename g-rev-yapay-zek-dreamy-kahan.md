# AI Destekli Kişisel Yaşam & Görev Yönetimi — Genel Çerçeve Planı (v2)

> ## 📍 İlerleme Durumu — 2026-11-08 (yeni oturum buradan devam eder)
>
> **Faz 8 (2026-11-08) planlandı:** `planlar/faz8/00-genel.md` + faz başına detay dosyası (8a–8g, sırayla; her faz yeni Sonnet oturumu, ardından Haiku push). **Sıradaki: 8a** — yeni oturumda yalnız `00-genel.md` + `8a-asistan-kart-araclari.md` oku.
>
> **Branch:** `feature/ai-life-manager` · Faz 0–6 tamam, **7a–7d commit'lendi** (7a–7c: `b8b46d1`, 7d: `b21b062`) ve push edildi. **Opus Faz 7 denetimi yapıldı** (aşağıda "Faz 7 denetimi"); denetimde eklenen OAuth kurulum sihirbazı **commit'lenmedi** (Haiku oturumu). **Sıradaki:** commit/push → kullanıcı gerçek hesaplarla kabul denemesi (Google, Microsoft, Trello, gemma4 triage).

## 0. İlerleme Durumu

### Faz durumu
| Faz | Durum | Commit | Not |
|---|---|---|---|
| 0 — Hazırlık | ✅ Tamam | `54fbde6` | Dapr kaldırıldı, 6 bug + ek bug'lar, user_settings, React iskeleti, dev.ps1, `.claude/agents` |
| 1a — Board & Kartlar | ✅ Tamam | `54fbde6` | boards/lists/cards/notes/checklist/labels, activity_log, kanban (dnd-kit) |
| 1b — Hiyerarşi & Bağlantılar | ✅ Tamam | `4e8431d` | alt kartlar, card_dependencies (DAG), bölme, unblock event'i, React Flow grafik |
| 2 — Takvim | ✅ Tamam | `4e8431d` | events, `/calendar`, FullCalendar, kartı takvime sürükleme |
| 3a — Zaman takibi | ✅ Tamam | `4e8431d` | time_sessions, global kronometre, elle giriş, çakışma kontrolü |
| 3b — Planlama/Değerlendirme/İstatistik | ✅ Tamam | `4e8431d` | day_plans, Bugün sayfası, `/analytics/summary`, İstatistik sayfası, hatırlatıcılar (bkz. sapmalar) |
| 4 — AI Çekirdek | ✅ Tamam | `e52b4b7` | assistant-service, Ollama native adaptörü, benchmark, okuma araçları, gizlilik filtresi, sohbet paneli |
| 5a — AI Aksiyonları | ✅ Tamam | `1d4f701` | yazma araçları, ai_permissions (ask/auto/never), ai_actions, onay kartları, `X-Actor: ai` |
| 5b — Hafıza + Tasarım | ✅ Tamam | `347b36a` | **Tasarım yenilemesi** (aşağıda), user_facts, goals, profil ekranı, tanışma sohbeti, ayrı hafıza çıkarımı |
| 5c — Claude + model ayarları + tasarım gözden geçirme | ✅ Tamam | `a6b5e34` | AnthropicProvider (resmi SDK), Claude/GPT/Gemini bağlantı ekranı (Fernet şifreli key), local-zorunlu varsayılan model, board varsayılan modeli + ModelRouter, ücret uyarısı; tüm sayfaların tasarım gözden geçirmesi (aşağıda) |
| 6a — Gün sonu döngüsü | ✅ Tamam | `f5ae4e8` | değerlendirme → arka plan işi: gün özeti (`ai_summary`) + yarın plan önerisi (gemma4:26b), tahmin katsayısı, arka plan modeli ayarı |
| 6b — Öğrenen asistan | ✅ Tamam | `ff08bce` | haftalık analiz → `ai_insights` (onay → kalıcı bilgi), zincirde sıradaki kart plan önerilerinde |
| 6c — Tekrarlayan işler | ✅ Tamam | `3fa972e` | tekrarlayan etkinlikler (RRULE, takvimde açılır), kart serileri (bitince sıradaki kart), ortak Tekrar seçici |
| 7a — Entegrasyon altyapısı + Trello | ✅ Tamam | `b8b46d1` (7a–7c ortak) | integration_accounts, external_links, Gelen Kutusu, Trello API key+token ile tek seferlik import (§4.1) |
| 7b — OAuth + Google Calendar | ✅ Tamam | `b8b46d1` (7a–7c ortak) | OAuth altyapısı, tek yönlü takvim senkronu, salt okunur etkinlikler (§4.1) |
| 7c — Microsoft To Do | ✅ Tamam | `b8b46d1` (7a–7c ortak) | Samsung Reminder → To Do → Gelen Kutusu; tamamlamayı geri yazma (outbox) (§4.1) |
| 7d — Gelen Kutusu dağıtımı | ✅ Tamam | `b21b062` | asistan kartlara board önerir, madde madde onay kartı (§4.1) |
| 7 denetimi (Opus) | ✅ Tamam | `d0a2c3c` | plan ↔ kod uyumlu; eksik: OAuth kimliği yalnız `.env`'den → **arayüzde kurulum sihirbazı** eklendi (aşağıda) |
| 8a — Asistan: checklist + etiket + "bu kart" | 🟡 Commit'lendi, push bekliyor (gerçek-model kabulü kullanıcıyla) | `6b7e233` | `planlar/faz8/8a-asistan-kart-araclari.md` (genel: `planlar/faz8/00-genel.md`) |
| 8b — Not editörü (çift tıkla düzenle, kod, GFM) | 🟡 Commit'lendi, push bekliyor (görsel kontrol kullanıcıda) | `dcfb1e1` | `planlar/faz8/8b-not-editoru.md` |
| 8c — Kart ekleri | 📝 Planlandı | — | `planlar/faz8/8c-ekler.md` · migration `card_attachments` |
| 8d — Teams/Outlook toplantıları | 📝 Planlandı | — | `planlar/faz8/8d-teams-toplantilari.md` · migration `events.meeting_url` |
| 8e — Sürükle-bırak animasyonları | 📝 Planlandı | — | `planlar/faz8/8e-surukle-birak.md` |
| 8f — Sesli dikte | 📝 Planlandı | — | `planlar/faz8/8f-sesli-dikte.md` |
| 8g — Dark mode + arka plan | 📝 Planlandı | — | `planlar/faz8/8g-tema-dark-mode.md` · migration `theme_settings` |

### Faz 5b'de yapılanlar (ayrıntı)
- **Tasarım yenilemesi (frontend-design skill'iyle):** jenerik SaaS kart kiti → "kâğıt üstüne mürekkep + ajanda sekmeleri".
  - Renkler `index.css` `@theme` içinde: Tailwind `slate` paleti mürekkep tonlarıyla yeniden tanımlandı (kâğıt `#F2F4F8`, mürekkep `#172038`, dolma kalem mavisi `#2B44C9`, kayıt kırmızısı `#D93A4A`). Yeni bileşenlerde de `slate-*`/`blue-*` kullanmak yeterli.
  - Yazı: Bricolage Grotesque (h1/h2 başlıklar), Atkinson Hyperlegible Next (arayüz) — `index.html`'de Google Fonts.
  - Üst menü → sol ray (`Layout.tsx`): ana menü + **hayat alanları renkli ajanda sekmeleri** (tek "cesur" öğe) + kronometre + asistan.
  - Emoji → lucide-react ikonları; büyük harfli etiketler kaldırıldı; "Bugün" sayfasında büyük tarih başlığı; board kartlarında kenar sekmesi; görünür klavye odağı; `prefers-reduced-motion`.
- **Hedefler (task-api):** `goals` tablosu + `/goals` CRUD, board/kart silinince bağlantı kopar (hedef kalır).
- **Hafıza (assistant-service):** `user_facts` (kategori, kaynak, `is_private`; sağlık/ilişki varsayılan gizli → bulut modele gitmez), `/assistant/facts` API'si.
- **Araçlar:** `remember_fact`, `forget_fact`, `save_goal` (izin türleri `remember_fact`, `forget_fact`, `manage_goal`), `list_goals`.
- **Sistem mesajı:** bilinen bilgiler + aktif hedefler + bilinmeyen kategoriler; az bilgi varsa tanışma talimatı.
- **Ayrı hafıza çıkarımı (`app/agent/memory_extractor.py`):** gerçek testte hem qwen3.5:4b hem gemma4:26b sohbet ederken araç çağırmadan "not aldım" dedi. Çözüm: cevaptan sonra tek görevli, sadece hafıza araçlı odaklı ikinci çağrı → öneriler onay kartı olarak gelir (gerçek modelle doğrulandı).
- **Profil sayfası** (`/profile`): bilgileri düzelt/gizle/sil, hedefler, "Tanışma sohbetini başlat".
- **Hata düzeltmeleri:** Ollama araç çağrısı id'leri her akışta `call_0`'dan başlıyordu → turlar arası çakışma (onay sonucu yanlış mesaja yazılabilirdi); artık benzersiz. Sohbet mesajına bağlı olmayan öneriler sayfa yenilenince kayboluyordu → en yakın asistan cevabına bağlanıyor.

### Faz 5c'de yapılanlar (ayrıntı)
- **Claude adaptörü** (`app/llm/anthropic_provider.py`, `anthropic` SDK 2.6): Messages API streaming (`client.beta.messages.stream`), araç sonuçları tek `user` mesajında birleşir, `temperature` gönderilmez (güncel API sürümünde kaldırıldı), `output_config.effort` (varsayılan `medium`), `claude-opus-5-5`/`sonnet-5-5`'te sunucu taraflı `fallbacks: "default"`, `refusal` ve `max_tokens` durdurmalarında araç çalıştırılmaz. **Düşünme blokları** `Msg.provider_state` ile sadece aynı tur içindeki araç döngüsünde aynen geri verilir; veritabanına yazılmaz (sistem mesajı her turda yeniden kurulduğu için turlar arası replay 400 riski taşır). Son turda (FORCE_ANSWER) araç tanımları `tool_choice: none` ile korunur.
- **Sağlayıcı ayarları** (`provider_configs`, `model_prefs`; `app/api/providers.py`): kullanıcı başına sağlayıcı başına tek kayıt, API anahtarı Fernet ile şifreli (`app/security.py`; ana anahtar `ASSISTANT_SECRET_KEY` ya da git'e girmeyen `.secret_key`), yanıtlarda sadece `…son4`. "Anahtarı doğrula" ücretsiz model listesi çağrısı yapar (token harcamaz) ve hesabın modellerini öneri olarak getirir.
- **Model seçimi** (`app/llm/router.py`): mesajda seçilen > açık board'un `default_model_id`'si > kullanıcının local varsayılanı. Varsayılan model **sadece local** olabilir (422). `local_only` board'a bulut model atanamaz (task-api 422); board `local_only`'ye çekilince bulut varsayılanı silinir.
- **Frontend:** Ayarlar → Asistan modeli (local varsayılan + Claude/GPT/Gemini satırları), board formunda "Bu board'da asistan modeli", sohbet panelinde "Otomatik" seçeneği + bulut modele geçerken ücret onay şeridi; bulut seçimi tarayıcıda kalıcı olmaz (yenilenince local'e döner).
- **Tasarım gözden geçirmesi** (1440 px'te tüm sayfalar gezildi, ekran görüntüleriyle eleştirildi): ortak `PageHeader`/`Section`/`Segmented` (`components/Page.tsx`); Ayarlar, İstatistik, gün değerlendirme ve plan düzenleyicideki "beyaz kart kiti" çizgili bölümlere çevrildi; Ayarlar'da sol bölüm menüsü + anında kaydetme; İstatistik'te defter satırı sayılar, mürekkep tonlarında eksen/ızgara, özel ipucu kutusu, veri yokken açıklamalı boş durum (ruh hâli noktalarının görünmeme hatası düzeltildi); FullCalendar `--fc-*` ve React Flow `--xy-*` değişkenleriyle temalandı (sarı "bugün", lacivert düğmeler, iki satırlık "Tüm gün" gitti); ilişki görünümüne çizgi açıklaması; kart penceresi PC'de iki sütun (içerik + künye); değerlendirme formu iki sütun, emoji yerine sözcüklü 1–5 ölçek; ✓ ⛓ ○ 🔒 ⏰ 🗓 gibi metin sembolleri lucide ikonlarına çevrildi; board başlığı/listesinde gizlilik ve atanmış model görünür.

### Faz 6a'da yapılanlar (ayrıntı)
- **Tetikleme:** RabbitMQ olmadığı için `review.submitted` olayı yerine arayüz değerlendirme kaydedilince `POST /assistant/day-review/{gün}` atar. İş assistant-service içinde `asyncio` ile sürer (sayfa kapansa da), işler sırayla çalışır (büyük model bir kez yüklensin). Durum `ai_jobs` tablosunda (queued/running/done/failed); servis yeniden başlarsa yarım işler `failed` olur, "Yeniden oluştur" ile tekrarlanır. Kullanıcının JWT'si kullanılır (30 dk; gemma4:26b gerçek testte 42 sn sürdü).
- **İş (`app/agent/day_review.py`):** model sadece **seçer ve gerekçe yazar** (JSON). Adaylar task-api'nin yarın önerilerinden gelir; bloke, zaten planlı ve (bulut modelde) `local_only` board'a ait olanlar elenir; kullanıcının günlük notu bulut modele gönderilmez. Günlük kapasite son 4 haftada değerlendirilen günlerin ortalama çalışma süresinin 1,25 katı (120–480 dk, veri yoksa 360). Geçmişte reddedilen plan önerileri ve nedenleri isteme eklenir.
- **Tahmin katsayısı:** son 4 haftada biten kartların gerçek/tahmin oranının medyanı (en az 3 ölçüm, 0,5–3 arası); kart süreleri buna göre düzeltilir ve arayüzde "İşlerin genelde tahmininden %35 uzun sürüyor" diye gösterilir.
- **Öneri:** `plan_day` işlemi olarak kaydedilir ve izin moduna uyar (sor → onay kartı, otomatik → hemen eklenir, asla → önerilmez). `plan_day` artık takvim etkinliği (`event_id`) maddesi de alır.
- **task-api:** `PUT /day-plans/{gün}/ai-summary`, yanıtlarda `ai_summary`.
- **Görev bazlı model:** `model_prefs.background_model_id` (boş = önerilen `gemma4:26b`, kurulu değilse sohbet modeli). Bulut seçilebilir, ücret uyarısıyla. Ayarlar → Asistan modeli → "Arka plan işleri".
- **Frontend:** Bugün sayfasında "Asistanın notu" (değerlendirilmiş günde özet, yarın için öneri, gerekçeler, onay kartı; iş sürerken 5 sn'de bir yoklama), planlama modunda önceki akşamın bekleyen önerisi.

### Faz 6b'de yapılanlar (ayrıntı)
- **Haftalık analiz (`app/agent/insights.py`):** kod son 4 haftanın istatistiğinden ölçülebilir sinyaller çıkarır: planların belirgin şekilde daha az bittiği hafta günü (en az 5 değerlendirilmiş gün), enerjinin tamamlama oranına etkisi, tahmin sapması (≥%25), en verimli 2 saat, haftalık süre hedefinin %60'ının altında kalan board'lar, 3+ kez ertelenen kartlar. Model sadece bunları cümleye çevirir ve haftayı özetler (JSON); yazamazsa verideki cümle kullanılır. Her gözlemde kanıt (`evidence`) saklanır. Bulut modelde `local_only` board'lar ve (board'u bilinmeyen) ertelenen kartlar elenir.
- **Tekrar önleme:** onaylanmış gözlem bir daha önerilmez; reddedilen ya da bekleyen gözlem 4 hafta önerilmez. Çalışma başına en fazla 4 gözlem.
- **Ne zaman çalışır:** gün sonu işinden sonra, son 7 günde başarılı analiz yoksa aynı sırada otomatik (`weekly_insights_auto`); Profil'de "Son 4 haftayı analiz et". Aynı `ai_jobs` altyapısı (`kind=weekly_insight`).
- **Onay → bilgi:** "Doğru, hatırla" (istenirse cümle düzeltilerek) → `user_facts` (`source=insight_confirmed`), sohbette sistem mesajına girer. "Doğru değil" → neden kaydedilir.
- **Zincirde sıradaki:** task-api yarın önerilerine yeni tür `next_in_chain`: ön koşullarının hepsi bitmiş ve sonuncusu son 14 günde bitmiş açık kartlar. Hem planlama ekranında ("Sıradaki") hem asistanın gün sonu önerisinde öncelikli aday.
- **Gerçek model:** gemma4:26b örnek 4 haftalık veriyle 8 sn'de 4 doğru gözlem ve hafta özeti üretti; sayıları değiştirmedi. Yerel veritabanında henüz yeterli değerlendirilmiş gün yok, gerçek veride "kalıp bulunamadı" dedi (beklenen).

### Faz 6c'de yapılanlar (ayrıntı)
- **Kurallar (`app/services/recurrence.py`, `python-dateutil`):** RFC 5545 RRULE, sadece günlük/haftalık/aylık/yıllık (saatlik ve daha sık reddedilir); kural kullanıcının **yerel saatinde** açılır (yaz/kış saatinden bağımsız 07:00 hep 07:00), veritabanında UTC.
- **Tekrarlayan etkinlik:** `events.recurrence_rule` (tek satır); `/calendar` ve gün planı önerileri aralıktaki tekrarları sorgu anında açar (tekrar başına satır yok; takvim kimliği `event-{id}-{zaman}`). Plan maddesi o günkü tekrarın saatini alır. Takvimde tekrarlar sürüklenmez; tıklayınca **seri** düzenlenir/silinir.
- **Tekrarlayan kart:** `card_series` (başlık, board, kural, aktif mi) + `tasks.series_id/series_index`. `PUT /cards/{id}/recurrence` ({rule} ya da null). Seri kartı tamamlanınca (kanban, kart penceresi, gün değerlendirmesi — hepsi aynı yoldan) bir kez sıradaki kart açılır: ilk normal listede, başlık/açıklama/öncelik/tahmin/etiketler ve checklist (işaretsiz) kopyalanır; son tarih eski son tarihin saatini koruyan, şimdiden sonraki ilk tekrar (kaçırılan günler atlanır). Kural bitince (`UNTIL`/`COUNT`) seri durur. Kartlarda `series_done_count` ("seri 14 kez tamamlandı").
- **Frontend:** ortak `RecurrencePicker` (Tekrarlanmaz / Her gün / Hafta içi / Haftanın günleri / Her ay / Her yıl / Özel RRULE + bitiş tarihi, okunur Türkçe açıklama — `lib/rrule.ts`); etkinlik penceresinde ve kart penceresinin künyesinde; kanban kartında tekrar ikonu + serideki sıra.

### Kullanıcı testi sonrası düzeltmeler (Faz 6 sonrası)
- **Günü saat saat planlama (`schedule_day`, `app/tools/schedule_day.py`):** gerçek testte local model "kart oluştur → kartın id'siyle takvime koy" zincirini yapamıyordu (kart onaya kadar yok), günü yanlış hesaplıyor (çarşamba → perşembe), saatleri tutarsız diziyordu. Yeni araçta model sadece sırayı ve süreleri verir; günü ("salı", "yarın"), başlangıcı verilmeyen blokların saatini, sabit saatten öncekileri geriye doğru (işe yol 07:00–09:00) ve gece yarısı geçişini KOD hesaplar, çakışmayı modelin düzeltebileceği mesajla reddeder. Tek onay kartı → yapılacak işler kart + takvim bloğu, sabit şeyler (yol/iş) sadece etkinlik, kartlar günün planına.
- **Odaklı planlama adımı (`app/agent/day_planner.py`):** "salı günü için … planla" gibi mesajlar (gün + planlama fiili, soru değil) sohbet modeli yerine tek görevli, tek araçlı, örnekli istemle ve hata geri bildirimiyle (3 deneme) işlenir. Model: panelde elle seçildiyse o; yoksa arka plan modeli (gemma4:26b, local ve kuruluysa). Ölçüm: qwen3.5:4b araç olsa da hiç çağırmadı; odaklı + örnekli istemle 4/4 geçerli çizelge ama anlam hataları (yol süresi, sıra); gemma4:26b daha doğru ama yine tutarsız olabiliyor → onay kartı şart.
- **Hafıza:** sohbet modeli `remember_fact`/`forget_fact` görmez (gerçek testte planlama isteğinde ~20 yanlış/tekrar bilgi kaydetmişti); sadece ayrı hafıza adımı kullanır, o da işlem önerilen turlarda çalışmaz; aynı bilgi tekrar kaydedilmez.
- **Sohbet silme:** SQLite'ta FK kapalı olduğu için silinen sohbetin `ai_actions` kayıtları aynı numarayı alan yeni sohbete karışıyordu; artık sohbetten koparılıyor.
- **Kronometre (Focus To-Do gibi):** sol raydaki "Çalışmaya başla" → kart seçici (bugünün planı + açık kartlar, arama, kartsız çalış), çalışırken "başka karta geç"; isteğe bağlı odak süresi (25/50 dk, ilerleme çubuğu, dolunca bildirim; kayıt durmaz). Bugün → plan maddelerinde ▶.

### Faz 7a'da yapılanlar (ayrıntı)
- **Migration `d9a2c6e4f1b8`:** `integration_accounts`, `external_links`, `boards.system_kind`. Gerçek DB'nin kopyasında upgrade → downgrade → upgrade denendi (gerçek DB'ye dokunulmadı; uygulama bir sonraki açılışta `alembic upgrade head` ile uygular).
- **Altyapı (`app/integrations/`):** `base.py` (`SyncResult`, `IntegrationError`, kullanıcı/sağlayıcı başına `asyncio.Lock`), `accounts.py` (Fernet şifreli kayıt, maskeli yanıt, yeniden bağlanınca ayarlar korunur), `trello.py`. `app/core/crypto.py` = asistan `security.py` kopyası (`TASK_API_SECRET_KEY` ya da git'e girmeyen `services/task-api/.secret_key`); `cryptography`, `httpx` ana bağımlılık.
- **Gelen Kutusu:** `BoardService.get_or_create_inbox()` (`system_kind="inbox"`, `local_only`, tek liste "Gelen"); silme 409 `INBOX_PROTECTED`, yeniden adlandırma serbest. **Bir entegrasyon hesabı kaydedilince otomatik oluşur** (planda çağıran yoktu; 7b/7c aynı `save()` yolunu kullanır).
- **Trello:** `TrelloClient` (key/token sorgu parametresi; `httpx` INFO günlüğü URL'yi yazdığı için `httpx` logger'ı WARNING'e çekildi), saf `map_board()` (arşivli liste/kart ve arşivli listedeki kartlar alınmaz; `Done/Bitti/Tamamlandı/Tamamlanan` → `is_done_list`; `dueComplete` → tamamlandı; renk adı/hex → en yakın palet rengi; ekler açıklamaya link listesi; birden çok checklist → "Ad: madde"; yorumlar → notlar `"<yazar>, <tarih>: "`, `created_at` yorum tarihi). Import doğrudan entity yazar (olay yayını/seri/unblock tetiklenmez), `actor=integration`, `created_by=integration`, tek commit/board; bir board'un hatası diğerlerini durdurmaz.
- **Idempotent kural (ayrıntı):** her nesne için ayrı kontrol — mevcut kart atlanır (yerel düzenlemeler ezilmez) ama o karta eklenen yeni checklist maddesi/yorum alınır; kullanıcının sildiği kart tekrar gelmez; yerelde silinen board/liste baştan kurulur (eski alt bağlantılar `external_parent_id` ile temizlenir).
- **API:** `PUT /integrations/trello`, `GET /integrations`, `DELETE /integrations/{provider}` (kartlar kalır), `GET /integrations/trello/boards`, `POST /integrations/trello/import`. Başkasının board id'si 404.
- **Frontend:** Ayarlar → **Bağlantılar** (`IntegrationsSettings.tsx`, `api/integrations.ts`); `Row` bileşeni `Page.tsx`'e taşındı; Board'lar sayfasında Gelen Kutusu ikonu, board ayarlarında silme yerine "silinemez" notu.
- **Testler:** task-api 153 → **176** (`tests/unit/test_trello_mapping.py`, `tests/integration/test_integrations_trello.py`, `tests/fixtures/trello_board.json`); `npm run build` temiz. Yeni dosyalarda ruff'ta sadece E501 (depoda zaten yaygın).
- **Doğrulanmadı:** gerçek Trello hesabıyla import (key/token verilmedi) ve tarayıcıda Ayarlar → Bağlantılar görsel kontrolü (8000/5173 portları çalışan uygulamada dolu; kopya DB ile önizleme izni verilmedi).

### Faz 7b'de yapılanlar (ayrıntı)
- **OAuth (`app/integrations/oauth.py`, sağlayıcıdan bağımsız):** `PROVIDERS` kaydı (şimdilik `google`; 7c'de `microsoft` sadece buraya bir tanım eklenir). `POST /integrations/{provider}/connect` → `authorize_url`; `state` = 10 dk'lık imzalı JWT (`purpose=oauth_state`, user_id + sağlayıcı; erişim token'ı ya da başka sağlayıcının state'i reddedilir). `GET /integrations/{provider}/callback` auth header'sız çalışır, her sonucu `WEB_BASE_URL/settings?connected=…` ya da `?connect_error=…&message=…` + `#baglantilar` ile **302** yönlendirir (hata sayfasında bile arayüze döner). `ensure_fresh_token()`: bitişe <60 sn → yeniler, eski refresh token korunur; `invalid_grant` → hesap `error`, 409 `INTEGRATION_RECONNECT` ("Yeniden bağlan"; hata durumunda senkron denemeleri anında reddedilir). Hesap etiketi `id_token`'daki e-posta (imza doğrulanmaz, sadece etiket). İstemci kimliği/sırrı yoksa 422 `OAUTH_NOT_CONFIGURED`.
- **Google (`google_calendar.py`):** `calendar.readonly` + `openid email`, `access_type=offline&prompt=consent`. `GET /integrations/google/calendars`, `PUT /integrations/google/settings` {calendar_ids, board_id}, `POST /integrations/{provider}/sync`. Senkron: takvim başına `singleEvents=true`; ilk sefer `timeMin=−30g/timeMax=+180g`, sonra `syncToken` (hesap `settings.sync_tokens`); **410 → tam yeniden senkron** (pencerede artık görünmeyenler silinir); `cancelled` → silinir; etag aynıysa atlanır. Tekrarlayan Google etkinlikleri örnek örnek satır (yerel RRULE yok). Tüm gün: yerel gece yarısı, bitiş haric. `external_id = "<takvim>|<etkinlik>"`, `external_parent_id` = takvim id.
- **Sağlamlık:** bir takvimin hatası diğerlerini durdurmaz (hata `errors` listesinde ve `last_error`'da); takvim başına commit; yerelde silinen (örn. board silinmesi) etkinlik bir sonraki değişiklikte yeniden gelir ve bağlantı yeni etkinliğe taşınır (çoğalmaz). Seçimden çıkarılan takvimin etkinlikleri + sync token'ı silinir; hedef board değişince mevcut etkinlikler yeni board'a taşınır; bağlantı kesilince Google etkinlikleri de silinir (yerel olanlar kalır).
- **Salt okunur:** `EventResponse.external` / `CalendarItem.external = {provider, url}`; `EventService.update/delete` → 409 `EVENT_READ_ONLY`. Etkinlikler `created_by="integration"`.
- **Zamanlayıcı (`scheduler.py`):** `lifespan`'da `asyncio` görevi, ilk tur açılıştan 30 sn sonra, sonra 15 dk'da bir (`sync_all_accounts`); bir hesabın/turun hatası döngüyü durdurmaz. Aynı kullanıcı için `asyncio.Lock` (elle + otomatik çakışmaz).
- **Frontend:** Ayarlar → Bağlantılar'da Google satırı ("Google ile bağlan" → yönlendirme, takvim çoklu seçimi, etkinliklerin board'u/rengi, "Kaydet" (kayıt sonrası otomatik senkron), "Şimdi senkronla" + sonuç özeti, son senkron zamanı, hata/"Yeniden bağlan", "Bağlantıyı kes"); OAuth dönüş bildirimi (URL sonra temizlenir). `EventDialog` dış etkinlikte salt okunur görünüm + "Google Takvim'te aç" bağlantısı; `CalendarPage` dış etkinlikte sürükleme/boyutlandırma kapalı. `api-schema.d.ts`'e `ExternalRef`/`external` elle eklendi (`npm run gen:api` çalışan sunucu ister, çıktısı aynı olmalı).
- **Testler:** task-api 176 → **210** (`tests/integration/test_integrations_google.py`, 34 test: state sahteciliği/süresi/yanlış sağlayıcı, şifreli saklama, token yenileme + iptal edilmiş yetki, takvim/ayar sahipliği, ilk/artımlı senkron, 410, etag atlama, iptal, başlıksız/sıfır süreli etkinlik, yerelde silinen etkinliğin yeniden gelmesi, tek takvim hatası, kullanıcı yalıtımı, salt okunur 409, seçim kaldırma/board taşıma/bağlantı kesme, zamanlayıcı); `npm run build` temiz. Ruff'ta yeni dosyalarda sadece E501. `.env.example`'a `GOOGLE_CLIENT_ID/SECRET` eklendi.
- **Doğrulanmadı:** gerçek Google hesabıyla bağlanma/senkron (Cloud Console kimlik bilgileri verilmedi) ve tarayıcıda Ayarlar → Bağlantılar / dış etkinlik penceresi görsel kontrolü (8000/5173 çalışan uygulamada dolu). Kabul ölçütünün gerçek-hesap kısmı kullanıcıda: `.env`'e kimlik bilgileri → Ayarlar → Google ile bağlan → takvim seç → `/calendar`'da etkinlikler; Google'da silinen etkinlik sonraki senkronda kaybolmalı. Çözülemeyen bir OAuth/refresh hatası çıkarsa yalnızca o iş için Opus hata ayıklama oturumu.

### Faz 7c'de yapılanlar (ayrıntı)
- **OAuth:** `oauth.PROVIDERS["microsoft"]` (yalnızca tanım): `login.microsoftonline.com/consumers/oauth2/v2.0`, kapsam `openid email offline_access User.Read Tasks.ReadWrite`, `response_mode=query`. Hesap etiketi `id_token`'daki `email`, yoksa `preferred_username`. Microsoft her yenilemede yeni refresh token verir; mevcut `_stored_tokens` bunu zaten saklıyor (testle doğrulandı). `.env.example`'a `MICROSOFT_CLIENT_ID/SECRET` eklendi (config'te zaten vardı). **Migration yok** (7a tabloları yetti).
- **İçeri (`app/integrations/microsoft_todo.py`):** `GraphClient` (httpx, `timeout=20`, `HTTP_TRANSPORT` ile sahte ağ), liste başına `…/tasks/delta` (`@odata.nextLink` takip edilir, `deltaLink` `settings.delta_links[liste]`'de), 410 → tam yeniden senkron (uzakta artık olmayan görevlerin kartları arşivlenir). Yeni açık görev → **Gelen Kutusu** kartı (`CardService(actor="integration")`: etkinlik/cache/aktivite yolları çalışır); `external_links` (card, `external_id`=görev id, `external_parent_id`=liste id, `url`=To Do ana sayfası). `@removed` → arşiv (silinmez). Uzakta tamamlandı/yeniden açıldı → kart `CardService` ile tamamlanır/açılır (unblock + seri mantığı çalışır). Yerelde silinen kart geri gelmez.
- **Yankı koruması:** `link.etag = "<sürüm>|<içerik parmak izi>"`; başlık/açıklama/tarih/öncelik yalnız uzak **içerik** gerçekten değiştiyse yazılır. Böylece kendi geri yazmamızın yankısı (To Do'nun yeni sürüm numarası) yerel düzenlemeleri (ör. yerelde yeniden adlandırma) ezmez.
- **Geri yazma (outbox):** `CardService._flag_external_push()` — kartın microsoft bağlantısı varsa ve actor `integration` değilse aynı transaction'da `pending_push=True`; `_apply_status` (kart penceresi, kanban, gün değerlendirmesi, AI) ve `move()` (bitti listesine taşıma) kapsanır. Commit sonrası `microsoft_todo.schedule_push()` (asyncio arka plan, kendi oturumu) hemen dener; her senkron turu **önce** bekleyenleri gönderir, sonra delta çeker. Gönderilen değer kartın o anki durumudur (`completed`/`notStarted`) → art arda aç/kapa tek PATCH. Hata → `push_error` + sonraki turda tekrar; 404 (To Do'da silinmiş) → bir daha denenmez; 401/`invalid_grant` → hesap `error` ("Yeniden bağlan"). Bekleyen push varken uzak durum yerel tamamlamayı ezmez.
- **API:** `GET /integrations/microsoft/lists`, `PUT /integrations/microsoft/settings` {list_ids|null=hepsi}, `GET /integrations/microsoft/status` {pending_push, failed_push}; `POST /integrations/{provider}/sync` artık microsoft'u da çalıştırır. `CardDetail.external = {provider, url, pending_push, push_error}` (Trello kartları da dolar). Liste seçimden çıkarılırsa bağlantıları + delta'sı silinir, **kartlar kalır**. Zamanlayıcı (`scheduler.run_once`) Google'dan sonra Microsoft'u da döndürür.
- **Frontend:** Ayarlar → Bağlantılar'da Microsoft satırı (Bağlan/Yeniden bağlan, liste çoklu seçimi + Kaydet, "Şimdi senkronla" + sonuç, bekleyen/hatalı geri yazma sayısı — bekleyen varken 10 sn'de bir yoklar, Bağlantıyı kes); OAuth dönüş bildirimi sağlayıcıya göre; kart penceresinde "Microsoft To Do'dan / Trello'dan" rozeti (+ "geri yazılıyor… / geri yazılamadı"). `api-schema.d.ts`'e `external`/`pending_push`/`push_error` elle eklendi.
- **Testler:** task-api 210 → **247** (`tests/integration/test_integrations_microsoft.py`, 37 test: eşleme birimleri [HTML gövde, 7 haneli kesir, Windows saat dilimi adı, tarih→yerel 23:59], OAuth/yenileme/iptal, sayfalı delta, idempotent, uzak güncelleme/tamamlama+unblock/yeniden açma/`@removed`, yerelde silinen kart, 410, tek liste hatası, yerel tamamlama→PATCH, bitti listesine taşıma, bekleyen push önceliği, hata→tekrar, 404 bırakma, `push_now`, yankı koruması, AI actor, liste seçimi, bağlantıyı kesme, kullanıcı yalıtımı, zamanlayıcı); `npm run build` temiz.
- **Doğrulanmadı:** gerçek Microsoft hesabıyla bağlanma/senkron/geri yazma (Azure kimlik bilgileri verilmedi; kabul ölçütünün gerçek-hesap kısmı kullanıcıda: Azure uygulaması + `.env` → Ayarlar → Microsoft ile bağlan → telefonda hatırlatıcı ekle ≤15 dk içinde Gelen Kutusu'nda; kartı bitirince To Do'da tamamlanmış görünür) ve tarayıcıda Ayarlar → Bağlantılar / kart rozeti görsel kontrolü. Samsung Reminder'ın To Do'ya senkron açılımı ve görevlerin gerçekten `consumers` uç noktasında göründüğü hâlâ gerçek hesapla teyit edilmeli.
- **Commit/push (Haiku oturumu, yapıldı):** 7a–7c tek commit `b8b46d1` (dosyalar fazlar arasında ortak: `api/v1/integrations.py`, `config.py`, `main.py`, `IntegrationsSettings.tsx`, `SettingsPage.tsx`; faz bazlı bölünürse ara commit'ler import edemez). Push: `origin/feature/ai-life-manager`.

### Faz 7d'de yapılanlar (ayrıntı)
- **Backend (`services/assistant-service`):** `app/agent/inbox_triage.py` (`day_review` deseni). Adaylar: Gelen Kutusu'ndaki (`system_kind=inbox`) açık, üst düzey kartlar; son 14 günde bekleyen/reddedilmiş `triage_inbox` önerisinde geçenler elenir; en fazla 20. Kart başına açıklama (200 karakter) ve hedef board'ların ad + `scope_description` + listeleri isteme girer. Model JSON `{"moves":[{card_id, board_id, list_id?, reason}]}` döndürür; `pick()` bilinmeyen kart/board, tekrar, Gelen Kutusu'nun kendisi ve gizli/arşivli board'u atar, geçersiz/eksik liste → board'un ilk bitmemiş listesi. Reddedilenlerin nedeni isteme eklenir.
- **Gizlilik:** Gelen Kutusu varsayılan `local_only` → bulut modelle çalıştırılırsa model hiç çağrılmaz, "gizli" notu döner; kullanıcı Gelen Kutusu'nu `cloud_allowed` yaparsa bile `local_only` hedef board'lar ve kullanıcının serbest notu gönderilmez.
- **İşlem türü `triage_inbox`** (`write_tools.py`: `ACTION_TYPES`, `_prepare_triage_inbox`, `_execute_triage`, `triage_summary`, `without_cards`): prepare id'leri çözer (kart/board/liste adı), yürütücü her madde için `POST /cards/{id}/move` (`X-Actor: ai`). **Onay anında kart hâlâ Gelen Kutusu'ndaysa taşınır; arada elle başka yere taşınmışsa atlanır** (`skipped`); bir kartın hatası diğerlerini durdurmaz. İzin modu ask/auto/never (Ayarlar → Asistan izinleri'nde etiketi otomatik gelir; `SettingsPage.tsx` değişmedi çünkü etiketler backend'den geliyor).
- **Madde madde onay:** `POST /actions/{id}/approve` gövdesine `exclude_card_ids` eklendi; çıkarılanlar `args`'tan düşülür, özet yeniden kurulur, hepsi çıkarılırsa 422.
- **İş:** `ai_jobs.kind=inbox_triage`; `POST/GET /assistant/inbox-triage` (güne bağlı değil: süren iş varsa o döner). Model = arka plan modeli (`start_job` mevcut yolu). Migration yok.
- **Frontend:** `components/InboxTriage.tsx` — Gelen Kutusu board sayfasında üst şerit (iş durumu yoklaması, "Asistan dağıtsın", `ActionCard` ile onay) ve `useAutoInboxTriage()` (Layout; açılışta Gelen Kutusu'nda kart varsa günde en fazla bir kez, localStorage `ajanda.inboxTriageDay`, hata sessiz). `ActionCard`'a isteğe bağlı `items` (onay kutulu maddeler, "Seçili N kartı onayla", atlanan/başarısız sayısı). `api/assistant.ts`: `useInboxTriageJob`, `useStartInboxTriage`, `approve` `excludeCardIds`.
- **Testler:** assistant-service 96 → **120** (`tests/test_inbox_triage.py`, 18 test: saf yardımcılar, aday sınırı/elemeler, geçersiz id eleme, gizlilik [bulut + açık inbox + gizli board], boş inbox'ta model çağrılmaz, ayrıştırılamayan cevap, bekleyen/reddedilen önerinin 14 gün tekrar gelmemesi + ret nedeninin isteme girmesi, izin modları, iş → onay → madde çıkarma, hepsini çıkarma 422, arada taşınan kartın atlanması, izin listesi). `npm run build` temiz.
- **Doğrulanmadı:** gerçek gemma4:26b ile 5 örnek kart (kabul ölçütünün gerçek-model kısmı; istem zayıf çıkarsa önce örnekli istem eklenir) ve tarayıcıda Gelen Kutusu şeridi görsel kontrolü (8000/5173 çalışan uygulama gerçek veritabanıyla dolu; açılışta otomatik tetik gerçek modeli çalıştıracağı için önizleme açılmadı). Gerçek denemede: Gelen Kutusu'na birkaç kart ekle → board sayfasında "Asistan dağıtsın" → onay kartı → madde çıkar/onayla.
- **Commit/push (Haiku oturumu, yapıldı):** 7d tek commit `b21b062`. Push: `origin/feature/ai-life-manager`. Ruff: yeni dosyalarda yalnız E501 (5 satır; depoda zaten yaygın).

### Faz 7 denetimi (Opus, 2026-11-08)
- **Sonuç:** 7a–7d adımları ve test kapsamı planla uyumlu; sapmalar zaten tabloda gerekçeli. task-api 247 → **265** test, assistant 120, `npm run build` temiz, ruff'ta yeni dosyalarda yalnız E501.
- **Eksik bulundu ve düzeltildi — OAuth kurulumu:** Google/Microsoft istemci kimliği/sırrı yalnız `services/task-api/.env`'den okunuyordu; arayüz sadece "`.env`'e yaz" hatası veriyordu, kullanıcı kendi başına bağlanamıyordu.
  - **Backend:** `oauth_clients` tablosu (migration `e4b8c2f6a9d3`, kullanıcı başına sağlayıcı başına; sır Fernet şifreli, API'den hiç dönmez). Çözüm sırası: arayüzden girilen → `.env` (yedek). `GET /integrations/oauth-clients` (configured/source/client_id/**redirect_uri**), `PUT|DELETE /integrations/{provider}/oauth-client`. Biçim denetimi sık kopyalama hatalarını yakalar: Google kimliği `.apps.googleusercontent.com` ile bitmeli; Microsoft kimliği GUID olmalı, sır alanına **Secret ID** (GUID) yapıştırılırsa "Value'yu kopyala" uyarısı; boşluk/satır sonu.
  - **Hata mesajları:** token ucundan `invalid_client`/`unauthorized_client` → "Kimlik bilgilerini değiştir" yönlendirmesi (`OAUTH_INVALID_CLIENT`); `redirect_uri_mismatch` → eklenecek tam adres; sağlayıcının callback'e gönderdiği `error_description` (ör. Microsoft AADSTS) ilk satırıyla gösterilir; yenilemede `invalid_client` da hesabı "Yeniden bağlan"a alır (önceden her 15 dk'da 502 tekrarlanırdı).
  - **Frontend:** `components/OAuthSetup.tsx` — "Kurulumu başlat" → adım adım sihirbaz (Google: proje, Calendar API, Auth Platform, **Publish app** (7 günlük token düşmesine karşı), Web client + kopyalanabilir yönlendirme adresi; Microsoft: Samsung Reminder senkronu, Azure App registrations, *Personal Microsoft accounts only*, Web yönlendirmesi, **Value** sırrı) → "Kaydet ve bağlan" (kaydeder, izin ekranına yönlendirir). Kurulu iken satırda kimlik özeti + "Kimlik bilgilerini değiştir" / "Sil". Google/Microsoft satırları tek `OAuthRow` bileşeninde birleşti.
  - **Testler:** `tests/integration/test_oauth_clients.py` (18: şifreli saklama, sır dönmez, arayüz kimliği ile tam bağlanma, `.env` önceliği/geri düşme, kullanıcı yalıtımı, biçim hataları, eyleme dönük hata mesajları).
  - Tarayıcıda doğrulandı (8001/5175 kopya portlarda; `vite.config.ts` artık `TASK_API_PROXY`/`ASSISTANT_PROXY` ortam değişkenini okur, `.claude/launch.json`'a `task-api-alt`/`web-alt` eklendi). Migration gerçek DB'ye uygulandı (öncesinde yedek alındı).
- **Bulundu, geri alındı:** commit'lenmemiş `scripts/start-app.ps1` değişikliği (`uvicorn --reload`): denetim sırasında dosya değişince Windows'ta yeniden başlatma takıldı — reloader 8000 portunu tuttu ama yanıt vermedi (uygulama erişilemez oldu); ayrıca reload migration çalıştırmıyor. Kullanıcı kararıyla geri alındı (`git checkout`). **Kural:** kod güncellenince (yeni oturum, `git pull`) "Ajanda - Durdur" → "Ajanda" (bu, `.env` eşitlemesi + migration'ı da çalıştırır).
- **Hâlâ kullanıcıda (kabul ölçütlerinin gerçek-hesap kısmı):** Google bağlan → takvim seç → `/calendar`; Microsoft bağlan → telefonda hatırlatıcı ≤15 dk Gelen Kutusu'nda, kartı bitir → To Do'da tamamlandı; Trello gerçek board import; gemma4:26b ile 5 kartlık triage. Çözülemeyen OAuth/refresh hatasında ayrı Opus hata ayıklama oturumu.
- **Gözlem (değişiklik gerekmedi):** Google ilk senkronda `nextSyncToken` dönmezse her tur tam senkron yapılır (doğru ama daha yavaş); Microsoft'ta kişisel hesapla Azure'da uygulama kaydı için ücretsiz Azure dizini istenebilir (sihirbazda not var).

### Plandan bilinçli sapmalar
| Plan | Yapılan | Neden |
|---|---|---|
| OAuth kimliği `.env`'de (§4.1 7b/7c ön koşul) | Arayüzde kurulum sihirbazı + şifreli `oauth_clients`; `.env` yedek | Kullanıcı `.env` düzenlemeden, yönlendirilerek bağlanabilsin |
| Model `[{card_id, board_id, list_id?, reason}]` seçer (§4.1 adım 2) | Aynen; ayrıca kart/board'un kendisi de modele gerçek id'siyle gösterilir | Numara eşlemesi yerine doğrudan id + kodla doğrulama yeterli |
| Tek onay kartı, kullanıcı tek tek çıkarabilir (adım 3) | `ActionCard` `items` + `exclude_card_ids` (onay anında `args` süzülür) | Madde seçimi için backend'de ayrı uç gerekmedi |
| Yürütücü kartı taşır (adım 3) | + onay anında kart hâlâ Gelen Kutusu'ndaysa taşır, değilse atlar | Öneri ile onay arasında kullanıcı kartı elle taşımış olabilir |
| Tetik: açılış + düğme (adım 5) | Aynı; ek olarak bekleyen/yakında reddedilmiş kartlar için model hiç çağrılmaz | GPU'yu boşuna meşgul etmesin |
| Ollama için OpenAI-uyumlu adaptör | Ollama **native** `/api/chat` adaptörü | `/v1` `num_ctx`'i yok sayıyor: 4B model 14.3 GB / %38 GPU → native + 16K: 3.6 GB / %100 GPU (~3.5× hız) |
| Hatırlatıcılar: notification-service + APScheduler + Web Push | Frontend `Reminders.tsx` (uygulama açıkken tarayıcı bildirimi + şerit) | Bu makinede Docker/RabbitMQ yok. Gerçek push Docker kurulunca |
| `daily_stats` / `card_stats` tabloları | Her istekte hesaplanan `/analytics/summary` | Kişisel ölçekte veri küçük; önbellek tablo eskiyebilirdi |
| Hafıza aracını sohbet modeli çağırır | Ayrı, odaklı hafıza çıkarımı adımı | Modeller sohbet ederken araç çağırmıyordu (yukarıda) |
| Faz 5 tek parça | 5a / 5b / 5c | Kapsam büyüklüğü |
| `provider` = ollama/openai/anthropic/openai_compatible, `is_default` kayıtta | Claude/GPT/Gemini (Gemini, Google'ın OpenAI-uyumlu uç noktasıyla mevcut adaptörü kullanır); varsayılan ayrı `model_prefs` tablosunda ve **sadece local** | Kullanıcı kararı: varsayılan hep local, bulut ücretli olduğu için bilerek seçilir |
| `boards.default_model_config_id` (FK) | `boards.default_model_id` (`"saglayici:model"` metni) | Ayrı servis/veritabanı; model kimliği zaten saglayici:model biçiminde |
| `review.submitted` olayını dinleyen tüketici | Arayüzün tetiklediği servis içi arka plan işi (`ai_jobs`) | RabbitMQ/Docker yok |
| `model_routes` tablosu (chat/background_planning/insight/classification) | `model_prefs.background_model_id` (sohbet = varsayılan, arka plan = tek ayar) | Şimdilik iki görev sınıfı yeterli; sınıflandırma Faz 7'de |
| pgvector semantik arama (ops.) | Yapılmadı | SQLite, Docker yok |
| `card.unblocked` olayıyla sıradaki kartı takvime otomatik koyma (`schedule_next_in_chain` izni) | Açılan kart ertesi günün plan önerilerine `next_in_chain` olarak düşer; asistan gün sonu planında önceliklendirir | Olay kuyruğu yok; plan önerisi zaten onay/izin akışından geçiyor |
| `series` tablosu (kart ve etkinlik ortak) | Kartlar için `card_series`; etkinlikte kural doğrudan `events.recurrence_rule` | Etkinlik tekrarları satır değil, sorgu anında açılıyor; seriye sadece kartların "kaçıncı" sayacı için gerek var |
| Tekil tekrarı düzenleme/silme (istisnalar) | Değişiklik bütün seriye uygulanır | İlk sürümde sade tutuldu; EXDATE ile eklenebilir |
| `propose_insight` sohbet aracı | Sadece haftalık analiz gözlem üretir | Model kalıp uydurmasın: gözlemler veriden hesaplanır |
| Gelen Kutusu'nu çağıran yer yok (§4.1) | Entegrasyon hesabı kaydedilince `get_or_create_inbox()` çağrılır | Aksi halde board hiç oluşmuyordu; 7b/7c aynı yolu kullanır |
| Trello etiketi için `external_links` | Etiket board içinde ada göre eşlenir (bağlantı yok) | Etiket idempotent zaten; ek tablo satırı gereksiz |
| Google etkinlikleri `activity_log`'a yazılır ("actor=integration") | Yazılmıyor | Dış takvim gürültüsü "planlanan vs gerçekleşen" zaman bloğu istatistiğini bozardı; `created_by="integration"` ayırt etmeye yeter |
| `PUT /integrations/google/settings` yalnızca takvim + board seçer (§4.1 adım 3) | Ek olarak seçimden çıkan takvimin etkinlikleri silinir, board değişince etkinlikler taşınır, bağlantı kesilince Google etkinlikleri de silinir | Aksi halde salt okunur kalan "yetim" etkinlikler düzenlenemez/silinemez kalırdı |
| Takvimde Google ikonu (§4.1 adım 7) | Pencerede kaynak adı + "Google Takvim'te aç" bağlantısı; takvim ızgarasında ikon yok | Görsel kontrol edilemedi; board rengi + sürükleme kilidi yeterli ayrım |
| To Do `dueDateTime`/`reminderDateTime` → `due_date` (§4.1 adım 3) | Bitiş tarihi varsa **tarihi** alınıp kullanıcının yerel gününde 23:59 yapılır (arayüzdeki tarih seçiciyle aynı kural); yoksa hatırlatıcı anı. Bilinmeyen (Windows) saat dilimi adı UTC sayılır | To Do bitişi aslında tarihtir (00:00 UTC yollar); saat dilimi çevirisi günü kaydırırdı |
| Yeni görev → kart (§4.1 adım 3) | Zaten **tamamlanmış** yeni görevler alınmaz | İlk delta tüm geçmişi getirir; bitmiş yüzlerce kart Gelen Kutusu'nu boğardı. Bilinen görev uzakta tamamlanırsa kart yine tamamlanır |
| Alan güncellemesi: her etag değişiminde (§4.1 adım 3) | Yalnız uzak içerik parmak izi değiştiyse | Kendi PATCH'imizin yankısı yerel düzenlemeleri ezmesin |
| Outbox kancası yalnız `_apply_status`'ta (§4.1 adım 4) | `_apply_status` + `move()` (bitti listesine taşıma) | Kanban sürüklemesi `_apply_status`'tan geçmiyor |
| Kapsam `offline_access User.Read Tasks.ReadWrite` | + `openid email` | Hesap etiketi (e-posta) için `id_token` gerekir |
| Gün değerlendirmesinde tamamlanan kart anında push (ihtimal) | Anında push yalnız `CardService` commit yolunda; gün değerlendirmesi sonrası 15 dk'lık turda gider | `day_plan` kendi commit'ini yapıyor; ayrıca kanca eklemeye değmedi |
| Bulut modellerle gerçek test | Sadece birim/entegrasyon testleri (sahte istemci); gerçek API'ye istek atılmadı | Kullanıcı kararı: API maliyeti |
| Faz 7 push: 4 ayrı commit (7a, 7b, 7c, 7d) | 2 commit: 7a–7c `b8b46d1`, 7d `b21b062` | 7a–7c dosyaları ortak (`api/v1/integrations.py`, `config.py`, `main.py`, `IntegrationsSettings.tsx`, `SettingsPage.tsx`); faz bazlı bölünürse ara commit'ler import hatası verirdi. 7d dosyaları ayrı, bağımsız |

### Bilinen sorunlar / dikkat
- **qwen3.5:4b** hızlı ve araç çağrılarında doğru ama çok adımlı işte zayıf: onay beklerken "ekledim" diyebiliyor, anlam hataları yapıyor (koşu etkinliğini "ayakkabı al" kartına bağladı). Onay kartları gerçeği gösteriyor; Faz 6'da görev bazlı yönlendirme (planlama → gemma4:26b) bunun için.
- Sohbet geçmişinde model önceki "not aldım" kalıbını taklit edebiliyor.
- Lokal test DB'sinde test verileri var (Spor/Date/Eğitimler board'ları, "Koşu ayakkabısı al" AI kartı, bekleyen bir hafıza önerisi).
- task-api'de eski dosyalarda birkaç lint uyarısı (Faz 0 öncesinden).

### Yeni oturum için hızlı başlangıç
- **Ortam:** Windows, Docker YOK (SQLite), uv: `C:\Users\alium\AppData\Roaming\Python\Python313\Scripts\uv.exe` (PATH'te değil). Ollama kurulu (qwen3.5:4b, gemma4:26b, qwen3.8:27b; deepseek-r1 ve coder listede gizli). GPU: RTX 4060 Laptop 8 GB.
- **Günlük kullanım:** masaüstündeki **Ajanda** kısayolu (`scripts/start-app.ps1`: servisleri penceresiz başlatır, Ollama kapalıysa açar, hazır olunca tarayıcıda açar; ikinci tıklama sadece tarayıcıyı açar), **Ajanda - Durdur** ile kapatılır. Kısayolları yeniden kurmak: `scripts/install-shortcut.ps1`. Kayıtlar `scripts/logs/`.
- **Asistan veritabanı:** sadece `ASSISTANT_DATABASE_URL` okur (eskiden `DATABASE_URL` sızınca boş `task_management.db` açıyordu).
- **Profil temizliği:** sohbette "profilimi temizle" → kod tekrarları, tek güne ait ve anlamsız bilgileri bulur, tek onay kartıyla pasife alır.
- **Çalıştırma:** `./scripts/dev.ps1` ya da önizleme (`task api project/.claude/launch.json`: task-api 8000, assistant 8100, web 5173).
- **Testler:** `services/task-api`: `uv run pytest -q` (265) · `services/assistant-service`: `uv run pytest -q` (120) · `apps/web`: `npm run build`.
- **Bulut model anahtarı:** `ASSISTANT_SECRET_KEY` yoksa ilk kayıtta `services/assistant-service/.secret_key` üretilir (git'te yok). Silinirse kayıtlı API anahtarları çözülemez, yeniden girilmeli.
- **Test hesabı:** `apps/web/README.md`.
- **Benchmark:** `services/assistant-service`: `uv run python -m scripts.benchmark_models` (rapor `benchmark_results/`, git'te yok).

---

## Context

Elimizde, öğrenme amaçlı yazılmış ve sağlam bir altyapısı olan bir **task-api** (FastAPI + PostgreSQL + Redis + Dapr/RabbitMQ, Repository/Specification/UoW, resilience desenleri, JWT auth) ve bir **notification-service** var. Bugün sadece düz bir `tasks` tablosu ve CRUD bulunuyor; arayüz, board/kart yapısı, takvim, süre takibi ve AI yok.

Hedef: bu altyapıyı atmadan genişleterek Trello benzeri board'lar, birbirine bağlanabilen hiyerarşik kartlar, birleşik takvim, kronometre + planlama/değerlendirme akışı ve **modelden bağımsız** (öncelik local) bir kişisel AI asistanı içeren bütünleşik bir uygulamaya dönüştürmek. Uygulama şimdilik **sadece PC'de, tarayıcıdan (localhost), Türkçe** kullanılacak; ama ileride ürünleşebileceği için **çok kullanıcıya hazır** (her şey `user_id` ile sahiplenilmiş, her kullanıcı kendi model/key ayarını getirir) tasarlanıyor.

### Senin cevaplarından çıkan kararlar
| Konu | Karar |
|---|---|
| Platform | PC, tarayıcı, localhost. Mobil/PWA yok |
| Local model | Laptop RTX 4060 Ti (**8 GB VRAM**) + 32 GB RAM → **7–9B parametre, Q4 quantize, tool-calling destekli** model tamamen GPU'da hızlı çalışır; 14B RAM'e taşar ve yavaşlar. Bağlam penceresi pratikte ~8–16k → mimari "özet veri + ihtiyaç halinde tool" üzerine kurulu |
| Cloud modeller | Claude ve GPT bağlanabilecek (API key gerekiyor, ayrı ücretli). Sohbette **mesaj bazında model seçimi** ("bunu Claude'a sor") + **board bazlı varsayılan model** (ör. Spor → Claude) |
| AI yazma yetkisi | **Sen karar verirsin**: işlem türü bazlı izin sistemi. AI bir işlemi ilk kez yapacağında sorar: "Bunu bundan sonra otomatik yapayım mı?" → cevabın kaydedilir, Ayarlar'dan değiştirilebilir |
| Gizlilik | Board bazlı kullanıcı seçimi: `cloud_allowed` / `local_only`. local_only board verisi cloud modele asla gitmez; o board için cloud model seçilirse uyarı + engel |
| Altyapı | **Dapr kaldırılır** (her servis için ayrı sidecar + CLI, Windows'ta geliştirmeyi yavaşlatır, katma değeri az). **RabbitMQ ve Redis kalır** (tek container'lar, zaman çalmaz; event'ler AI'ın öğrenme/tetikleme akışları ve çok kullanıcı ölçeği için değerli). Zaten var olan `core/messaging.py` (aio-pika) ve notification-service `consumer.py` (DLQ'lu) kullanılır |
| Veri/istatistik | Geçmiş baştan itibaren eksiksiz tutulur: aktivite log'u, süreler, kaçıncı tamamlama, erteleme, tahmin vs gerçek, plan kabul/ret → hem performans istatistikleri hem AI'ın seni öğrenmesi için |
| Planlama zamanı | Kullanıcı ayarlar: planlama saati (sabah ya da akşam) ve değerlendirme saati, ikisine de hatırlatma |
| Kartlar | Ana görev → alt görevler (tam kart), checklist, kartlar arası **bağımlılık ipleri**, grafik görünüm. AI parçalayıp bağlayabilir, biri bitince sıradakini atar/planlar |
| Tekrarlayan işler | Acelesi yok → Faz 6. Ama "kaçıncı sefer" istatistiği için `series` kavramı veri modeline baştan konur |
| Entegrasyonlar | Önce kendi içinde çalışsın; Faz 7'de Trello (tek seferlik import), Google Calendar (Gmail kapsam dışı), Microsoft To Do (Samsung Reminders buradan) |
| Local modeller | Elindeki modellerden benchmark ile seçim; görev bazlı yönlendirme (hızlı model sohbet, büyük model arka plan planlaması) — bkz. §8 |

> ⚠️ Proaktif uyarılar
> 1. **Proje klasörü git repo'su değil.** Paralel agent'lar (worktree) ve faz bazlı geri dönüş için Faz 0'da `git init` şart.
> 2. **Samsung Reminders'ın bildiğim kadarıyla herkese açık bir API'si yok.** Samsung Reminder'ın Microsoft To Do / Outlook senkronizasyonu açılırsa veriler Microsoft Graph API üzerinden dolaylı çekilebilir — Faz 7'de doğrulanacak.
> 3. 8 GB VRAM'e sığan küçük model hızlı ama çok adımlı planlamada zayıf kalabilir; elindeki 26–32B modeller ise kaliteli ama RAM'e taşdığı için yavaş olacak. Çözüm: görev bazlı model yönlendirme + onay akışı (bkz. §8).

---

## 1. Mimari

```
┌──────────────────────────── apps/web (React SPA) ─────────────────────────────┐
│ Boards · Kart detayı · Grafik görünüm · Takvim · Timer · Plan/Değerlendirme   │
│ İstatistikler · AI Chat (model seçici) · Ayarlar (modeller, izinler, gizlilik)│
└───────────────┬───────────────────────────────────────────┬───────────────────┘
                │ REST (JWT)                                │ REST + SSE (stream)
        ┌───────▼──────────┐  tool çağrıları (REST,           ┌▼──────────────────┐
        │    task-api      │◄─── kullanıcının JWT'si ile) ────│ assistant-service │
        │ (modüler monolit)│                                   │   (yeni, FastAPI) │
        │ boards · cards · │                                   │ Provider katmanı  │
        │ deps · events ·  │                                   │ Agent loop · Tools│
        │ sessions · plans │                                   │ Hafıza · İzinler  │
        │ activity · stats │                                   │ Gizlilik filtresi │
        └──┬────────┬──────┘                                   └──┬─────────┬──────┘
           │        │     RabbitMQ (aio-pika, topic exchange)      │         │
     PostgreSQL   Redis ── card.completed, card.unblocked, ──────► │   ┌─────▼────────┐
   (schema: app,  (cache,   session.stopped, review.submitted      │   │ Ollama(local)│
    assistant)    rate      plan.reminder_due ...                  │   │ Claude API   │
           ▲      limit)              │                            │   │ OpenAI API   │
           │                 ┌────────▼──────────────┐             │   └──────────────┘
           └─ assistant ───  │ notification-service  │ ──► Tarayıcı bildirimi (Web Push)
              şeması         │ APScheduler: plan/    │
                             │ review hatırlatıcıları│
                             └───────────────────────┘
```

**Kararlar ve gerekçeler**
- **task-api genişletilir (modüler monolit).** Board, kart, bağımlılık, etkinlik, session ve plan birbirine sıkı bağlı (aynı transaction, aynı sahiplik kontrolü). Her domain kendi `entities / repositories / services / api` dosyalarıyla mevcut katman düzenine eklenir.
- **AI ayrı servis (`assistant-service`).** LLM çağrıları yavaş/stream'li ve ağır bağımlılık getirir. **AI veriye yalnızca task-api REST API'si üzerinden, kullanıcının JWT'siyle erişir** → doğrulama, sahiplik, cache invalidation, aktivite log'u ve event'ler AI işlemleri için de otomatik çalışır.
- **Event'ler:** `TaskEventPublisher` → genel `DomainEventPublisher` (Dapr yerine doğrudan aio-pika). Örn. `card.completed` → bağımlı kartlar `card.unblocked` olur → assistant-service sıradakini atar/planlar (izne göre).
- **Hatırlatıcılar:** notification-service'e APScheduler eklenir; kullanıcının ayarladığı saatlerde tarayıcıya Web Push bildirimi gönderir (simülasyon olan email/webhook handler'ları gerçek kanala dönüşür).
- **Tek komutla geliştirme ortamı:** `docker compose` (Postgres, Redis, RabbitMQ) + servisleri birlikte başlatan bir PowerShell dev script'i. Ollama Windows'ta native çalışır (GPU erişimi için).
- **Resilience:** `core/resilience.py`'deki `ai_feature`, `external_api_bulkhead`, `with_timeout`, `CircuitBreaker` LLM ve entegrasyon çağrılarında kullanılır.

### Teknoloji önerileri
| Alan | Seçim | Gerekçe |
|---|---|---|
| Frontend | **React + TypeScript + Vite** | En geniş ekosistem; aşağıdaki kütüphanelerin hepsi birinci sınıf destekli |
| Sunucu state | **TanStack Query** | Cache/invalidation, optimistic update (kart sürükleme için kritik) |
| UI state | **Zustand** | Aktif timer gibi küçük global state için sade |
| UI kit | **Tailwind + shadcn/ui** | Hızlı, sahiplenilebilir bileşenler |
| Drag & drop | **dnd-kit** | Liste/kart sıralama ve listeler arası taşıma |
| Takvim | **FullCalendar (React, MIT core)** | Gün/hafta/ay, sürükle-bırak, kartı takvime bırakıp zaman bloğu oluşturma |
| Bağlı kart grafiği | **React Flow (@xyflow/react)** | Düğüm/ip görünümü, sürükleyerek bağlantı kurma, otomatik yerleşim (dagre) |
| Grafikler (istatistik) | **Recharts** | Basit, React-dostu |
| Notlar | **Markdown** (textarea + `react-markdown` önizleme) | Sade; AI'ın da okuması/yazması kolay |
| API tipleri | **openapi-typescript** | FastAPI OpenAPI şemasından TS tipleri → otomatik sözleşme |
| Chat stream | **SSE** | Tek yönlü token akışı için WebSocket'ten basit |
| Local LLM | **Ollama** (Windows native) | OpenAI-uyumlu `/v1` + tool calling; model değişimi tek komut. 8 GB VRAM için 7–9B Q4 model |
| Cloud SDK | resmi `anthropic` ve `openai` Python SDK'ları | Kendi ince adaptör katmanımız altında |
| Zamanlayıcı | **APScheduler** (notification-service) | Hatırlatıcılar; Celery'ye gerek yok |
| Bildirim | **Web Push** (`pywebpush` + service worker) | Sekme kapalıyken bile tarayıcı açıksa bildirim; localhost'ta çalışır |
| Semantik arama (ops., Faz 6) | **pgvector** + Ollama embedding modeli | Ayrı vektör DB'ye gerek yok |
| Gizli bilgi saklama | `cryptography.Fernet` (anahtar `.env`'de) | API key ve entegrasyon token'ları DB'de şifreli |

### Repo yerleşimi
```
Task-Management-Master-Project/
├── apps/web/                       # YENİ — React SPA
├── services/task-api/              # GENİŞLER — yeni domain modülleri
├── services/assistant-service/     # YENİ — AI
├── services/notification-service/  # Hatırlatıcı + Web Push
├── infrastructure/docker/          # Dapr klasörü kaldırılır
└── scripts/dev.ps1                 # Tüm servisleri tek komutla başlatır
```

---

## 2. Veri Modeli Taslağı

Tüm zamanlar `timestamptz` (UTC); "gün" hesapları kullanıcının saat dilimine göre. Her tablo `user_id` ile sahiplenilir (çok kullanıcıya hazır).

### 2.1 task-api — Çekirdek (schema: `app`)
| Tablo | Ana alanlar | Not |
|---|---|---|
| `users` *(mevcut)* | — | değişmez |
| `user_settings` | timezone, **planning_time**, **review_time**, reminders_enabled, week_start | Planlama sabah mı akşam mı kullanıcıya kalır |
| `boards` | name, color, icon, position, **scope_description**, **weekly_time_budget_min**, **privacy** (`cloud_allowed`/`local_only`), **default_model_config_id?**, is_archived | scope_description: AI'a bu alanın sınırını söyler (gelen işleri doğru board'a koymak için) |
| `board_lists` | board_id, name, position, is_done_list | Trello kolonları |
| `tasks` → **kart** *(mevcut tablo genişler)* | + board_id, list_id, position (float), **parent_id** (alt görev), **series_id?**, description (markdown TEXT), start_at, due_date, estimated_minutes, completed_at, **blocked** (hesaplanan), **assigned_to** (user_id), is_archived, created_by (`user`/`ai`/`integration`), graph_x/graph_y | Mevcut entity/servis/cache/testler korunur. Migration mevcut task'ları "Genel" board'a taşır. Alt görevler de tam karttır (süre tutulur, takvime konur). Ana kartın ilerlemesi = alt kartlardan roll-up (tamamlanan sayı, tahmini/gerçek süre) |
| `card_dependencies` | card_id, depends_on_id, type (`blocks`) | **Kartlar arası ipler.** Döngü kontrolü (DAG). Board'lar arası bağlantıya izin var. Bağımlılıkları tamamlanmamış kart "blocked" |
| `card_notes` | card_id, content (md) | Kart içi not akışı |
| `checklist_items` | card_id, text, is_done, position | Küçük, süre tutulmayan adımlar için |
| `labels`, `card_labels` | board_id, name, color | |
| `series` | title, board_id, recurrence_rule? (RRULE, Faz 6) | Aynı işin tekrarlarını gruplar → "Koşu: 14. tamamlama" |
| `events` | board_id?, card_id?, title, start_at, end_at, all_day, location, notes, recurrence_rule?, created_by | **Kart = ne, etkinlik = ne zaman.** Kartı takvime koymak = karta bağlı zaman bloğu |
| `time_sessions` | card_id?, started_at, ended_at, duration_sec, note, source (`timer`/`manual`) | Kullanıcı başına tek aktif session (partial unique index). Duraklat = durdur + yeni session |
| `day_plans` | date (unique/user), status (`planned`/`reviewed`), mood, energy, reflection, ai_summary, planned_at, reviewed_at | Planlanan vs gerçekleşen |
| `day_plan_items` | day_plan_id, card_id?, event_id?, title_snapshot, was_planned, planned_start?, outcome (`done`/`partial`/`not_done`/`postponed`), reason, tracked_sec, estimated_min (snapshot) | Snapshot'lar geçmişi korur; plansız yapılan işler `was_planned=false` |
| `goals` | board_id?, title, why, target_date, status, root_card_id? | "Hayatımda yapmak istediklerim" — AI yönlendirmesinin dayanağı; büyük hedef kart ağacına bağlanabilir |

### 2.2 task-api — Geçmiş ve İstatistik (performans + AI'ın seni öğrenmesi)
| Tablo | Ana alanlar | Ne sağlar |
|---|---|---|
| `activity_log` | entity_type, entity_id, action (`created`,`moved`,`completed`,`reopened`,`postponed`,`rescheduled`,`estimate_changed`,`deleted`...), before/after (jsonb), actor (`user`/`ai`/`integration`), occurred_at | **Faz 1'den itibaren her değişiklik kaydedilir** (servis katmanında, tek noktadan). Silinen kartın geçmişi bile kaybolmaz |
| `card_stats` *(view / tablo)* | card_id, lead_time (oluşturma→tamamlama), total_tracked_sec, session_count, postpone_count, estimate_ratio, completion_index (series içinde kaçıncı) | Kart bazlı performans |
| `daily_stats` | date, board_id, planned_count, done_count, tracked_min, estimated_min, by_hour (jsonb: saat bazlı odaklanma) | Review gönderildiğinde/gece hesaplanır; istatistik sayfası ve AI için hazır özet |
| `analytics` endpoint'leri | — | Tamamlanma oranı (board/hafta), tahmin doğruluğu, erteleme kalıpları, en verimli saatler, seriler/streak, board zaman bütçesi dengesi, hedef ilerlemesi |

### 2.3 assistant-service (schema: `assistant`)
| Tablo | Ana alanlar | Not |
|---|---|---|
| `conversations` | title, summary | Uzun sohbetler özetlenir |
| `messages` | conversation_id, role, content, tool_calls (jsonb), provider, model, tokens_in/out | Provider-nötr format; hangi mesajın hangi modelle yanıtlandığı görülür |
| `user_facts` | category (`goal`,`routine`,`preference`,`health`,`relationship`,`work`,`other`), content, source (`ai_learned`/`user_entered`/`insight_confirmed`), confidence, last_confirmed_at, is_active | AI'ın seni tanıması. Profil ekranından görür/düzeltir/silersin |
| `ai_insights` | observation ("Salı günleri spor kartları %70 erteleniyor"), evidence (jsonb: hangi metrikler), status (`new`/`confirmed`/`rejected`) | Haftalık analizle üretilir; onayladığın insight fact'e dönüşür |
| `ai_actions` | conversation_id, tool_name, args, status (`proposed`/`approved`/`rejected`/`executed`/`failed`), **user_feedback** (ret nedeni) | Onay akışı + denetim kaydı + **öğrenme sinyali** (hangi önerileri kabul/ret ettiğin) |
| `ai_permissions` | action_type (`create_card`,`create_event`,`schedule_next_in_chain`,`add_note`,`remember_fact`...), mode (`ask`/`auto`/`never`) | Senin belirlediğin otomatiklik kuralları |
| `provider_configs` | provider (`ollama`/`openai`/`anthropic`/`openai_compatible`), base_url, model, api_key_encrypted, is_default, is_local, options | Kullanıcı başına kendi key'i (ürünleşmeye hazır) |

### 2.4 Entegrasyonlar (Faz 7, şimdiden genel yapı)
| Tablo | Ana alanlar |
|---|---|
| `integration_accounts` | provider (`trello`,`google`,`microsoft`...), tokens_encrypted, scopes, status |
| `external_links` | entity_type, entity_id, provider, external_id, etag, last_synced_at — her kayda kolon eklemek yerine genel bağlantı tablosu |

İçeri alınan işler bir **"Gelen Kutusu"** board'una düşer; AI board'ların `scope_description`'ına bakarak doğru board'a taşımayı önerir.

---

## 3. AI Entegrasyon Katmanı

### 3.1 Provider soyutlaması (modelden bağımsızlık)
```
LLMProvider (Protocol)
  chat(messages, tools, stream) -> ChatResult | AsyncIterator[ChatChunk]
  capabilities -> {tool_calling, max_context, is_local}

OpenAICompatibleProvider  → Ollama, LM Studio, OpenAI GPT (aynı protokol; base_url/key farkı)
AnthropicProvider         → Claude
ProviderRegistry          → provider_configs'ten provider üretir
ModelRouter               → hangi model? sırası: mesajda seçilen > board varsayılanı > kullanıcı varsayılanı
                            + gizlilik kontrolü (local_only veri + cloud model → engel/uyarı)
                            + fallback (local çökerse, izin verilmişse ikinci provider)
```
Uygulamanın geri kalanı yalnızca nötr tipleri (`Msg`, `ToolSpec`, `ToolCall`, `ChatChunk`) görür; model değiştirmek başka hiçbir kodu etkilemez. Kendi ince katmanımız (LiteLLM yerine): 2 adaptör yeterli, tool-calling normalizasyonu kontrolümüzde.

### 3.2 Agent döngüsü ve bağlam
1. `ContextBuilder` kısa bir sistem prompt'u kurar: persona + aktif `user_facts` + `goals` + bugünün özeti (plan, aktif session, blocked/unblocked zincirler) + **profildeki eksik kategoriler** (AI'ın seni tanımak için doğal şekilde soru sorması).
2. Model yanıtı stream edilir; tool çağrısı → çalıştır → sonucu geri ver (maks. N tur).
3. Geri kalan her şey ihtiyaç halinde tool'larla ve **hazır istatistik özetleriyle** çekilir → 8 GB VRAM'deki modelin küçük bağlamına sığar.
4. **Gizlilik filtresi**: aktif model cloud ise `local_only` board'lara ait veriler tool sonuçlarından çıkarılır.

### 3.3 Tool seti (assistant-service → task-api REST)
- **Okuma:** `list_boards`, `search_cards`, `get_card_tree`, `get_calendar`, `get_day_plan`, `get_stats_summary`, `get_estimate_accuracy`, `get_patterns` (erteleme, verimli saatler), `list_goals`
- **Yazma:** `create_card`, `update_card`, `move_card`, `create_event`, `schedule_card`, `create_day_plan`, `add_note`
- **Yapı kurma:** `decompose_card(card_id, parts)` (ör. 20 saatlik eğitim → 9 alt kart, süreler dağıtılmış), `link_cards(from, to)` (ip), `assign_next_in_chain` (sıradaki unblocked kartı bugüne/takvime al)
- **Hafıza:** `remember_fact`, `update_fact`, `forget_fact`, `upsert_goal`, `propose_insight`

### 3.4 İzin ve onay akışı
- Her yazma tool'u bir `action_type`'a sahip; `ai_permissions`'a bakılır:
  - `ask` → UI'da öneri kartı (Onayla / Düzenle / Reddet + isteğe bağlı neden). İlk seferde "Bundan sonra otomatik yapayım mı?" sorusu.
  - `auto` → direkt uygulanır, sohbette bilgilendirilir, geri alınabilir.
  - `never` → AI o işlemi önermez.
- AI kayıtları `created_by='ai'`; tüm işlemler `ai_actions`'ta.

### 3.5 AI'ın seni öğrenmesi (kullandıkça iyileşme)
- **Açık bilgi:** sohbette öğrendikleri → `user_facts` (onboarding tanışma sohbeti + eksik kategoriler için doğal sorular).
- **Davranış verisi:** activity_log, sessions, day_plans → `analytics` özetleri (tahmin sapması, erteleme kalıpları, verimli saatler, board dengesi).
- **Geri bildirim:** kabul/ret edilen öneriler ve ret nedenleri → planlama prompt'una "geçmişte şu tip planları reddettin" olarak girer.
- **Insight döngüsü:** haftalık değerlendirmede AI kalıpları `ai_insights` olarak çıkarır → sen onaylarsın → kalıcı fact olur. Böylece öğrenme şeffaf ve düzeltilebilir.
- **Gerçekçi planlama:** AI yeni plan yaparken kişisel tahmin katsayını uygular (ör. "tahminlerin ortalama %35 düşük → 2 saat dediğin iş 2,7 saat").

### 3.6 Bağlı kart zinciri örneği
"20 saatlik eğitim, 9 part" → AI `decompose_card` ile ana kart + 9 alt kart (~2,2 saat tahmin) oluşturur, `link_cards` ile sıralı ip kurar → yalnızca 1. part açık, diğerleri blocked. 1. part tamamlanınca `card.completed` → `card.unblocked` event'i → izin `auto` ise AI 2. part'ı müsait bir zaman bloğuna koyar; `ask` ise önerir; ya da sen grafik görünümden kendine atarsın.

---

## 4. Geliştirme Fazları

| Faz | İçerik | Faz sonunda çalışır durumda |
|---|---|---|
| ✅ **0 — Hazırlık** | `git init`; PROJECT_OVERVIEW §12'deki 6 bug; **Dapr'ın kaldırılması** (publisher → aio-pika, notification-service → `consumer.py`); `servicess/` temizliği; CORS; `user_settings`; genel `DomainEventPublisher`; `scripts/dev.ps1`; `apps/web` iskeleti (Vite + login + API client) | Tek komutla ayağa kalkan ortam, yeşil testler, frontend'den login |
| ✅ **1a — Board & Kartlar** | boards (privacy, scope, bütçe), board_lists, kart genişletmesi + migration, notes, checklist, labels; sıralama/taşıma; **activity_log (ilk günden)**; frontend: board listesi, kanban (dnd-kit), kart detay modalı | Trello benzeri günlük kullanım; geçmiş birikmeye başlar |
| ✅ **1b — Hiyerarşi & Bağlantılar** | parent_id alt kartlar, card_dependencies (DAG + döngü kontrolü), blocked hesaplama, `card.completed → card.unblocked` event'i, ilerleme roll-up; frontend: alt kart listesi, **React Flow grafik görünüm** (sürükleyerek ip bağlama) | Ana görev → alt görevler → sıralı zincirler |
| ✅ **2 — Takvim** ⟂ **3a — Zaman takibi** *(paralel)* | **2:** events CRUD, `GET /calendar?from&to` (etkinlik + tarihli kartlar, board renkleriyle), FullCalendar, kartı takvime sürükleme. **3a:** time_sessions, global timer widget, kart/ana kart toplam süre | Tüm board'lar tek takvimde; kronometre çalışıyor |
| ✅ **3b — Planlama, Değerlendirme & İstatistik** (hatırlatıcılar: bkz. §0 sapmalar) | day_plans/items; planlama ekranı (takvimden + vadeli kartlardan otomatik dolar), değerlendirme ekranı (done/partial/not_done/postponed + neden + mood/energy), "yarına taşı"; planning/review saati ayarı + **hatırlatıcılar** (APScheduler + Web Push); `card_stats`, `daily_stats`, analytics endpoint'leri; **istatistik sayfası** (Recharts) | Performansını ölçen istatistikler; AI için zengin geçmiş |
| ✅ **4 — AI Çekirdek** | **local model benchmark'ı (§8) ve model seçimi**; assistant-service; provider katmanı (OpenAICompatible → Ollama + GPT); ModelRouter + gizlilik filtresi; ContextBuilder; okuma tool'ları; SSE chat; chat paneli + **mesaj bazında model seçici** | Verilerini gören, yorumlayan sohbet asistanı (local model öncelikli) |
| 🟡 **5 — AI Aksiyonları & Hafıza** (5a ✅, 5b ✅ + tasarım yenilemesi, **5c ⏳**: AnthropicProvider + model ayarları) | yazma + yapı kurma tool'ları; `ai_permissions` + onay kartları + "otomatik yapayım mı?" akışı; user_facts, goals, profil ekranı; onboarding sohbeti; AnthropicProvider; Ayarlar: provider/model, şifreli key, board varsayılan modeli | AI plan yapıp kart/etkinlik/zincir oluşturuyor, seni hatırlıyor; Claude/GPT/local geçişi |
| ✅ **6 — Proaktif & Öğrenen Asistan** | review/plan event'i → AI gün özeti + plan önerisi; zincirde sıradakini otomatik atama; haftalık değerlendirme + ai_insights; kişisel tahmin katsayısı; tekrarlayan kart/etkinlik (series + RRULE); ops. pgvector semantik arama | Kullandıkça seni daha iyi tanıyan, hedeflerine yönlendiren asistan |
| ✅ **7 — Dış Entegrasyonlar** (7a–7d push edildi; Opus denetimi yapıldı, gerçek hesap denemesi kullanıcıda) | `IntegrationConnector` arayüzü (provider katmanıyla aynı fikir) + Gelen Kutusu board'u; sırasıyla **Trello** (tek seferlik import, API key+token), **Google Calendar** (Gmail kapsam dışı) ve **Microsoft (Outlook/To Do, Graph API — Samsung Reminder → To Do senkronu üzerinden)** OAuth ile | Dış kaynaklardaki güncel işler uygulamaya akıyor, AI doğru board'a dağıtıyor |

## 4.1 Faz 7 — Detay Plan

> Kullanıcı kararları (2026-11-08): Trello = **API key + token** ile tek seferlik import · Google = **sadece Calendar** (Gmail yok) · Microsoft To Do = **içeri al + tamamlamayı geri yaz**.

### Genel kararlar (tüm alt fazlar)
- **Entegrasyonlar task-api içinde** (`app/integrations/`): veriyi sahiplenen servis o, sahiplik/aktivite/tekrar/unblock yolları aynen çalışır. AI sınıflandırması (7d) assistant-service'te.
- **Zamanlayıcı yok, RabbitMQ yok:** task-api `lifespan`'ında bir `asyncio` döngüsü 15 dk'da bir aktif hesapları senkronlar + elle "Şimdi senkronla". Aynı kullanıcı/sağlayıcı için `asyncio.Lock`.
- **Token şifreleme:** task-api'ye `cryptography` eklenir; `app/core/crypto.py` = assistant-service `app/security.py`'nin kopyası (`TASK_API_SECRET_KEY` ya da `services/task-api/.secret_key`, `.gitignore`'a eklenir).
- **HTTP:** `httpx` dev'den ana bağımlılığa taşınır; her dış çağrı `timeout=20`. Testlerde gerçek ağ yok: `httpx.MockTransport`.
- **Kaynak etiketi:** entegrasyondan gelen kart/etkinlikte `created_by="integration"`, activity_log `actor="integration"`. Entegrasyonun yaptığı değişiklik geri yazmayı tetiklemez (döngü önlemi).
- **Gelen Kutusu:** `boards.system_kind` (`NULL`/`"inbox"`), `BoardService.get_or_create_inbox()` (`get_or_create_default` deseniyle; tek liste "Gelen", gizlilik varsayılanı `local_only`). Silinemez (409), yeniden adlandırılabilir.
- **Kullanıcının elle yapacakları** her alt fazın "Ön koşul" maddesinde; kod bunlar olmadan da testlerle bitirilebilir.

### Veri modeli (7a'da tek migration, sonraki fazlar sadece kullanır)
| Tablo / kolon | Alanlar |
|---|---|
| `integration_accounts` | id, user_id, provider (`trello`/`google`/`microsoft`), account_label, tokens_encrypted (Fernet, JSON: access/refresh/expires_at ya da key/token), scopes, status (`active`/`error`), settings (JSON: seçili takvim/liste id'leri, sync/delta token'ları), last_synced_at, last_error · unique(user_id, provider) |
| `external_links` | id, user_id, provider, entity_type (`board`/`list`/`card`/`event`/`note`/`checklist_item`), entity_id, external_id, external_parent_id (ör. To Do liste id'si), etag, url, **pending_push** (bool), push_error, last_synced_at · unique(user_id, provider, entity_type, external_id) · index(entity_type, entity_id) |
| `boards.system_kind` | nullable String(20) |

Ortak modül yapısı (`services/task-api/app/integrations/`): `base.py` (`SyncResult` dataclass: created/updated/removed/errors), `accounts.py` (hesap CRUD + şifreleme), `links.py` (external_links repo yardımcıları), `oauth.py` (7b'de: authorize URL, code→token, refresh, `state` = 10 dk'lık imzalı JWT içinde user_id+provider), `scheduler.py` (lifespan döngüsü), `trello.py`, `google_calendar.py`, `microsoft_todo.py`. API: `app/api/v1/integrations.py` (`/integrations/...`).

---

### Faz 7a — Altyapı + Trello tek seferlik import ✅ (commit `b8b46d1`; gerçek hesapla doğrulama bekliyor)
**Ön koşul (kullanıcı):** https://trello.com/power-ups/admin → Power-Up oluştur → API key. Token arayüzdeki "Token al" bağlantısından (`https://trello.com/1/authorize?expiration=never&scope=read&response_type=token&key=<KEY>&name=Ajanda`).

**Adımlar**
1. ✅ Migration + entity'ler + repo'lar (`IntegrationAccountEntity`, `ExternalLinkEntity`, `boards.system_kind`); UoW'ye ekle; `core/crypto.py`; `cryptography`, `httpx` bağımlılıkları; `.gitignore`.
2. ✅ `BoardService.get_or_create_inbox()`; inbox board silme → 409; `BoardResponse`'a `system_kind`.
3. ✅ Trello istemcisi (`trello.py`): `GET /1/members/me` (doğrulama), `GET /1/members/me/boards?filter=open`, board başına tek istek `GET /1/boards/{id}?lists=open&cards=open&card_checklists=all&labels=all&actions=commentCard&actions_limit=1000&card_attachments=true`.
4. ✅ Eşleme: board→board (ad, Trello rengi→en yakın palet rengi), list→list (`Done/Bitti/Tamamlandı/Tamamlanan` → `is_done_list`), kart→kart (name, desc, due, dueComplete→done, sıra `pos`'a göre, etiketler, ekler açıklamanın sonuna link listesi), checklist→checklist_items, yorum→card_notes (`"<yazar>, <tarih>: "` önekiyle). Arşivli liste/kart alınmaz.
5. ✅ **Idempotent:** her nesne external_links'e yazılır; tekrar import mevcutları atlar (güncellemez), yeni olanları ekler. Tek transaction/board.
6. ✅ API: `PUT /integrations/trello` {api_key, token} (doğrula → şifreli kaydet, yanıtta maskeli) · `GET /integrations` (tüm hesaplar, maskeli) · `DELETE /integrations/{provider}` · `GET /integrations/trello/boards` (zaten import edilenler işaretli) · `POST /integrations/trello/import` {board_ids} → board başına sayımlar.
7. ✅ Frontend: Ayarlar'a **"Bağlantılar"** bölümü (`components/IntegrationsSettings.tsx`, mevcut `Section`/`Row` desenleri): Trello satırı (key/token girişi, "Token al" linki, board seçim listesi, "İçe aktar", sonuç özeti, "Bağlantıyı kaldır"). Inbox board'u board listesinde ikonla, silme menüsü gizli.
8. ✅ Testler (task-api): eşleme birim testleri (örnek Trello JSON fixture'ı `tests/fixtures/trello_board.json`), idempotent tekrar import, sahiplik (başkasının hesabı/board'u), şifreli saklama (DB'de düz metin yok), inbox silinemez.

**Kabul:** örnek fixture'la import → board/list/kart/checklist/not sayıları doğru; ikinci import 0 yeni; arayüzden gerçek Trello board'u (kullanıcı key verdiyse) içeri alınır. — *Durum: fixture ile import/idempotent testleri geçti; gerçek Trello board'u ve arayüz görsel kontrolü kullanıcıda bekliyor.*

**Önerilen model:** **Sonnet** (tüm adımlar; desenler hazır: entity/repo/UoW/servis/`ApiResponse`). Adım 1'deki migration tek sahip olarak backend-agent kuralına uyar; ayrı agent başlatmaya gerek yok, tek oturum sırayla yapar.

---

### Faz 7b — OAuth altyapısı + Google Calendar (tek yönlü) ✅ (commit `b8b46d1`; gerçek hesapla doğrulama bekliyor)
**Ön koşul (kullanıcı):** Google Cloud Console → proje → Calendar API'yi aç → OAuth izin ekranı (External, kendi hesabını test kullanıcısı ekle; **"In production"a al** — test modunda refresh token 7 günde düşer; doğrulanmamış uygulama uyarısı bir kez görülür, kişisel kullanımda sorun değil) → OAuth istemcisi "Web application", yönlendirme `http://localhost:8000/api/v1/integrations/google/callback`. `services/task-api/.env`: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.

**Adımlar**
1. `oauth.py` (sağlayıcıdan bağımsız): `POST /integrations/{provider}/connect` → `{authorize_url}` (state JWT) · `GET /integrations/{provider}/callback?code&state` (auth header yok, state doğrulanır) → token kaydı → `http://localhost:5173/settings?connected=<provider>#baglantilar`'a 302. `ensure_fresh_token()` (bitişe <60 sn → refresh; `invalid_grant` → status `error`, last_error "Yeniden bağlan"). Ayarlar `config.py`'ye (`google_client_id`, `microsoft_client_id`, … `web_base_url`).
2. Kapsam: `https://www.googleapis.com/auth/calendar.readonly` (+ `openid email` hesap etiketi için), `access_type=offline&prompt=consent`.
3. `GET /integrations/google/calendars` (calendarList) · `PUT /integrations/google/settings` {calendar_ids, board_id?}.
4. Senkron (`google_calendar.py`): takvim başına `events.list(singleEvents=true)`; ilk sefer `timeMin=şimdi-30g, timeMax=şimdi+180g`, sonra `syncToken` (settings'te); 410 → tam yeniden senkron. Eşleme: summary→title, start.date→all_day, dateTime→UTC, location, description→notes, htmlLink→external_links.url; `status=cancelled` → yerel etkinlik silinir; etag aynıysa atla. Tekrarlayan Google etkinlikleri pencere içinde örnek örnek satır olur (yerel RRULE kullanılmaz).
5. Google'dan gelen etkinlik **salt okunur**: `EventResponse.external = {provider, url}`; `EventService.update/delete` → 409 "Google Takvim'de düzenleyin". Takvimde sürükleme kapalı, pencerede "Google'da aç" bağlantısı.
6. `scheduler.py`: lifespan'da 15 dk döngüsü (ilk tur açılıştan 30 sn sonra), `POST /integrations/{provider}/sync` elle.
7. Frontend: Bağlantılar'da Google satırı (Bağlan → yönlendirme, takvim çoklu seçimi, hedef board seçimi, son senkron zamanı/hata, "Şimdi senkronla", "Bağlantıyı kes"); `EventDialog` salt okunur mod + Google ikonu; `CalendarPage` `editable:false` (external).
8. Testler: state sahteciliği reddi, token yenileme, syncToken akışı, 410 yeniden senkron, iptal edilen etkinliğin silinmesi, salt okunur 409, MockTransport ile.

**Kabul:** testler yeşil; (kimlik bilgileri verildiyse) gerçek hesapla bağlan → seçili takvimin etkinlikleri `/calendar`'da görünür, Google'da silinen etkinlik sonraki senkronda kaybolur.

**Önerilen model:** **Sonnet** (adım 2–8). **Adım 1 (OAuth/state/refresh)** yine Sonnet ile yazılır; gerçek hesapla bağlanırken çözülemeyen bir hata çıkarsa (redirect_uri_mismatch dışı, token/refresh döngüsü) **o noktada yeni bir Opus oturumu** sadece hata ayıklama için açılır — baştan Opus kullanılmaz.

---

### Faz 7c — Microsoft To Do (Samsung Reminder) iki yönlü tamamlama ✅ (commit `b8b46d1`; gerçek hesapla doğrulama bekliyor)
**Ön koşul (kullanıcı):** Telefonda Samsung Reminder → Ayarlar → "Microsoft To Do ile senkronize et" açık. Azure portal → App registrations → "Personal Microsoft accounts only" → platform **Web**, yönlendirme `http://localhost:8000/api/v1/integrations/microsoft/callback` → client secret. `.env`: `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`. Kapsam: `offline_access User.Read Tasks.ReadWrite`, uç nokta `login.microsoftonline.com/consumers/oauth2/v2.0`.

**Adımlar**
1. 7b'deki `oauth.py`'ye Microsoft yapılandırması (yeni kod değil, sağlayıcı tanımı).
2. `GET /integrations/microsoft/lists` (`/me/todo/lists`) · `PUT /integrations/microsoft/settings` {list_ids} (varsayılan: hepsi).
3. Senkron (`microsoft_todo.py`): liste başına `/me/todo/lists/{id}/tasks/delta` (deltaLink settings'te). Yeni görev → **Gelen Kutusu** board'unda kart (title, body.content→description, dueDateTime/reminderDateTime → due_date (kullanıcı saat dilimiyle), importance high→priority high); güncel görev → başlık/açıklama/tarih güncellenir; `status=completed` → kart `CardService` yoluyla tamamlanır (unblock/seri mantığı çalışsın, actor=integration); `@removed` → kart arşivlenir (silinmez).
4. **Geri yazma (outbox):** `CardService._apply_status` içinde, kartın microsoft external_link'i varsa ve actor `integration` değilse aynı transaction'da `pending_push=True`. Commit sonrası arka planda hemen + her senkron turunda: `PATCH /me/todo/lists/{listId}/tasks/{taskId}` {status: completed | notStarted}. Başarı → `pending_push=False`; hata → `push_error`, sonraki turda tekrar.
5. Çatışma kuralı: aynı turda iki taraf değiştiyse önce bekleyen push'lar gönderilir, sonra delta çekilir (yerel tamamlama kaybolmaz).
6. Frontend: Bağlantılar'da Microsoft satırı (Bağlan, liste seçimi, son senkron, bekleyen/hatalı geri yazma sayısı); kart penceresinde "Microsoft To Do'dan" rozeti.
7. Testler: delta akışı, tamamlanan uzak görev → kart done + `card.unblocked` yolu, yerel tamamlama → pending_push → PATCH, integration actor'u geri yazmaz (döngü yok), push hatası tekrar denenir, @removed → arşiv.

**Kabul:** testler yeşil; (kimlik bilgileri verildiyse) telefonda eklenen hatırlatıcı ≤15 dk içinde Gelen Kutusu'nda; uygulamada bitirilince To Do'da tamamlanmış görünür.

**Önerilen model:** **Sonnet**. Adım 4–5 (outbox + çatışma) bu fazın en riskli kısmı; plan net olduğu için Sonnet yeterli, gerçek testte döngü/çift tamamlama görülürse ayrı Opus hata ayıklama oturumu.

---

### Faz 7d — Asistan Gelen Kutusu'nu dağıtır ✅ (commit `b21b062`; gerçek modelle doğrulama bekliyor)
**Adımlar (assistant-service)**
1. `app/agent/inbox_triage.py` (`day_review.py` deseni): adaylar = Gelen Kutusu'ndaki açık kartlar, son 14 günde bekleyen/reddedilmiş bir `triage_inbox` önerisinde geçmeyenler, en fazla 20. Board listesi: ad + `scope_description` + listeler; bulut modelde `local_only` board'lar ve Gelen Kutusu içeriği gönderilmez (inbox varsayılan `local_only` olduğundan pratikte local model).
2. Model **sadece seçer** (JSON: `[{card_id, board_id, list_id?, reason}]`); kod doğrular (bilinmeyen id, inbox'ın kendisi → atılır; list yoksa board'un ilk listesi). Emin olmadığı kart önerilmez.
3. Yeni işlem türü `triage_inbox` (izinler: ask/auto/never; Ayarlar → Asistan izinleri'nde etiketiyle) → tek onay kartı, madde madde (kullanıcı tek tek çıkarabilir). Yürütücü `write_tools.execute` içinde: her madde için task-api `POST /cards/{id}/move` (`X-Actor: ai`).
4. `ai_jobs` `kind=inbox_triage`; `POST /assistant/inbox-triage`; model = arka plan modeli (`background_model_id`, yoksa gemma4:26b).
5. Tetik: frontend, Gelen Kutusu'nda dağıtılmamış kart varsa uygulama açılışında (günde en fazla bir kez, localStorage) ve Gelen Kutusu board sayfasındaki **"Asistan dağıtsın"** düğmesiyle.
6. Frontend: Gelen Kutusu board sayfasında üst şerit (iş durumu yoklama — `DayDigest` deseni, onay kartı `ActionCard` ile).
7. Testler (assistant-service, sahte provider): aday seçimi, geçersiz id eleme, gizlilik filtresi, reddedilen önerinin 14 gün tekrar gelmemesi, izin modları.

**Kabul:** testler yeşil; gerçek gemma4:26b ile 5 örnek inbox kartı → anlamlı board önerileri + gerekçe; onay → kartlar taşınır.

**Önerilen model:** **Sonnet** (desen birebir `day_review`/`insights`'ta var). İstem ayarı gerçek modelle zayıf çıkarsa önce örnekli istem eklenir (Sonnet), Opus'a gerek yok.

---

### Sıra, oturumlar ve usage verimliliği
| # | Oturum | Model | Kapsam | Not |
|---|---|---|---|---|
| 1 | ✅ 7a kodlama | Sonnet | Altyapı + Trello | Migration burada, tek seferde |
| 2 | ✅ 7a push | Haiku | commit + push | 7a–7c tek commit `b8b46d1` (ortak dosyalar; bkz. §0 sapmalar) |
| 3 | ✅ 7b kodlama | Sonnet | OAuth + Google Calendar | 7a'ya bağımlı |
| 4 | ✅ 7a+7b+7c push | Haiku | commit + push | `b8b46d1` |
| 5 | ✅ 7c kodlama | Sonnet | Microsoft To Do | 7b'nin `oauth.py`'sine bağımlı |
| 6 | ✅ 7d kodlama | Sonnet | Inbox triage | 7c'den **bağımsız** (Gelen Kutusu 7a'da) → istenirse 7b'den sonra 7c ile **ayrı oturumda paralel** (farklı servis, çakışan dosya yok; tek ortak dosya `SettingsPage.tsx` izin etiketleri → 7d bunu en sona bıraksın) |
| 7 | ✅ 7a–7d push | Haiku | commit + push | 7d tek commit `b21b062` (`inbox_triage.py`, `jobs.py`, `actions.py`, `write_tools.py`, test, web `InboxTriage.tsx`/`ActionCard.tsx`/`BoardPage.tsx`/`Layout.tsx`/`assistant.ts`); tüm testler + web build geçti (task-api 247, assistant 120) |
| 8 | ✅ Faz 7 denetimi | Opus | plan ↔ kod karşılaştırması | Yapıldı; OAuth kurulum sihirbazı eklendi (§0 "Faz 7 denetimi") — commit/push bekliyor |
| (gerekirse) | OAuth/senkron hata ayıklama | Opus | yalnızca çözülemeyen gerçek-hesap hatası | |

Verimlilik kuralları (kodlama oturumlarına):
- Oturum başında yalnızca bu dosyanın **§0 (Hızlı başlangıç) + §4.1 ilgili alt faz** bölümünü oku; diğer bölümleri okuma.
- Subagent/paralel agent açma (her biri bağlamı baştan kurar); tek oturum sırayla yapsın. reviewer agent yerine oturum sonunda testler + 8. satırdaki tek Opus denetimi.
- Test çalıştırırken önce yeni test dosyasını (`uv run pytest -q tests/.../test_integrations_*.py`), en sonda bir kez tüm paketi çalıştır; `npm run build` faz sonunda bir kez.
- Gerçek hesapla deneme, kullanıcı kimlik bilgilerini verdiyse ve sadece bir kez (kabul ölçütü); vermediyse MockTransport testleriyle bitir, §0'a "gerçek hesapla doğrulanmadı" yaz.
- Faz sonunda §0 tablosunu ve "Faz 7x'te yapılanlar" kısa ayrıntısını güncelle (sapmalar tablosuna ekle).
- Oturum uzarsa (≈ büyük bir alt faz bitip diğeri başlayacaksa) yeni oturuma geç.

### Doğrulama (her alt faz)
- `services/task-api`: `uv run pytest -q` (247 + yeni) · `uv run ruff check app tests`
- `services/assistant-service` (7d): `uv run pytest -q` (96 + yeni)
- `apps/web`: `npm run build`
- Önizleme (`.claude/launch.json`: task-api 8000, assistant 8100, web 5173): Ayarlar → Bağlantılar akışı tarayıcıda gezilir.

---

---

## 5. Agent Yapısı (geliştirme sürecinde)

`.claude/agents/` altına tanımlanacak subagent'lar:

| Agent | Sorumluluk | Devreye girdiği faz | Sahip olduğu alan |
|---|---|---|---|
| **backend-agent** | task-api domain modülleri, Alembic migration'ları, activity_log, analytics, notification-service scheduler, testler (mevcut fixture zinciri + sahiplik testleri) | 0–3, 5 (AI'ın ihtiyaç duyduğu endpoint'ler), 6, 7 | `services/task-api/**`, `services/notification-service/**` — **migration'ların tek sahibi** |
| **frontend-agent** | `apps/web`: sayfalar, kanban, grafik görünüm, takvim, timer, istatistik, chat, ayarlar; OpenAPI'den tip üretimi | 0 (iskelet), 1–7 | `apps/web/**` |
| **ai-agent** | assistant-service: provider adaptörleri, ModelRouter, agent loop, tools, ContextBuilder, izinler, hafıza/insight, prompt'lar, provider kontrat testleri (mock'lu) | 2–3 (provider katmanı, paralel), 4–6 | `services/assistant-service/**` |
| **reviewer** (salt-okunur) | Her faz sonunda testleri çalıştırır; sahiplik/yetki, gizlilik filtresi ve sözleşme uyumunu gözden geçirir | Her faz sonu | — (yazmaz) |

**Bağımlılıklar ve paralellik**
```
Faz 0:    backend-agent (bug fix, Dapr kaldırma) → frontend-agent (iskelet)          [sıralı, küçük]
Faz 1a/b: backend-agent: şema + OpenAPI ──► frontend-agent: kanban / grafik UI       [sözleşme sonrası paralel]
Faz 2/3a: backend-agent (events → sessions, sıralı: aynı migration zinciri)
          frontend-agent (takvim + timer UI)                      ┐ paralel
          ai-agent (provider katmanı + ModelRouter, veriye bağımsız) ┘
Faz 3b:   backend-agent (plan/review, stats, scheduler) ──► frontend-agent (ekranlar, istatistik)
Faz 4–5:  ai-agent (tools: task-api endpoint'lerine bağımlı) ∥ frontend-agent (chat, onay kartları, profil, ayarlar)
          backend-agent yalnızca eksik endpoint'ler için
Faz 6:    ai-agent (proaktif/insight) ∥ backend-agent (series/RRULE) ∥ frontend-agent
Faz 7:    backend-agent (connector'lar) ∥ frontend-agent (entegrasyon ayarları, gelen kutusu)
```
**Bölünmeyenler:** backend tek agent (Alembic head çakışması ve aynı dosyalara iki yazar olmaması için); Faz 0 bölünmez.
**Sözleşme kuralı:** Her fazda önce backend Pydantic şemaları + OpenAPI yayınlanır; frontend ve ai-agent buna göre çalışır (gerekirse mock).
**Ön koşul:** Paralel agent'lar worktree kullanacağı için git zorunlu (Faz 0).

---

## 6. Kritik Dosyalar / Yeniden Kullanılacaklar

- `services/task-api/app/services/task.py` — kart servisi bunun üzerine genişler (cache invalidation + event deseni korunur; activity_log yazımı buraya eklenir)
- `services/task-api/app/db/repositories/specifications.py` — yeni filtreler (`BoardSpecification`, `DateRangeSpecification`, `ParentSpecification`) aynı desende
- `services/task-api/app/db/unit_of_work.py` — yeni repository'ler eklenir
- `services/task-api/app/core/events.py` + `core/messaging.py` — Dapr yerine aio-pika ile genel domain event publisher
- `services/task-api/app/core/dapr_client.py`, `dapr_pubsub.py`, `infrastructure/dapr/` — kaldırılır
- `services/notification-service/app/consumer.py` — ana consumer olur (DLQ + retry hazır)
- `services/task-api/app/core/resilience.py` — `ai_feature`, `external_api_bulkhead`, `CircuitBreaker` LLM/entegrasyon çağrılarında
- `services/task-api/app/core/cache_keys.py` — yeni modüller için aynı `{entity}:user:{id}:*` deseni
- `services/task-api/app/models/common.py` — `ApiResponse[T]` tüm yeni endpoint'lerde
- `services/task-api/tests/conftest.py` — fixture zinciri tüm yeni integration testlerde

## 7. Doğrulama

- Her faz: `uv run pytest --cov=app tests/` (task-api, assistant-service), `ruff`, `mypy`; her yeni modül için sahiplik testleri.
- Faz 1–3: tarayıcıda uçtan uca — board oluştur → ana kart + alt kartlar + ip bağla → 1. alt kartı bitir, 2.'sinin açıldığını gör → takvime sürükle → timer başlat/durdur → hatırlatıcı gelsin → değerlendirmeyi doldur → istatistik sayfasında gör.
- Faz 4–5: provider kontrat testleri (aynı senaryo üç adaptörle mock'lu); gerçek Ollama ile "yarın için plan yap" → öneri kartı → onay → takvimde etkinlik; "bu eğitimi 9 parçaya böl" → zincir oluşur; local_only board + cloud model → verinin gitmediğini test et; mesajda modeli değiştirip aynı senaryoyu tekrarla.
- Faz 6: değerlendirme → event → ertesi gün plan önerisi; haftalık insight üretimi.
- Faz 7: alt faz kabul ölçütleri §4.1'de (Trello import, Google takvim senkronu, To Do iki yönlü tamamlama, Gelen Kutusu dağıtımı).

---

## 8. Son Kararlar (açık soru kalmadı)

1. **Samsung Reminders (Faz 7):** Samsung Reminder → Microsoft To Do senkronizasyonu açılacak; uygulama Microsoft Graph API üzerinden To Do görevlerini çeker.
2. **Trello (Faz 7):** Tek seferlik içeri aktarma (board → board, list → list, kart + açıklama + checklist + yorumlar → kart + not). İki yönlü senkron yok; Trello zamanla bırakılacak. Yöntem: API key + token (kullanıcı kararı 2026-11-08).
3. **Local model seçimi (Faz 4 başı):** Elindeki modeller arasından **benchmark script'iyle** seçim yapılır.

### Local model değerlendirme planı
Elindeki modeller: `gemma4:26b`, `qwen3.8:27b`, `deepseek-r1:32b`, `qwen2.5-coder:32b`, `qwen3.5:4b`.

**Ön beklenti (testle doğrulanacak):**
- 8 GB VRAM'e yalnızca **`qwen3.5:4b`** tamamen sığar → hızlı. 26–32B modellerin büyük kısmı RAM'e taşar → doğru çalışır ama yavaş (saniyede birkaç token mertebesi bekliyorum; test ölçecek).
- `deepseek-r1:32b` bir akıl yürütme (reasoning) modeli: uzun "düşünme" çıktısı ve tool-calling davranışı ajan döngüsü için sorunlu olabilir → muhtemelen eleme.
- `qwen2.5-coder:32b` kod odaklı → sohbet/planlama asistanı için uygun değil, test listesinden çıkarılabilir.
- Asıl adaylar: **`qwen3.5:4b`** (hız) vs **`gemma4:26b`** / **`qwen3.8:27b`** (kalite).

**Benchmark (`services/assistant-service/scripts/benchmark_models.py`):** her model için aynı Türkçe senaryolar —
1. Serbest sohbet (Türkçe akıcılık, kişiliğe uygunluk)
2. Tek tool çağrısı ("yarın 18:00'e koşu ekle" → doğru `create_event` argümanları)
3. Çok adımlı tool zinciri ("bu eğitimi 9 parçaya böl ve sırayla bağla")
4. Geçmiş özetinden plan çıkarma (örnek analytics JSON'u verilerek)

Ölçülenler: token/sn, ilk token süresi, geçerli tool-call oranı (JSON şemaya uyum), görev başarısı (otomatik kontroller + senin 1–5 puanın), VRAM/RAM kullanımı. Sonuç tablo olarak raporlanır, sen seçersin.

**Muhtemel sonuç → görev bazlı yönlendirme (ModelRouter'a eklenir):**
| Görev | Model sınıfı | Neden |
|---|---|---|
| Anlık sohbet, hızlı ekleme/düzenleme | Hızlı local (ör. 4B) | Gecikme önemli |
| Gece/arka plan işleri: değerlendirme sonrası ertesi gün planı, haftalık insight, Trello import sınıflandırma | Büyük local (26–27B) | Arka planda çalıştığı için yavaşlık sorun değil, kalite önemli |
| Zor sorular ("spor programımı detaylı kur") | Seçtiğin cloud model (Claude/GPT) | Mesaj bazında seçim, gizlilik kurallarına tabi |

Bu yüzden `provider_configs`'e ek olarak `model_routes` (task_type → provider_config) ayarı eklenir: `chat`, `background_planning`, `insight`, `classification`.
