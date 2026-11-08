# Analiz Dokümanı — Faz 8 İstekleri (2026-11-08)

> **Bu dosya ne?** Kullanıcının notlarındaki yeni isteklerin kod tabanı üzerinden yapılmış araştırma/analizi. Plan modunda Opus'a verilecek; Opus bundan **genel planı + her fazın detay planını** (CLAUDE.md kuralı: faz başına ayrı dosya, "Önerilen model" bölümü, yeni oturumda geçmişsiz uygulanabilir) çıkaracak.
> **Onaydan sonra:** bu dosya repoya `Task-Management-Master-Project/analiz-faz8.md` olarak kopyalanır (ana plan `g-rev-yapay-zek-dreamy-kahan.md`'nin yanına).
> **Ön koşul:** Faz 0–7 tamam, branch `feature/ai-life-manager`. Ana planın "0. İlerleme Durumu" bölümü ortam/test komutları için geçerli (uv yolu, Docker yok, SQLite, 8000/8100/5173, "Ajanda - Durdur → Ajanda" migration kuralı).

---

## Context

Kullanıcı uygulamayı gerçekten kullanmaya başladı; notlarından çıkan istekler:

1. **Asistan etiket ekleyebilsin.**
2. **Asistan kart detaylarına müdahale edebilsin** — "kartın checklist'ine şunu ekle" gibi.
3. **Teams entegrasyonu:** toplantılarını haftalık olarak çekip takvime yerleştirebilsin.
4. **Not alma (Trello gibi):** ek belge koyma, kod parçacığı ekleme, nota **çift tıklayınca düzenleme**.
5. **Sesli konuşma desteği.**
6. **Kart sürükle-bırak animasyonları** (smooth geçiş).
7. **Arka plan renk seçenekleri ve dark mode.**

### Kullanıcıdan alınan netleştirmeler (bu analiz sırasında)
| Soru | Cevap |
|---|---|
| Teams hangi hesapta? | **Kişisel Microsoft hesabı** (outlook.com/hotmail) → mevcut `consumers` OAuth altyapısı yeterli, kurumsal yönetici onayı sorunu yok |
| Sesli destek kapsamı | **Sadece konuş → yazıya (dikte).** Asistanın cevabı yazılı kalır, sesli okuma (TTS) yok |
| Ses tanıma motoru | **Tarayıcı Web Speech API** (kurulum yok; ses Chrome'da Google'a, Edge'de Microsoft'a gider) |

---

## 1. Mevcut durum — ilgili kod bulguları

### 1.1 Asistan yazma araçları (`services/assistant-service/app/tools/write_tools.py`)
- `ACTION_TYPES` (satır 44): `create_card`, `update_card`, `add_note`, `create_event`, `split_card`, `link_cards`, `plan_day`, `schedule_day`, `triage_inbox` + silme ve hafıza türleri.
- `WRITE_SPECS` (satır 66–180): araç JSON şemaları. **Etiket ve checklist için hiçbir araç yok.** `create_card`/`update_card` etiket ve checklist almıyor.
- Desen: `prepare(name, args)` → `_prepare_<name>()` doğrular, id'leri çözer, Türkçe özet üretir (`PreparedAction(action_type, args, summary)`); yürütücü (`_execute_*` ya da genel yol) task-api REST'ini `X-Actor: ai` ile çağırır. Yardımcılar: `_card()` (gizlilik kontrollü), `_board()`, `_find_list()` (ada göre, casefold), `_clip()`, `_int()`.
- İzin: `ai_permissions` (ask/auto/never, varsayılan ask). Ayarlar → Asistan izinleri etiketleri **backend'den** geliyor (7d'de `SettingsPage.tsx` değişmeden yeni tür göründü) → yeni işlem türleri UI değişikliği gerektirmez.
- Okuma araçları (`app/tools/read_tools.py`): `list_boards`, `get_board`, `search_cards`, `get_card`, `get_calendar`, `get_day_plan`, `get_stats_summary`, `list_goals`. **Kontrol edilmeli:** `get_card` çıktısı checklist maddelerini **id'leriyle** ve etiketleri **adlarıyla** veriyor mu? Vermiyorsa genişletilmeli (model madde işaretlemek/silmek için id'ye ihtiyaç duyar).
- Bilinen model zaafı (ana plan "Bilinen sorunlar"): local model "kart oluştur → id'siyle başka işlem" zincirini yapamıyor (kart onaya kadar yok). **Sonuç:** `create_card`'a doğrudan `labels` ve `checklist` parametreleri eklemek zincir sorununu ortadan kaldırır.

