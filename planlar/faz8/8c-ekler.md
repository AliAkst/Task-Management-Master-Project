# Faz 8c — Kart ekleri (Trello gibi)

**Önerilen model: Sonnet.** Güvenlik/depolama kararları bu dosyada Opus tarafından kesinleştirildi; Sonnet bunlara birebir uyar. Kararlardan sapma gerekirse (ör. FastAPI dosya yanıtı farklı davranırsa) sapmalar tablosuna yaz, güvenlik başlıklarından taviz verme.

**Ön koşul:** 8b bitti (`MarkdownEditor.insert`, `MarkdownView`).

## Kararlar
- Dosya başına **25 MB** (`ATTACHMENTS_MAX_MB`, config). Kullanıcı başı toplam sınır yok.
- **Yasak uzantılar:** `.exe .msi .bat .cmd .com .scr .ps1 .psm1 .vbs .vbe .wsf .jar .lnk .dll .sys .reg .hta .cpl` → 422 `ATTACHMENT_TYPE_BLOCKED`. (Kod dosyaları `.js .py .ts` serbest: kullanıcı kod saklamak istiyor; zaten hiçbir dosya inline çalıştırılmaz.)
- MIME **istemciden alınmaz**: uzantıdan `mimetypes.guess_type`, yoksa `application/octet-stream`.
- **Inline gösterilen türler yalnız:** `image/png, image/jpeg, image/gif, image/webp, application/pdf`. SVG dahil diğer her şey `Content-Disposition: attachment`.
- İndirme yanıt başlıkları: `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox`, `Cache-Control: private, max-age=3600`. Dosya adı RFC 5987 (`filename*=UTF-8''…`).
- **İmzalı URL:** `purpose="attachment"`, `sub=user_id`, `aid=attachment_id`, `exp=60 dk`, `settings.jwt_secret_key` (desen: `app/integrations/oauth.py` `make_state/read_state`). Her `AttachmentResponse` üretilirken taze `url` eklenir; kart sorgusu tazelendikçe yenilenir. Uç Authorization başlığını da kabul eder.
- Depolama: `services/task-api/data/attachments/<user_id>/<uuid4>` (uzantısız); kökü `ATTACHMENTS_DIR` (varsayılan task-api klasörüne göre `data/attachments`). `.gitignore`'a `services/task-api/data/`. Yol yalnız sunucu ürettiği `storage_key`'den kurulur (kullanıcı adı yolda yok → yol geçişi imkânsız); okurken `resolve()` kök altında mı kontrolü.
- Silme: kart silme ve board silme ek satırlarını + dosyaları siler; not silme eki silmez (`note_id = NULL`); kart arşivleme dokunmaz. Dosyalar **commit sonrası** silinir (hata loglanır, akış bozulmaz). Seri kart kopyası ekleri **kopyalamaz**. Trello import değişmez.
- Açılışta yetim temizliği: kökteki, DB'de satırı olmayan ve 24 saatten eski dosyalar silinir (log: adet).
- AI: ek içerikleri modele gitmez; `get_card` yalnız `attachments: [dosya adı]` verir.

