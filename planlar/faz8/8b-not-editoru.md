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
_(oturum sonunda doldurulur)_
