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
_(oturum sonunda doldurulur)_