## Adımlar (task-api)
1. `uv add python-multipart`.
2. Entity `CardAttachmentEntity` (`app/db/entities/card_content.py`): `id, user_id (index), card_id (FK tasks, index), note_id (nullable), filename String(255), mime_type String(120), size_bytes Integer, storage_key String(80) unique, sha256 String(64), created_at`. Repo + UoW kaydı (mevcut not/checklist deseni).
3. Migration `<rev>_card_attachments.py`, `down_revision = "e4b8c2f6a9d3"`. Gerçek DB yedeği → kopyada upgrade/downgrade/upgrade.
4. `app/services/attachment_storage.py`: `LocalAttachmentStorage(root)` — `save(user_id, chunks) -> (storage_key, size, sha256)` (geçici dosyaya 1 MB parçalarla yaz, sınır aşılınca sil + `ATTACHMENT_TOO_LARGE` 413), `path(key)`, `delete(key)`, `sweep_orphans(known_keys, older_than)`. Ayrıca `make_attachment_token / read_attachment_token`.
5. `app/services/attachment.py` `AttachmentService`: `upload(card_id, file, note_id?)` (kart sahipliği, note_id karta ait mi, uzantı kontrolü, ad temizleme: basename + kontrol karakterleri at + 200 karakter), `list(card_id)`, `get_for_download(id, user_id)`, `delete(id)`. Activity `("attachment", id, "created"/"deleted")`.
6. Uçlar (`app/api/v1/cards.py` ya da yeni `attachments.py`): `POST /cards/{card_id}/attachments` (multipart `file`, form `note_id?`), `GET /cards/{card_id}/attachments`, `GET /attachments/{id}/download?token=&download=1`, `DELETE /attachments/{id}`. Başkasının eki → 404 (token'daki `sub` ≠ sahip → 404).
7. Modeller: `AttachmentResponse {id, card_id, note_id, filename, mime_type, size_bytes, is_image, created_at, url}`; `CardDetail.attachments`; `CardSummary.attachment_count` (`note_count` nasıl hesaplanıyorsa öyle).
8. Silme yolları: kart silme servisinde notlar/checklist nasıl elle siliniyorsa ekleri de sil (SQLite'ta FK kapalı); `db/repositories/board.py:83+` board silmeye ekle; `delete_note` → bağlı eklerin `note_id`'si NULL. Dosya silme commit sonrası.
9. `main.py` lifespan: açılışta `sweep_orphans` (try/except, uygulamayı durdurmaz).
10. assistant-service `get_card`: `attachments: [filename]` (8a'daki biçime ek).

## Adımlar (frontend)
11. `api/attachments.ts`: `useUploadAttachment(cardId)` (`fetch` + `FormData`, auth başlığı; hata kodlarını Türkçe göster: 413 "Dosya 25 MB'tan büyük", 422 "Bu dosya türü yüklenemez"), `useDeleteAttachment`. Kart sorgusunu tazele.
12. CardModal **"Ekler"** bölümü (notların üstünde): liste (resimse 48 px küçük resim `<img src={url}>`, ad, boyut KB/MB, tarih), satır düğmeleri Aç (yeni sekme `url`), İndir (`url&download=1`), Sil (onaylı); "Dosya ekle" düğmesi (`<input type=file multiple>`); kart penceresine dosya sürüklenince bırakma alanı vurgusu; yükleme sürerken satırda dönen gösterge.
13. `MarkdownEditor` `toolbarExtra`'ya 📎 düğmesi; editöre **yapıştırılan** (`clipboardData.files`) ya da **bırakılan** dosya → yükle → resimse `![ad](attachment:ID)`, değilse `[📎 ad](attachment:ID)` imlece eklenir (`insert`). Mevcut not düzenlenirken `note_id` gönderilir.
14. `MarkdownView` `attachments` prop'u + `urlTransform`: `attachment:ID` → eşleşen `url`; bulunamazsa "📎 ek silinmiş" metni; diğer URL'ler react-markdown `defaultUrlTransform`.
15. `CardFace.tsx`: `attachment_count > 0` → ataş ikonu + sayı (not sayacının yanında).
16. `api-schema.d.ts` elle.

## Testler (`tests/integration/test_attachments.py`, `ATTACHMENTS_DIR` → `tmp_path` monkeypatch)
Yükleme + liste + indirme içeriği/sha; 25 MB aşımı 413 (sınırı testte küçült); yasak uzantı 422; MIME uzantıdan (istemci `text/html` gönderse de `.png` → image/png); inline/attachment başlıkları + nosniff + CSP; SVG attachment; token süresi dolmuş/yanlış purpose/başka kullanıcı → 404/401; Authorization başlığıyla indirme; başkasının kartına yükleme 404; not silme → ek kalır `note_id` NULL; kart silme ve board silme → satır + dosya yok; seri kart kopyası eksiz; yetim temizliği; ad temizleme (`../../x.txt` → `x.txt`).

## Kabul ölçütleri
- Testler yeşil (task-api mevcut + ≥16); `npm run build` temiz.
- Tarayıcıda (5175): PDF + PNG ekle, küçük resim görünür, Aç/İndir/Sil çalışır; nota ekran görüntüsü yapıştır → notta resim görünür; kanban kartında ataş sayısı.

## İlerleme
**Durum: ✅ Kod tamam, commit'lendi (`ab4571c`, 2026-11-09), push bekliyor.** Migration `a5c9e1b3d7f2_card_attachments.py` (down = `e4b8c2f6a9d3`).

### Yapılanlar
- **Backend:** `python-multipart`; `CardAttachmentEntity` + `AttachmentRepository` (UoW `attachments`); `app/services/attachment_storage.py` (`LocalAttachmentStorage` save/path/delete/sweep_orphans, `make/read_attachment_token`); `app/services/attachment.py` (`AttachmentService`: upload/list_for_card/get_for_download/delete, ad temizleme, yasak uzantılar, MIME uzantıdan); `app/api/v1/attachments.py` (4 uç; indirme token'lı ya da Authorization'lı); `AttachmentResponse`, `CardDetail.attachments`, `CardSummary.attachment_count`; config `ATTACHMENTS_MAX_MB` (25) + `ATTACHMENTS_DIR`; açılışta yetim temizliği (`main.sweep_orphan_attachments`, try/except).
- **Silme yolları:** `CardService.delete`, `TaskService.delete` (eski `/tasks` ucu da kart siler), `BoardService.delete` (+ `delete_cascade`) ek satırlarını siler, dosyalar commit sonrası; `delete_note` → `note_id = NULL`; arşiv dokunmaz; seri kopyası eksiz (zaten kopyalanmıyordu, test eklendi).
- **assistant-service:** `get_card` → `attachments: [dosya adı]` (URL/token yok) + 1 test.
- **Frontend:** `api/attachments.ts` (`uploadAttachment` FormData + 401'de yenileme, `useUploadAttachment/useDeleteAttachment/useUploads`, Türkçe 413/422 mesajı); `AttachmentsSection.tsx` (Notlar'ın üstünde; 48 px küçük resim, ad, boyut, tarih, Aç/İndir/Sil(onaylı), "Dosya ekle", yükleme göstergesi); `CardModal` kart penceresine dosya sürükleme vurgusu + bırakma; `MarkdownEditor` `onFiles` (📎 düğmesi, yapıştırma, bırakma → `![ad](attachment:ID)` / `[📎 ad](attachment:ID)`; not düzenlerken `note_id`); `MarkdownView` `attachments` + `urlTransform` (bulunamazsa "📎 ek silinmiş"); `CardFace` ataş + sayı; `formatBytes`.
- `api-schema.d.ts`: `npx openapi-typescript` ile uygulamanın `app.openapi()` çıktısından üretildi (elle değil).

### Sapmalar
| Planda | Yapılan | Neden |
|---|---|---|
| `.gitignore`'a `services/task-api/data/` | Eklenmedi | `services/task-api/.gitignore:27` zaten `data/` içeriyor |
| 📎 düğmesi `toolbarExtra`'ya | `MarkdownEditor` kendisi (`onFiles` verilince) 📎 + gizli `<input>` çiziyor; `toolbarExtra` aynen duruyor | Düğme editörün `insert`/imleç mantığına ve yükleme durumuna bağlı; dışarıdan yönetmek kırılgan |
| Yükleme `app/api/v1/cards.py` ya da yeni dosya | Yeni `attachments.py` | Plan iki seçeneği de sundu |
| Token ≠ sahip → 404; süresi dolmuş/yanlış purpose → "404/401" | Bozuk/süresi dolmuş/yanlış purpose/token'sız → **401**; token geçerli ama başka kullanıcı/başka ek → **404** | Plan "404/401" diyordu; ayrım kimlik hatası vs. sahiplik |
| Dosya adı yalnız `filename*=` | `filename="ascii-yedek"; filename*=UTF-8''…` ikisi birden | RFC 6266 uyumu, eski istemciler |
| 25 MB sınırı yalnız parça parça yazarken | Ek olarak `Content-Length` > sınır+1 MB ise baştan 413 | Starlette multipart'ı önce geçici dosyaya alıyor; gereksiz okumayı önler. Sınır yine yazarken kesin uygulanır |
| `AttachmentResponse` her üretildiğinde taze token | `to_response()` her çağrıda yeni token (60 dk) | Plana uygun; kart sorgusu tazelenince URL'ler yenilenir |
| `api-schema.d.ts` elle | Üreteçle (dosyadan) | Çıktı gerçek şemayla birebir; yeni router'ın sırası yüzünden bazı blokların yeri değişti (diff gürültülü, içerik aynı) |
| Gerçek DB yedeği | DB'ye hiç dokunulmadı; migration yalnız kopyada (`%TEMP%\8c_copy.db`) denendi | Kural: gerçek DB'ye dokunma. Gerçek DB'yi kullanıcı "Ajanda - Durdur → Ajanda" ile taşıyacak (öncesinde yedek almak kullanıcıda) |

### Doğrulanmayanlar
- **PDF'yi yeni sekmede (Aç) görüntüleme:** plandaki CSP `sandbox` bazı tarayıcılarda dahili PDF görüntüleyicisini engelleyebilir; yalnız başlıklar doğrulandı (`inline` + CSP). Sorun çıkarsa "İndir" çalışır; çözüm gerekirse PDF için `sandbox` çıkarılabilir (kullanıcı kararı).
- Gerçek ekran görüntüsü yapıştırma (pano izni), gerçek sürükle-bırak (OS'tan) ve 25 MB'lık gerçek dosya yüklemesi tarayıcıda denenmedi; yapıştırma/yükleme `ClipboardEvent`/`DataTransfer` ile simüle edildi, 413 testle doğrulandı.
- Silme düğmesi (`confirm`) tarayıcıda tıklanmadı (API testleri kapsıyor).
- Dark mode yok (8g); yeni bileşende `bg-surface`/`text-on-ink` kuralına uyuldu.

### Test sayıları
- task-api: 298 geçti (+29: `tests/integration/test_attachments.py`). assistant-service: 148 geçti (+1). `npm run build` temiz.
- Migration (DB kopyasında): `upgrade` → `downgrade -1` → `upgrade`, `alembic check` "No new upgrade operations".
- Tarayıcı (8001 kopya DB + kopya ek klasörü / 5175): PNG + PDF + `.exe` yükleme (`.exe` → "Bu dosya türü yüklenemez"), küçük resim görünür, nota resim yapıştırma → `![image.png](attachment:3)` → kayıtta resim render, kanban kartında ataş + 3, indirme başlıkları (inline, nosniff, CSP). Kopya DB'den entegrasyon hesabı satırı silindi (arka plan senkronu gerçek hesaba gitmesin).
- Ruff: yeni/değişen dosyalarda yalnız E501 (yeni dosyalarda kabul).
