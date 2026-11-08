# AI Destekli Kişisel Yaşam & Görev Yönetimi — Genel Çerçeve Planı (v2)

> ## 📍 İlerleme Durumu — 2026-11-08 (yeni oturum buradan devam eder)
>
> **Branch:** `feature/ai-life-manager` · Faz 0–6b tamam. **Sıradaki: Faz 6c** (series + RRULE), sonra Faz 7.

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
| 6c — Tekrarlayan işler | ⏳ Bekliyor | — | `series` + RRULE (kart ve etkinlik), "Koşu: 14. tamamlama" |
| 7 — Dış Entegrasyonlar | ⏳ Bekliyor | — | Trello (tek seferlik import), Google, Microsoft To Do (Samsung Reminder üzerinden) |

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

### Plandan bilinçli sapmalar
| Plan | Yapılan | Neden |
|---|---|---|
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
| `propose_insight` sohbet aracı | Sadece haftalık analiz gözlem üretir | Model kalıp uydurmasın: gözlemler veriden hesaplanır |
| Bulut modellerle gerçek test | Sadece birim/entegrasyon testleri (sahte istemci); gerçek API'ye istek atılmadı | Kullanıcı kararı: API maliyeti |

### Bilinen sorunlar / dikkat
- **qwen3.5:4b** hızlı ve araç çağrılarında doğru ama çok adımlı işte zayıf: onay beklerken "ekledim" diyebiliyor, anlam hataları yapıyor (koşu etkinliğini "ayakkabı al" kartına bağladı). Onay kartları gerçeği gösteriyor; Faz 6'da görev bazlı yönlendirme (planlama → gemma4:26b) bunun için.
- Sohbet geçmişinde model önceki "not aldım" kalıbını taklit edebiliyor.
- Lokal test DB'sinde test verileri var (Spor/Date/Eğitimler board'ları, "Koşu ayakkabısı al" AI kartı, bekleyen bir hafıza önerisi).
- task-api'de eski dosyalarda birkaç lint uyarısı (Faz 0 öncesinden).

### Yeni oturum için hızlı başlangıç
- **Ortam:** Windows, Docker YOK (SQLite), uv: `C:\Users\alium\AppData\Roaming\Python\Python313\Scripts\uv.exe` (PATH'te değil). Ollama kurulu (qwen3.5:4b, gemma4:26b, qwen3.8:27b; deepseek-r1 ve coder listede gizli). GPU: RTX 4060 Laptop 8 GB.
- **Çalıştırma:** `./scripts/dev.ps1` ya da önizleme (`task api project/.claude/launch.json`: task-api 8000, assistant 8100, web 5173).
- **Testler:** `services/task-api`: `uv run pytest -q` (146) · `services/assistant-service`: `uv run pytest -q` (77) · `apps/web`: `npm run build`.
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
| Entegrasyonlar | Önce kendi içinde çalışsın; Faz 7'de Trello (tek seferlik import), Google (Calendar/Gmail), Outlook/Microsoft To Do (Samsung Reminders buradan) |
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
| ⏳ **6 — Proaktif & Öğrenen Asistan** | review/plan event'i → AI gün özeti + plan önerisi; zincirde sıradakini otomatik atama; haftalık değerlendirme + ai_insights; kişisel tahmin katsayısı; tekrarlayan kart/etkinlik (series + RRULE); ops. pgvector semantik arama | Kullandıkça seni daha iyi tanıyan, hedeflerine yönlendiren asistan |
| ⏳ **7 — Dış Entegrasyonlar** | `IntegrationConnector` arayüzü (provider katmanıyla aynı fikir) + Gelen Kutusu board'u; sırasıyla **Trello** (tek seferlik import, API key+token), **Google Calendar/Gmail** ve **Microsoft (Outlook/To Do, Graph API — Samsung Reminder → To Do senkronu üzerinden)** OAuth ile | Dış kaynaklardaki güncel işler uygulamaya akıyor, AI doğru board'a dağıtıyor |

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
- Faz 7: Trello'dan import → Gelen Kutusu → AI'ın board önerisi.

---

## 8. Son Kararlar (açık soru kalmadı)

1. **Samsung Reminders (Faz 7):** Samsung Reminder → Microsoft To Do senkronizasyonu açılacak; uygulama Microsoft Graph API üzerinden To Do görevlerini çeker.
2. **Trello (Faz 7):** Tek seferlik içeri aktarma (board → board, list → list, kart + açıklama + checklist + yorumlar → kart + not). İki yönlü senkron yok; Trello zamanla bırakılacak.
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
