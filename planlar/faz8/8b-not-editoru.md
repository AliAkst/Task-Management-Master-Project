# Faz 8b — Not editörü: çift tıkla düzenle, kod parçacığı, GFM

**Önerilen model: Sonnet** — saf frontend + 1 küçük backend düzeltmesi; kararlar verildi.

## Mevcut durum
- `apps/web/src/components/CardModal.tsx`: açıklama tıkla→textarea + `react-markdown` (~200–217); notlar (~301–319) yalnız ekle (Ctrl+Enter) + Sil; `remark-gfm` ve vurgulama yok.
- Backend `PATCH /notes/{id}` var; `CardService.update_note` (`services/card.py:628-634`) activity yazmıyor (`add_note` yazıyor: `("note", id, "created")`).
- `AssistantPanel.tsx` mesajları `react-markdown` ile.

## Adımlar
1. **Belirteçler (8g'ye hazırlık):** `index.css` `@theme`'e `--color-surface: #ffffff;` ve `--color-on-ink: #ffffff;` ekle (Tailwind `bg-surface`, `text-on-ink` üretir). Kod renkleri için `:root` değişkenleri: `--code-bg` (slate-100), `--code-fg` (slate-900), `--code-comment` (slate-500), `--code-keyword` (#7a3fc4), `--code-string` (#1f7a4a), `--code-number` (#b05a00), `--code-title` (blue-700), `--code-attr` (#a1356b), `--code-meta` (slate-600); `.hljs-*` sınıflarını bunlara bağla (keyword, built_in, type, literal, number, string, regexp, comment, title, function, attr, attribute, meta, variable, symbol, deletion/addition). highlight.js'in hazır CSS'i **import edilmez**.
2. Bağımlılıklar: `npm i remark-gfm rehype-highlight`.
3. **`components/MarkdownView.tsx`:** `react-markdown` + `remark-gfm` + `rehype-highlight` (`detect: false`, `ignoreMissing: true`); ham HTML kapalı (varsayılan). Bileşen eşlemeleri: `pre` → `CodeBlock` (üstte dil etiketi + **Kopyala** düğmesi → `navigator.clipboard.writeText`, 1,5 sn "Kopyalandı", `overflow-x-auto`, `bg-[var(--code-bg)]`, monospace), satır içi `code` (hafif zemin), `a` (`target=_blank rel="noopener noreferrer"`), tablo (ince çizgili, yatay kaydırma), görev listesi kutuları salt okunur. Prop'lar: `content`, `className`, ileride (8c) `attachments?`. Mevcut tipografi sınıflarını CardModal'dan taşı.
4. **`components/MarkdownEditor.tsx`** (`forwardRef`, `useImperativeHandle` → `insert(text)`, `focus()`): otomatik yükselen textarea (`bg-surface`), araç çubuğu (lucide ikonları, `title` ipuçları): Kalın (Ctrl+B), Satır içi kod (Ctrl+E), **Kod bloğu** (dil menüsü: Düz metin, JavaScript, TypeScript, Python, Bash, PowerShell, JSON, SQL, HTML, CSS, C#, Java, YAML → seçimi ```` ```lang\n…\n``` ```` ile sarar ya da şablon ekler, imleç içte), Liste, Görev listesi, Bağlantı. Kod çiti içindeyken (imleçten önceki ```` ``` ```` sayısı tek) **Tab = 2 boşluk**, Shift+Tab girinti azaltır. **Ctrl+Enter = kaydet, Esc = vazgeç.** Prop'lar: `value, onChange, onSubmit, onCancel, placeholder, autoFocus, minRows, toolbarExtra?: ReactNode` (8c ek düğmesi, 8f mikrofon buraya). Düğmeler: "Kaydet" (`bg-slate-900 text-on-ink`), "Vazgeç".
5. **CardModal açıklama:** gösterim `MarkdownView`, düzenleme `MarkdownEditor` (mevcut tıkla-düzenle davranışı korunur; çift tıklama da açar).
6. **CardModal notlar:**
   - Yeni not formu → `MarkdownEditor`.
   - Not bloğu: `onDoubleClick` → yerinde `MarkdownEditor` (içerik dolu, imleç sonda). Aynı anda tek not düzenlenir. Hover/odakta görünen **"Düzenle"** ve "Sil" düğmeleri (klavye erişimi). Kaydet → `PATCH /notes/{id}` (api/cards.ts'te hook yoksa `useUpdateNote` ekle, kart sorgusunu tazele). Esc: içerik değişmişse `confirm('Değişiklikler kaybolsun mu?')`.
   - `updated_at` − `created_at` > 5 sn ise tarih yanında "(düzenlendi)".
   - Not içindeki bağlantı/kopyala düğmesine çift tıklama düzenlemeyi açmasın (`e.target.closest('a,button')` kontrolü).
7. `AssistantPanel` asistan mesajları → `MarkdownView` (kod blokları kopyalanabilir).
8. **Backend:** `update_note` → `ActivityLogger` `("note", id, "updated")`; `delete_note` → `("note", id, "deleted")`. Test: `tests/integration/` not testlerine 2 test (activity kayıtları).

## Kabul ölçütleri
- Nota çift tık → düzenle → Ctrl+Enter kaydedilir, "(düzenlendi)" görünür; Esc iptal; "Düzenle" düğmesiyle klavyeden de olur.
- ```` ```python ```` bloğu renkli, dil etiketi + Kopyala çalışır; tablo, `- [ ]` görev listesi, ~~üstü çizili~~ görünür.
- Asistan mesajındaki kod bloğu da aynı görünümde.
- task-api testleri yeşil (+2), `npm run build` temiz.

## Doğrulama
5175'te kart penceresi: not ekle (kod bloklu), çift tıkla düzenle, kaydet; ekran görüntüsü. `read_console_messages` hatasız.

## İlerleme
**Durum: ✅ Kod tamam, commit edilmedi (2026-11-09).**

### Yapılanlar
- `index.css`: `--color-surface`, `--color-on-ink` (`@theme`), `--code-*` değişkenleri ve `.hljs-*` kuralları (highlight.js hazır CSS'i kullanılmadı).
- `npm i remark-gfm rehype-highlight`.
- `components/MarkdownView.tsx` (GFM + rehype-highlight `detect:false, ignoreMissing:true`, `CodeBlock` dil etiketi + Kopyala/“Kopyalandı” 1,5 sn, `a` → `_blank noopener noreferrer`, tablo yatay kaydırma, satır içi kod, salt okunur görev kutuları).
- `components/MarkdownEditor.tsx` (forwardRef: `insert`, `focus`; otomatik yükselen textarea; araç çubuğu: kalın/satır içi kod/kod bloğu dil menüsü (13 dil)/liste/görev listesi/bağlantı; Ctrl+B, Ctrl+E; çit içinde Tab = 2 boşluk, Shift+Tab girinti azaltır; Ctrl+Enter kaydet, Esc vazgeç; `toolbarExtra`).
- `CardModal`: açıklama `MarkdownView`/`MarkdownEditor` (tıkla + çift tıkla düzenle); notlar: yeni not `MarkdownEditor`, çift tıkla yerinde düzenleme (tek not), hover/odakta “Düzenle”/“Sil”, “(düzenlendi)” (>5 sn), Esc'te değişiklik varsa `confirm`, `a,button` üzerinde çift tık düzenlemeyi açmaz. `api/boards.ts` → `updateNote`.
- `AssistantPanel`: mesajlar `MarkdownView`.
- Backend: `update_note` → `("note", id, "updated")`, `delete_note` → `("note", id, "deleted")`; 2 yeni test.

### Sapmalar
| Planda | Yapılan | Neden |
|---|---|---|
| Not Esc: yalnız notta onay | Açıklama düzenleyicisinde de değişiklik varsa aynı `confirm` | Tutarlılık; kaybolmasın |
| Geçmişte not satırı hep “not eklendi” | “not eklendi/düzenlendi/silindi” (`NOTE_ACTION`) | Yeni activity eylemleri görünsün |
| Notta mevcut “Notu kaydet” yalnız doluyken görünürdü | Kaydet düğmesi `MarkdownEditor`'da hep görünür | Editör bileşeni ortak |
| `attachments?` prop (8c) | Eklenmedi | 8c'de eklenecek |
| `delete_note` activity kartı silinmiş sayılmaz | Kart `get_owned_card` ile alınır | board_id/card_id için |

### Doğrulanmayanlar
- Ekran görüntüsü alınamadı (Claude penceresi gizliydi, screenshot zaman aşımı); davranış DOM/JS ile doğrulandı. Görsel kontrol kullanıcıda (koyu sürüm yok; kod renkleri, tablo, dil menüsü konumu).
- Dil menüsü, Tab/Shift+Tab, Ctrl+B/E, “Kopyala” panoya gerçek yazma (clipboard izni) elle denenmedi; kod yazıldı, derleme temiz.
- Asistan panelinde kod bloğu (gerçek model yanıtı) denenmedi.

### Test sayıları
- task-api: 269 geçti (+2). assistant-service: 147 geçti. `npm run build` temiz.
- Tarayıcı (8001 DB kopyası / 5175): not ekle (python kod bloğu + tablo + görev listesi + ~~üstü çizili~~) → hljs sınıfları, tablo, checkbox, `del` var; çift tık → düzenle → Ctrl+Enter → “(düzenlendi)”; Esc'te `confirm` ile editör açık kaldı ve kart penceresi kapanmadı; konsolda yalnız sunucu açılırken oluşan geçici 500/401.
- Ruff: bu fazda eklenen satırlarda hata yok (kalan E501'ler eski satırlar).