### 1.2 task-api kart içeriği
- Entity'ler `app/db/entities/card_content.py`: `CardNoteEntity` (`content` Text, markdown; `TimestampMixin` → `created_at/updated_at`), `ChecklistItemEntity` (`text` 500, `is_done`, `position` float), `CardDependencyEntity`.
- Etiketler `app/db/entities/board.py`: `LabelEntity` (board'a ait, `color`), `CardLabelEntity` (bağlantı). Board'un `color` alanı var, **arka plan alanı yok**.
- Uçlar (`app/api/v1/cards.py`, `boards.py`): `POST /cards/{id}/notes`, **`PATCH /notes/{id}` zaten var** (not düzenleme backend'i hazır), `DELETE /notes/{id}`; `POST /cards/{id}/checklist` (tek madde), `PATCH|DELETE /checklist/{id}`; `POST /boards/{id}/labels`, `PATCH|DELETE /labels/{id}`; kart etiketleri `PATCH /cards/{id}` gövdesinde **`label_ids` tam liste** (`CardService.update`, `services/card.py:330–351`, `_validate_labels` etiketin kartın board'una ait olmasını şart koşar).
- `NoteCreate/NoteUpdate.content` max 20000; checklist `text` max 500.
- Board silme (`db/repositories/board.py:83+`) kart içeriklerini **elle** siliyor (SQLite'ta FK kapalı) → yeni ek tablosu da buraya eklenmeli.
- Seri kart kopyalama (`services/card.py:470+`) etiket + checklist kopyalıyor; ekler kopyalanmamalı (karar Opus'ta, öneri: kopyalanmaz).

### 1.3 Frontend kart penceresi (`apps/web/src/components/CardModal.tsx`)
- Açıklama: tıkla → textarea, `react-markdown` ile gösterim (satır ~200–217).
- Notlar (satır ~301–319): yalnızca **ekle** formu (Ctrl+Enter) ve **Sil**; **düzenleme yok**. Gösterim `<Markdown>{n.content}</Markdown>`; `remark-gfm` yok (tablo/görev listesi yok), **kod vurgulama yok**, kopyala düğmesi yok.
- Checklist ekle/işaretle/sil var; etiketler künyede tıkla-aç/kapa (`toggleLabel`).
- `package.json`: `react-markdown ^10.1.0` var; `remark-gfm`, vurgulayıcı, dosya yükleme bileşeni yok.

### 1.4 Microsoft entegrasyonu (`services/task-api/app/integrations/`)
- `oauth.py:93–95`: `login.microsoftonline.com/consumers/...`, kapsam `openid email offline_access User.Read Tasks.ReadWrite`. **`Calendars.Read` yok.** Hesap kaydında verilen `scope` saklanıyor (satır 406) → eksik kapsam tespit edilebilir.
- `microsoft_todo.py`: `GraphClient` (httpx, `HTTP_TRANSPORT` ile sahte ağ testleri) yeniden kullanılabilir.
- `google_calendar.py`: salt okunur dış etkinlik deseni hazır — `external_id`, etag atlama, iptal → silme, pencere dışı silme, board taşıma, bağlantı kesilince silme, `EventService.update/delete` → 409 `EVENT_READ_ONLY`, `created_by="integration"`, activity'ye yazılmaz. Teams senkronu **bu deseni birebir kopyalamalı** (ideal: ortak "dış salt okunur etkinlik upsert" yardımcısına çıkarılması — Opus karar versin).
- `scheduler.py`: 15 dk'lık tur (Google → Microsoft To Do); takvim adımı buraya eklenir.
- Frontend: `IntegrationsSettings.tsx` (`OAuthRow`), `OAuthSetup.tsx` (Azure sihirbazı — API izinlerine `Calendars.Read` adımı eklenmeli), `EventDialog.tsx` (dış etkinlik salt okunur görünüm + "…'te aç" bağlantısı).

### 1.5 Sürükle-bırak (`apps/web/src/pages/BoardPage.tsx`, `components/KanbanList.tsx`, `api/boards.ts`)
- dnd-kit: `closestCorners`, `PointerSensor (distance 5)`, `DragOverlay` **varsayılan drop animasyonu**, sadece kart için overlay (liste sürüklemede overlay yok).
- **Asıl takılmanın nedeni (bulundu):** `api/boards.ts:127` `moveCard` yalnızca `onSettled: refresh` — **iyimser güncelleme (optimistic update) yok**. `BoardPage.tsx:~75–85` `useEffect`, `activeKey` null olunca `columns`'u **eski `board.data`'dan** yeniden kuruyor → bırakınca kart bir an **eski yerine zıplıyor**, refetch gelince yeni yerine geçiyor. `moveList` de aynı.
- `index.css:70–78` `prefers-reduced-motion` kuralı var (korunmalı).

### 1.6 Tema (`apps/web/src/index.css`)
- Tailwind v4 `@theme`: `slate-50…950` mürekkep tonlarıyla yeniden tanımlı, `blue-50…700`, `--color-rec`. Bileşenler neredeyse tamamen `slate-*`/`blue-*` kullanıyor → **dark mode için büyük avantaj:** CSS değişkenlerini `[data-theme=dark]` altında ters çevirmek uygulamanın çoğunu tek yerden koyulaştırır.
- **Engeller:** `bg-white`/`text-white`/`bg-black` **30 dosyada ~90 kullanım** (ör. `AssistantPanel` 10, `DayReviewForm` 8, `IntegrationsSettings` 7, `ProfilePage` 7, `CardModal` 6). Slate ters dönünce `bg-slate-900 text-white` düğmeleri açık zemin + beyaz yazı olur → okunmaz. Ayrıca `green-700`, `amber-*`, `red-*` durum renkleri, FullCalendar `--fc-*`, React Flow `--xy-*`, Recharts sabit hex renkleri (dataviz paleti), `::selection`.
- `user_settings` (`db/entities/user_settings.py`): `timezone`, `planning_time`, `review_time`, `reminders_enabled`, `week_start` — **tema/arka plan alanı yok**.

### 1.7 Ses
- Projede mikrofon/ses kodu yok. `AssistantPanel.tsx` metin girişi var.

---

## 2. İstek bazında analiz ve önerilen çözüm

### 2.1 Asistan: etiket + checklist + kart detayları (İstek 1, 2)

**Yeni/değişen araçlar (assistant-service):**
| Araç | Parametreler | İşlem türü (izin) | Yürütme |
|---|---|---|---|
| `add_checklist_items` | `card_id`, `items: [str]` (1–20) | `edit_checklist` (yeni) | madde başına `POST /cards/{id}/checklist` (ya da yeni toplu uç, aşağıda) |
| `update_checklist_items` | `card_id`, `changes: [{item_id, is_done?, text?}]` | `edit_checklist` | `PATCH /checklist/{id}` |
| `remove_checklist_items` | `card_id`, `item_ids: [int]` | `edit_checklist` (ya da mevcut silme türleri arasına — Opus karar) | `DELETE /checklist/{id}` |
| `set_card_labels` | `card_id`, `add: [ad]`, `remove: [ad]` | `manage_labels` (yeni) | eksik etiketi board'da oluştur → **yürütme anında** kartın güncel `label_ids`'ini alıp birleştir → `PATCH /cards/{id}` |
| `create_card` (genişlet) | + `labels: [ad]`, `checklist: [str]` | `create_card` | kart oluştur → etiket/checklist aynı yürütmede |
| `update_card` (ops. genişlet) | + `add_labels`, `remove_labels` | `update_card` | — (ya da yalnız `set_card_labels`; çakışan iki yol olmasın, Opus seçsin) |

- **Etiket ada göre çözülür** (board içinde casefold). Yoksa: özet "🏷 yeni etiket oluşturulur: 'Okul'" der; renk backend'deki palet listesinden (Trello eşlemesindeki en yakın palet mantığı `integrations/trello.py`) sıradaki kullanılmayan renk. Çok benzer ad (ör. "acil" vs "Acil!") için yeni etiket açmadan önce mevcut adlar özette gösterilir.
- **Özet örnekleri:** `☑️ 'Tez yazımı' kartına 3 madde: «Kaynakça», «Özet», «Giriş»` · `🏷 'Tez yazımı': +Okul, −Bekliyor`.
- **Yürütme anında yeniden okuma:** etiket seti ve checklist, onay ile öneri arasında kullanıcı tarafından değişmiş olabilir (7d'deki "arada taşındıysa atla" ilkesi) → tam liste PATCH'ini öneri anındaki değil yürütme anındaki duruma göre kur.
- **`get_card` okuma aracı:** checklist `[{id, text, is_done}]` ve etiketler `[{id, name}]` döndürmeli; board'un mevcut etiket adları `get_board`'da görünmeli (model doğru adı seçsin).
- **"Bu kart" bağlamı (öneri):** kart penceresi açıkken asistan paneline `context.card_id` gönderilirse "bu karta şunu ekle" çalışır. Panelin board bağlamını nasıl ilettiği (ModelRouter açık board'u biliyor) incelenip aynı yoldan eklenmeli.
- **task-api (opsiyonel):** `POST /cards/{id}/checklist/bulk` {items:[…]} tek transaction + tek activity kaydı. Gerek yoksa atlanır (madde başına POST da yeterli; Opus karar).
- **Odaklı istem riski:** qwen3.5:4b araç çağrısında iyi ama "ekledim" uydurabiliyor → onay kartı zaten gerçeği gösteriyor. Kabul testi gerçek modelle: "X kartının checklist'ine A, B, C ekle", "X kartına Acil etiketi koy", "X kartında 'Kaynakça'yı tamamlandı yap".
- **Testler:** `services/assistant-service/tests/` mevcut write tool test deseni (sahte task-api) — çözümleme, eksik etiket oluşturma, gizli board reddi, yürütme anında birleşme, izin modları.

### 2.2 Not geliştirmeleri (İstek 4)

**a) Çift tıklayınca düzenleme (küçük, yalnız frontend):**
- Not bloğuna `onDoubleClick` → aynı yerde textarea (içerik dolu, imleç sonda, otomatik yükseklik); **Ctrl+Enter kaydet, Esc iptal**, "Kaydet / Vazgeç" düğmeleri. `PATCH /notes/{id}` hazır.
- Erişilebilirlik: klavye kullanıcısı için görünür "Düzenle" düğmesi de (hover'da "Sil" yanında).
- `updated_at > created_at` ise "(düzenlendi)" ibaresi. Not güncellemesinin activity'ye yazılıp yazılmadığı kontrol edilmeli.
- Açıklama alanı ile aynı editör bileşeni kullanılmalı (aşağıda).

**b) Kod parçacığı:**
- `remark-gfm` (tablo, `- [ ]` görev listesi, üstü çizili) + vurgulayıcı: **`rehype-highlight` (highlight.js)** önerilir — hafif, açık/koyu tema CSS'i var (Shiki daha güzel ama ağır; Opus seçsin). Ham HTML kapalı kalır (güvenlik, react-markdown varsayılanı).
- Kod bloğu bileşeni: dil etiketi + **Kopyala** düğmesi, yatay kaydırma, dark mode uyumlu tema.
- Editör araç çubuğu: **Kod bloğu** (dil seçimli, ```` ```lang ```` şablonu ekler), satır içi kod, kalın, liste, görev listesi, bağlantı, **Ek ekle**. Tab tuşu kod bloğunda girinti (opsiyonel).
- Ortak bileşenler: `components/MarkdownView.tsx` (gösterim; açıklama + notlar + asistan mesajları ileride) ve `components/MarkdownEditor.tsx` (textarea + araç çubuğu + yapıştırma/sürükleme ile ek yükleme).

**c) Ek belge (Trello gibi) — backend + frontend, en büyük parça:**
- **Tablo `card_attachments`** (migration): `id, user_id, card_id (CASCADE), note_id (nullable, SET NULL), filename, mime_type, size_bytes, storage_key, sha256, created_at`. Karta ait; nota gömülü olanlar `note_id` taşır.
- **Depolama:** yerel disk `services/task-api/data/attachments/<user_id>/<uuid>` (git'e girmez, `.gitignore`); yol `config.py`'den (`ATTACHMENTS_DIR`). Docker/S3 yok → arayüz soyut tutulsun (`storage.save/open/delete`) ki ileride değişebilsin.
- **Uçlar:** `POST /cards/{id}/attachments` (multipart; `python-multipart` bağımlılığı var mı kontrol edilmeli), `GET /cards/{id}/attachments`, `GET /attachments/{id}/download`, `DELETE /attachments/{id}`. `CardDetail.attachments` + `CardSummary.attachment_count` (kanban kartında ataş ikonu).
- **`<img>` ve indirme yetkisi:** tarayıcı `<img src>` Authorization başlığı gönderemez → `GET /attachments/{id}/download?token=…` kısa ömürlü imzalı JWT (`purpose=attachment`, 10 dk, mevcut OAuth `state` imzalama deseni). Ya da frontend `fetch` → blob URL. Öneri: imzalı URL (önizleme + yeni sekmede açma basit).
- **Sınırlar:** dosya başına 25 MB (ayar), tür beyaz listesi değil kara liste (çalıştırılabilirler: `.exe .bat .ps1 .cmd .msi .js`?) — Opus netleştirsin; `Content-Disposition: attachment` ve resim/PDF dışı türlerde `inline` yok (XSS önlemi), `X-Content-Type-Options: nosniff`.
- **Nota gömme:** editöre yapıştırılan/sürüklenen resim → yükle → markdown'a `![ad](attachment:ID)` eklenir; `MarkdownView` `urlTransform` ile `attachment:ID` → imzalı URL. Resim dışı dosya → `[📎 ad](attachment:ID)`.
- **Kart penceresinde "Ekler" bölümü:** liste (ad, boyut, tarih, küçük resim), sürükle-bırak alanı, sil, indir; resim/PDF önizleme.
- **Silme yolları:** kart silme (CASCADE + **dosyayı diskten silme**), board silme (`repositories/board.py` elle siliyor → eklenmeli), not silme (ek kalır, `note_id` NULL). Commit sonrası dosya silme; yetim dosya temizliği (açılışta ya da zamanlayıcıda) opsiyonel.
- **AI ve gizlilik:** ek içerikleri modele gönderilmez; `get_card` yalnız ek adlarını/sayısını verir. (İleride: PDF/metin özetleme, `local_only` kuralına uyarak.)
- **Trello import:** şu an ekler açıklamaya link listesi olarak geliyor; değişmesin (dosya indirme gerçek Trello token'ı ister — kapsam dışı, ileride).
- **Testler:** yükleme/boyut sınırı/yasak tür/kullanıcı yalıtımı (başkasının eki 404)/imzalı token süresi ve amacı/kart ve board silmede dosyanın silinmesi (geçici dizin fixture'ı).

### 2.3 Teams toplantıları → takvim (İstek 3)

**Yaklaşım: Microsoft Graph takvimi (kişisel hesap), mevcut Microsoft OAuth hesabına kapsam eklenerek.**
- Kişisel hesapta Teams toplantıları Outlook.com takviminde etkinlik olarak durur. `GET /me/calendarView?startDateTime&endDateTime` (tekrarları örneklere açar), başlık `Prefer: outlook.timezone="UTC"`, `$select=subject,start,end,isAllDay,isCancelled,isOnlineMeeting,onlineMeetingProvider,onlineMeeting,webLink,location,showAs,changeKey,seriesMasterId`, sayfalama `@odata.nextLink`.
- **Kapsam:** `oauth.PROVIDERS["microsoft"]`'a `Calendars.Read` eklenir. Mevcut bağlı hesabın kayıtlı `scope`'unda yoksa UI'da "Teams toplantıları için izin ver" → yeniden bağlanma (`prompt=consent`). `OAuthSetup.tsx` Azure sihirbazına "API permissions → Microsoft Graph → Delegated → Calendars.Read" adımı eklenir. Token yenilemeleri yeni kapsamı korur.
- **"Haftalık çekme":** senkron penceresi = bu haftanın başı (`user_settings.week_start`'a göre) → **+N hafta** (varsayılan 2, ayar). 15 dk'lık zamanlayıcı turunda otomatik + Ayarlar'da ve Takvim sayfasında **"Bu haftanın toplantılarını çek"** düğmesi (sonuç özeti: eklendi/güncellendi/silindi). Pencere içinde artık dönmeyen ya da `isCancelled` olanlar silinir; geçmiş haftalar dokunulmadan kalır (istatistik için). `calendarView/delta` yerine pencere farkı önerilir (consumers'ta delta kaprisli; pencere yaklaşımı idempotent ve basit) — Opus teyit etsin.
- **Filtre ayarı:** "Sadece Teams toplantıları" (varsayılan) / "Tüm Outlook takvimi". Teams tespiti: `isOnlineMeeting && onlineMeetingProvider ∈ {teamsForBusiness, skypeForConsumer, …}` **veya** `onlineMeeting.joinUrl`'de `teams.live.com`/`teams.microsoft.com`. Hangi `onlineMeetingProvider` değerinin kişisel Teams'te döndüğü **gerçek hesapla doğrulanmalı** (risk).
- **Veri:** etkinlikler `events` tablosunda salt okunur (`created_by="integration"`, `external_links` provider `microsoft`, ayrı `kind`/`external_parent_id="calendar"`), hedef board ayarı (Google gibi). **Yeni sütun `events.meeting_url`** (migration) → `EventDialog`'da **"Teams'te katıl"** düğmesi, takvim ızgarasında video ikonu. Hesap ayarları `settings.calendar = {enabled, teams_only, board_id, weeks_ahead}`.
- **Bağlantı kesme / ayar kapatma:** Teams etkinlikleri silinir (Google deseni); To Do bağlantısı ayrı kalabilir.
- **Asistan etkisi:** toplantılar `get_calendar`'da görünür → `schedule_day` ve gün planı önerileri bunları sabit blok sayar. `schedule_day`'in mevcut etkinliklerle çakışma kontrolü yapıp yapmadığı doğrulanmalı; yapmıyorsa eklenmeli. Gizlilik: toplantı başlıkları bulut modele gidebilir → hedef board'un `privacy` ayarı uygulanır.
- **Hatırlatıcı (ops.):** `Reminders.tsx` toplantıdan 5 dk önce bildirim + "Katıl" bağlantısı.
- **Yedek plan (risk gerçekleşirse):** Outlook.com "Takvimi yayımla" ICS adresi ile genel **ICS aboneliği** içe aktarma. Yalnız Graph yolu toplantıları göstermezse ayrı alt faz olarak.
- **Testler:** `tests/integration/test_integrations_microsoft.py` deseni (sahte `HTTP_TRANSPORT`): kapsam eksik → yeniden bağlan, pencere hesaplama (hafta başı, saat dilimi), sayfalama, Teams filtresi, iptal, pencereden düşen silme, tüm gün, tekrar örnekleri, board taşıma, bağlantı kesme, salt okunur 409, kullanıcı yalıtımı, zamanlayıcı.
- **Gerçek hesap kabulü (kullanıcıda):** Azure'da izin ekle → Ayarlar → yeniden bağlan → Teams'te gelecek hafta için toplantı oluştur → "Bu haftayı çek" → `/calendar`'da görünür, "Teams'te katıl" çalışır; toplantıyı iptal et → sonraki senkronda kaybolur.

### 2.4 Sesli dikte (İstek 5)

- **Tamamen frontend.** `lib/useDictation.ts`: `window.SpeechRecognition || window.webkitSpeechRecognition`, `lang='tr-TR'`, `interimResults=true`, `continuous=true`; geçici metin girişte soluk görünür, kesinleşen eklenir.
- **Yerler:** önce `AssistantPanel` mesaj girişi (mikrofon düğmesi, kayıtta kırmızı nabız — `--color-rec`); sonra `MarkdownEditor` (not/açıklama) ve checklist ekleme girişi.
- **Davranış:** tıkla başlat/durdur (ya da basılı tut — Opus seçsin), kısayol (ör. `Ctrl+M`), sessizlikte otomatik durma; **mesaj otomatik gönderilmez**, kullanıcı gözden geçirip gönderir (ayar: "Dikte bitince gönder").
- **Destek:** Chrome/Edge; Firefox'ta yok → düğme gizlenir (özellik tespiti). localhost güvenli bağlam sayılır, mikrofon izni ilk kullanımda tarayıcı sorar.
- **Gizlilik:** ses tarayıcı üreticisinin sunucusuna gider → ilk kullanımda tek seferlik bilgi notu ("Sesin Google/Microsoft'ta metne çevrilir; local modelle çalışsan bile"). Ayarlar'da kapatma seçeneği. (İleride local Whisper seçeneği eklenebilir; tasarım hook arayüzünü motor bağımsız tutsun.)
- **Hata durumları:** `not-allowed` (izin), `no-speech`, `network`, `audio-capture` → Türkçe mesaj.
- **Doğrulama:** otomatik test zor (tarayıcı API'si) → hook için sahte `SpeechRecognition` ile birim testi yoksa elle tarayıcı denemesi; `npm run build`.

### 2.5 Sürükle-bırak animasyonları (İstek 6)

1. **İyimser güncelleme (asıl düzeltme):** `moveCard`/`moveList` `onMutate` → `qc.setQueryData(board)` ile kartın `list_id`/`position`'ını (ve liste sırasını) hemen güncelle, `onError` geri al + hata mesajı, `onSettled` refresh. `BoardPage`'deki `useEffect` mutasyon sürerken `columns`'u eski veriden yeniden kurmamalı (`isPending` ya da sürüm sayacı).
2. **Drop animasyonu:** `DragOverlay dropAnimation={{ duration: 200, easing: 'cubic-bezier(0.18,0.67,0.6,1.22)', sideEffects: defaultDropAnimationSideEffects({ styles: { active: { opacity: '0.4' } } }) }}`.
3. **Taşıma hissi:** overlay kartı hafif eğik (`rotate(2–3deg)`), `scale(1.03)`, gölge; yerinde kalan "hayalet" kesik çizgili yer tutucu.
4. **Liste sürükleme overlay'i** (şu an yok) + yatay otomatik kaydırma ayarı.
5. **Çarpışma:** boş listeye bırakma ve listeler arası geçiş için özel algılayıcı (`pointerWithin` → yoksa `rectIntersection`/`closestCenter`); `measuring={{ droppable: { strategy: MeasuringStrategy.Always } }}`.
6. `prefers-reduced-motion`'da animasyon kapalı kalır (mevcut CSS kuralı + `dropAnimation: null`).
7. **Kapsam dışı/ops.:** Bugün sayfası `PlanEditor` ve Takvim kenar paneli sürüklemeleri aynı ilkelerle gözden geçirilebilir.
- **Doğrulama:** tarayıcıda 3 liste × ~30 kart; listeler arası/aynı liste/boş liste/bitti listesine bırakma — geri zıplama yok; ağ yavaşlatıldığında (DevTools throttling) de yok; hata (sunucu kapalı) → geri alınır.

### 2.6 Dark mode + arka plan renkleri (İstek 7)

**Mekanizma:**
- `<html data-theme="light|dark">`; Tailwind v4 `@custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *));`.
- `[data-theme=dark]` altında `--color-slate-*` skalası **ters/koyu** değerlerle yeniden tanımlanır (50 = gece zemini … 900 = açık mürekkep), `blue-*`, `green/amber/red` kullanılan tonlar da koyu uyumlu. Bu, uygulamanın büyük kısmını tek yerden çevirir.
- **Anlamsal belirteçler:** `--color-surface` (kart/panel zemini; açıkta beyaz, koyuda slate-900 civarı) ve `--color-on-ink` (koyu düğme üstü yazı). **Kod dönüşümü:** `bg-white` → `bg-surface`, `bg-slate-900 text-white` desenli düğmeler → `text-on-ink` (~90 kullanım / 30 dosya; elle gözden geçirmeli toplu değişiklik — renkli zeminlerdeki `text-white` (board rengi, kayıt kırmızısı) aynen kalır).
- **Üçüncü taraflar:** FullCalendar `--fc-*`, React Flow `--xy-*` (5c'de zaten değişkenlerle temalanmış → koyu değerler eklenir), Recharts renkleri (dataviz paletinin koyu varyantı; `StatsPage`), kod vurgulama teması, `color-scheme: dark` (kaydırma çubukları, form denetimleri), `::selection`.
- **Board renkleri** aynen kalır; etiket çiplerinde yazı rengi kontrastına göre otomatik (açık/koyu) seçilsin.
- **İlk boyamada parlama olmasın:** `index.html`'de küçük satır içi script localStorage'daki temayı `data-theme`'e yazar; sunucudaki tercih gelince eşitlenir. "Sistem" seçeneği `matchMedia('(prefers-color-scheme: dark)')` dinler.

**Arka plan renk seçenekleri — iki katman önerisi (Opus kullanıcıya teyit ettirsin):**
1. **Uygulama zemini (kâğıt tonu):** hazır set — Kâğıt (varsayılan `#F2F4F8`), Krem, Adaçayı, Lavanta, Gri; koyu temada her birinin koyu karşılığı. Yalnız zemin/`surface` değişkenlerini değiştirir, mürekkep okunurluğu korunur. Serbest renk seçici **verilmez** (kontrast bozulur) ya da yalnız "gelişmiş" altında.
2. **Board arka planı (Trello gibi):** `boards.background` (hazır anahtar ya da hex; migration) → kanban alanının zemini; board formunda renk/degrade seçimi; koyu temada otomatik koyulaştırma. Liste sütunları yarı saydam yüzeyle okunur kalır.
- **Saklama:** `user_settings.theme` (`system|light|dark`) + `user_settings.background` (migration) — cihazlar arası; localStorage önbellek.
- **UI:** Ayarlar → yeni "Görünüm" bölümü (`Segmented` Sistem/Açık/Koyu + renk örnekleri, anında kaydetme — mevcut Ayarlar deseni), sol rayda hızlı tema düğmesi (ops.).
- **Doğrulama:** her sayfanın iki temada ekran görüntüsü (Bugün, Board, Kart penceresi, Takvim, İlişkiler, İstatistik, Ayarlar, Profil, Asistan paneli, Giriş), WCAG AA kontrast kontrolü (metin 4.5:1), `frontend-design` skill'iyle eleştiri turu.

---

## 3. Önerilen faz bölünmesi (Opus'un genel planı için taslak)

| Faz | Kapsam | Bağımlılık | Migration | Önerilen model | Gerekçe |
|---|---|---|---|---|---|
| **8a** | Asistan: checklist + etiket araçları, `create_card` genişletme, `get_card` genişletme, "bu kart" bağlamı | — | yok | **Sonnet** | Mevcut write-tool deseni net; araç tasarım kararları bu dokümanda |
| **8b** | Notlar: `MarkdownView/Editor`, çift tıkla düzenle, gfm + kod vurgulama + kopyala | — | yok | **Sonnet** | Saf frontend, net |
| **8c** | Ekler: `card_attachments`, depolama, uçlar, imzalı URL, kart penceresi "Ekler", nota resim yapıştırma | 8b (editör) | `card_attachments` | **Sonnet**; depolama/güvenlik ayrıntıları detay planda **Opus** tarafından kesinleştirilmeli | Dosya güvenliği ve silme yolları dikkat ister |
| **8d** | Teams/Outlook toplantıları (Graph calendarView, kapsam, haftalık pencere, `meeting_url`, "Teams'te katıl") | — | `events.meeting_url` | **Sonnet**; çözülemeyen OAuth/kapsam sorununda ayrı **Opus** hata ayıklama | Google deseni kopyası; gerçek-hesap riski |
| **8e** | Sürükle-bırak: iyimser güncelleme + animasyonlar | — | yok | **Sonnet** | Kök neden bulundu, iş net |
| **8f** | Sesli dikte (Web Speech) | 8b (editöre de eklenecekse) | yok | **Sonnet** (küçük; Haiku'ya fazla UI kararı) | — |
| **8g** | Dark mode + arka plan seçenekleri + `bg-white` dönüşümü | **en son** (8a–8f'de yazılan yeni bileşenler de dönüşsün) | `user_settings.theme/background`, `boards.background` | Belirteç/palet tasarımı **Opus**, toplu dönüşüm **Sonnet** | Tüm arayüze dokunur, tasarım kararı yoğun |
| Push | Her faz sonu commit/push | — | — | **Haiku** | CLAUDE.md iş akışı |
| Denetim | Tüm fazlar bitince plan ↔ kod | — | — | **Opus** | CLAUDE.md iş akışı |

- **Migration sırası:** alembic tek zincir (şu anki head `e4b8c2f6a9d3`); migration'lı fazlar (8c → 8d → 8g) **sırayla** yapılmalı, paralel oturumda dallanma olmasın.
- **Paralellik:** 8a (assistant-service), 8e (BoardPage/boards.ts), 8d (integrations) farklı dosyalara dokunur → ayrı oturumlarda paralel yapılabilir; 8b → 8c → 8f aynı editöre dokunur, sıralı.
- **Yeni bileşenlerde kural (8a–8f):** `bg-white` yerine 8g'de gelecek `bg-surface`'i şimdiden kullanmak için 8b başında yalnızca belirteci tanımlamak (değeri beyaz) öneri olarak değerlendirilsin — 8g dönüşümünü küçültür.

---

## 4. Opus'un plan aşamasında kesinleştirmesi gereken açık noktalar
1. Arka plan: iki katman (uygulama zemini + board arka planı) mı, yalnız biri mi? → kullanıcıya sorulmalı.
2. Ek: dosya boyutu sınırı, yasak türler, seri kartta ek kopyalanır mı (öneri: hayır), yetim dosya temizliği.
3. Etiket araçları: `set_card_labels` tek yol mu, `update_card`'a da eklenecek mi? Checklist silme hangi izin türü?
4. Teams: pencere uzunluğu varsayılanı (2 hafta), "sadece Teams" varsayılanı, ICS yedeğinin şimdi mi ileride mi yapılacağı.
5. Dikte: tıkla-başlat mı basılı tut mu; otomatik gönderme varsayılanı (öneri: kapalı).
6. Kod vurgulayıcı: `rehype-highlight` vs Shiki.
7. "Bu kart" bağlamının asistan paneline nasıl iletileceği (mevcut board bağlamı yolunu inceleyerek).

---

## 5. Kritik dosyalar (detay planlarda kullanılacak)
- Asistan: `services/assistant-service/app/tools/write_tools.py`, `app/tools/read_tools.py`, `app/tools/schedule_day.py`, izin/aksiyon modelleri, `tests/`.
- task-api kart: `app/api/v1/cards.py`, `app/services/card.py`, `app/models/card.py`, `app/db/entities/card_content.py`, `app/db/repositories/board.py` (board silme), `app/db/entities/board.py`, `app/db/entities/user_settings.py`, `app/db/entities/event.py`, `alembic/versions/`.
- Entegrasyon: `app/integrations/oauth.py`, `microsoft_todo.py` (`GraphClient`), `google_calendar.py` (desen), `scheduler.py`, `app/api/v1/integrations.py`, `app/services/event.py` (salt okunur 409).
- Frontend: `components/CardModal.tsx`, `pages/BoardPage.tsx`, `components/KanbanList.tsx`, `components/CardFace.tsx`, `api/boards.ts`, `components/AssistantPanel.tsx`, `components/EventDialog.tsx`, `pages/CalendarPage.tsx`, `components/IntegrationsSettings.tsx`, `components/OAuthSetup.tsx`, `pages/SettingsPage.tsx`, `components/BoardForm.tsx`, `components/Page.tsx` (ortak `Segmented`/`Row`), `index.css`, `index.html`, `lib/api-schema.d.ts` (elle güncelleme notu: `npm run gen:api` çalışan sunucu ister).

## 6. Doğrulama (her faz için genel)
- `services/task-api`: `uv run pytest -q` (şu an 265) · `services/assistant-service`: `uv run pytest -q` (120) · `apps/web`: `npm run build`; ruff yeni dosyalarda yalnız E501 kabul.
- Tarayıcı doğrulaması kopya portlarda (`task-api-alt` 8001 / `web-alt` 5175, `.claude/launch.json`) — gerçek uygulama 8000/5173'te gerçek DB ile çalışıyor; migration öncesi gerçek DB yedeği.
- Gerçek-model/gerçek-hesap kabul adımları (8a: qwen3.5:4b ve gemma4:26b ile 3 cümle; 8d: kişisel Microsoft hesabıyla Teams toplantısı) kullanıcıda; bulut modellere gerçek istek atılmaz (kullanıcı kuralı).
- Her faz sonunda ana plandaki "0. İlerleme Durumu" tablosuna satır + "yapılanlar" bölümü eklenir.
