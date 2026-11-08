# Faz 8a — Asistan: checklist + etiket + "bu kart" bağlamı

**Önerilen model: Sonnet** — mevcut write-tool deseni (`prepare` → `PreparedAction` → `execute`) birebir uygulanıyor; araç tasarım kararları bu dosyada verildi. Opus gerekmez.

**Hedef:** Kullanıcı "X kartının checklist'ine A, B, C ekle", "X kartına Acil etiketi koy", "'Kaynakça'yı tamamlandı yap", kart penceresi açıkken "bu karta … ekle" diyebilsin; hepsi onay kartından (izin ask/auto/never) geçsin.

## Mevcut durum (doğrulandı)
- `services/assistant-service/app/tools/write_tools.py`: `ACTION_TYPES` (~44), `WRITE_SPECS` (~66–180), `TOOL_TO_ACTION`, `action_type_of` (~186), `prepare()` (~316–341; `_prepare_<name>` getattr), `_prepare_create_card` (~343–381), `_prepare_update_card` (~383–440), `execute()` tek if-zinciri (~730–813), `_execute_schedule`/`_execute_triage`. Yardımcılar `_card()` (gizlilik kontrollü), `_board()`, `_find_list()`, `_clip()`, `_int()`.
- `app/tools/delete_tools.py`: `delete_cards`, `cancel_day`; `execute_delete(api, action_type, args)`.
- `app/tools/read_tools.py`: `_card(c)` (39–57) özet; `get_board` (235–244) etiketsiz; `get_card` (262–288) checklist id'siz, etiket yok.
- Chat: `app/api/chat.py` `ChatRequest` (55–60: message, conversation_id, model_id, board_id); `board_id` yalnız `resolve_model`'e (262–266); `build_system_prompt(...)` (`app/agent/context.py:44-52`) board almıyor (çağrı `chat.py:342`).
- Frontend: `AssistantPanel.tsx:127-128` `useMatch('/boards/:boardId')`, 176'da gövde; tip `api/assistant.ts:103`. Açık kart URL'de `?card=<id>`.
- task-api: kart etiketleri `PATCH /cards/{id}` `label_ids` tam liste (`services/card.py:330–351`, `_validate_labels`); `POST /boards/{id}/labels`; checklist `POST /cards/{id}/checklist`, `PATCH|DELETE /checklist/{id}` (text ≤ 500).
- Testler: `tests/conftest.py` `FakeTaskApi` (183), `fake_api`, `task_api_transport`, `FakeProvider`; yazma testleri `tests/test_actions.py`.

## Adımlar
### A. task-api (küçük)
1. **Etiket rengi opsiyonel:** `LabelCreate.color` verilmezse task-api board'da kullanılmayan ilk palet rengini seçer. Palet listesini `app/integrations/trello.py`'deki paletten ortak `app/services/palette.py`'ye taşı (trello.py oradan import etsin; davranış değişmez). Tümü kullanılıyorsa ilk renk.
2. Test: `tests/integration/` altında mevcut label testlerinin yanına "renksiz etiket → sıradaki boş palet rengi" (2 test).

### B. Okuma araçları (`read_tools.py`)
3. `get_card`: `checklist_items` → `[{id, text, is_done}]`; `labels` → `[{id, name}]` (board'un etiket listesinden ad eşle; `GET /boards/{board_id}` zaten `labels` veriyor); `recent_notes` aynen. Araç açıklamasını güncelle ("madde id'leri update/delete için").
4. `get_board`: `labels: [ad, …]` ekle. `_card()` özetine `labels: [ad]` ekle (ad haritası verilirse).

### C. Yazma araçları (`write_tools.py`, `delete_tools.py`)
5. Yeni işlem türleri `ACTION_TYPES`'a: `edit_checklist`, `manage_labels`, `delete_checklist_items`. Türkçe etiketleri izin listesinin üretildiği yere ekle ("Checklist düzenleme", "Etiket ekleme/çıkarma", "Checklist maddesi silme") — Ayarlar UI'ı etiketleri backend'den okur, frontend değişmez.
6. Araçlar (`WRITE_SPECS`):
   - `add_checklist_items(card_id:int, items:[str] 1–20)` → `edit_checklist`. Prepare: kartı `_card()` ile al (gizlilik), metinleri `_clip(…, 500)`, boşları at, karttaki mevcut maddelerle casefold aynı olanları at (özet "zaten var: …"). Özet: `☑️ 'Tez yazımı' kartına 3 madde: «Kaynakça», «Özet», «Giriş»`.
   - `update_checklist_items(card_id:int, changes:[{item_id:int, is_done?:bool, text?:str}])` → `edit_checklist`. Prepare: item_id karta ait değilse hata ("Bu madde kartta yok; get_card ile id'leri al"). Özet: `☑️ 'Tez yazımı': «Kaynakça» ✓ tamamlandı`.
   - `delete_checklist_items(card_id:int, item_ids:[int])` → `delete_checklist_items` (delete_tools.py'de, `delete_cards` deseniyle). Özet maddeleri adlarıyla listeler.
   - `set_card_labels(card_id:int, add:[str]=[], remove:[str]=[])` → `manage_labels`. Ad çözümü `_norm(s) = casefold + yalnız harf/rakam` ile board etiketleriyle eşleşir ("Acil!" = "acil"). Eşleşmeyen `add` → yeni etiket; özet: `🏷 'Tez yazımı': +Okul (yeni etiket; mevcutlar: Acil, Bekliyor), −Bekliyor`. Eşleşmeyen `remove` → yok sayılır, özette not.
   - `create_card` genişlet: `labels:[str]`, `checklist:[str]` (≤20). Aynı çözüm ve özet satırları kart özetinin altına.
   - `update_card`'a etiket **eklenmez**; araç açıklamasına "etiket için set_card_labels" yaz.
7. Yürütme (`execute()` if-zinciri; `X-Actor: ai`):
   - `edit_checklist`: ekleme → madde başına `POST /cards/{id}/checklist`; değişiklik → `PATCH /checklist/{id}`. Yürütme anında madde silinmişse (404) atla, sonuçta `skipped`.
   - `delete_checklist_items`: `DELETE /checklist/{id}`, 404 atlanır.
   - `manage_labels`: **yürütme anında** kartı yeniden oku (güncel `label_ids`), eksik etiketleri `POST /boards/{board_id}/labels {name}` (renksiz → task-api seçer) ile oluştur (bu arada aynı ad oluşmuşsa onu kullan), `label_ids = (güncel ∪ add) − remove` → `PATCH /cards/{id}`.
   - `create_card`: `POST /cards` → dönen id ile etiket (manage_labels yolu) + checklist POST'ları. Kart oluştu ama ek adım hata verdiyse işlem `executed`, sonuç mesajında "kart oluşturuldu; etiket eklenemedi: …".
8. Sistem mesajı/araç açıklamaları: "Checklist/etiket değişikliği için önce get_card ile id'leri al; maddeyi metinle değil item_id ile işaretle."

### D. "Bu kart" / "bu board" bağlamı
9. Frontend `AssistantPanel.tsx`: `useSearchParams` ile `card` paramını oku; board sayfasındaysa gövdeye `card_id` ekle (`api/assistant.ts` tipi). Panel üstünde küçük bağlam çipi: "Bağlam: «kart adı»" (kart adı board verisinden; yoksa "#id"). Çipte ✕ → o mesaj için bağlamı gönderme.
10. Backend `ChatRequest.card_id: int | None`. `chat.py`: `board_id`/`card_id` varsa `/boards/{id}` ve `/cards/{id}` oku (kullanıcı JWT'si → sahiplik), **gizlilik:** model bulut ve board `local_only` ise bağlam satırı eklenmez. `build_system_prompt(..., focus: str | None)` → "Kullanıcı şu an «Board» board'unda, #42 «Tez yazımı» kartını açık tutuyor; 'bu kart' dediğinde bunu kastediyor." Odaklı planlama yolu (`day_planner`) etkilenmez.

### E. Testler (`services/assistant-service/tests/test_card_content_tools.py`, conftest `FakeTaskApi`'ye checklist/label uçları eklenir)
11. En az: madde ekleme özeti + tekrar elemesi; 20 sınırı; başka kartın item_id'si reddi; update/delete 404 atlama; etiket `_norm` eşleşmesi; eksik etiket oluşturma; yürütme anında birleşme (öneri ile onay arasında kullanıcı etiket eklemiş → kaybolmaz); `create_card` + labels + checklist; gizli (`local_only`) board + bulut model reddi; izin modları (never → araç modele gösterilmez, ask → pending, auto → yürür); `card_id` bağlamı sistem mesajında, local_only + bulutta yok; `get_card` yeni çıktı biçimi.

## Kabul ölçütleri
- Tüm testler yeşil (assistant mevcut + ≥14 yeni; task-api mevcut + 2).
- Ayarlar → Asistan izinleri'nde 3 yeni tür görünür (frontend kodu değişmeden).
- Gerçek model (kullanıcıyla, qwen3.5:4b ve gemma4:26b): (1) "Tez kartının checklist'ine Kaynakça, Özet, Giriş ekle" (2) "Tez kartına Acil etiketi koy" (3) "Tez kartında Kaynakça'yı tamamlandı yap" (4) kart penceresi açıkken "bu karta 'hoca ile görüş' maddesi ekle" → doğru onay kartları. Model "ekledim" uydurursa not düş (bilinen sorun), onay kartı doğruysa kabul.

## Doğrulama
`uv run pytest -q tests/test_card_content_tools.py` → tüm paket; task-api `uv run pytest -q`; `npm run build`; 5175'te panel bağlam çipi ekran görüntüsü.

## İlerleme
**Durum: ✅ Kodlandı (2026-11-08, Sonnet) · ✅ Commit'lendi `6b7e2337f91a7c5ad1511cc8806f0d39cb97a609` (2026-11-09, Haiku; push YAPILMADI). Gerçek-model kabulü kullanıcıyla yapılacak.**
Testler (commit öncesi): task-api 267 geçti · assistant-service 147 geçti · `npm run build` yeşil.

### Yapılanlar
- **A. task-api:** `app/services/palette.py` (`BOARD_PALETTE` + `next_free_color`); `trello.py` buradan import ediyor; `LabelCreate.color` opsiyonel → `BoardService.create_label` board'da kullanılmayan ilk palet rengini seçer (hepsi doluysa ilk renk). `api-schema.d.ts` elle güncellendi. 2 yeni test (`tests/integration/test_boards_cards.py`).
- **B. Okuma:** `get_card` → `checklist_items [{id,text,is_done}]`, `labels [{id,name}]`; `get_board` → `labels [ad]`, kart özetlerinde `labels`. Açıklama güncellendi.
- **C. Yazma:** yeni `app/tools/card_content.py` (araç şemaları, `norm`, etiket çözümü, yürütme yardımcıları). Araçlar: `add_checklist_items`, `update_checklist_items`, `delete_checklist_items`, `set_card_labels`; `create_card` → `labels` + `checklist`. İşlem türleri `edit_checklist`, `manage_labels`, `delete_checklist_items` (Türkçe etiketler `ACTION_TYPES`'ta → Ayarlar UI'ı değişmeden gösterir). Yürütmede kart yeniden okunur (etiket birleşmesi), eksik etiket `POST /boards/{id}/labels {name}` ile açılır (arada oluşmuşsa o kullanılır), 404'lü madde `skipped`. `create_card`'ta etiket/checklist hatası kartı bozmaz, sonuçta `note`.
- **D. "Bu kart" bağlamı:** `ChatRequest.card_id`; `focus_line()` (`agent/context.py`) kullanıcı JWT'siyle okur, bulut modelde `local_only` board/kart için hiçbir şey eklemez; `build_system_prompt(..., focus)`. Frontend: `AssistantPanel` `?card=` okur, "Bağlam: «kart adı»" çipi (✕ ile kapanır), `streamChat` gövdesine `card_id`; `TOOL_LABEL` yeni araçlar.
- **E. Test:** `tests/test_card_content_tools.py` 27 test; `conftest.FakeTaskApi` etiket/checklist uçları kazandı.
- **Sonuçlar:** assistant 147 geçti (120 + 27), task-api 267 geçti (265 + 2), `npm run build` yeşil. 5175'te (task-api-alt 8001) çip DOM'dan doğrulandı: «5 km koşu» kartı açıkken "Bağlam: «5 km koşu»".

### Sapmalar / yapılmayanlar
| Konu | Durum | Neden |
|---|---|---|
| `delete_checklist_items` `delete_tools.py`'de değil `write_tools.py`'de (`_prepare_delete_checklist_items`) | Sapma | Kart/gizlilik yardımcıları (`_card`) `WriteTools`'ta; yürütme `card_content.py`'de. Davranış plana uygun |
| `delete_checklist_items` `ALWAYS_ASK`'e eklenmedi | Bilinçli | Plan istemedi; madde silme küçük/telafili, izin ask/auto/never'a tabi |
| Çipteki ✕ "yalnız o mesaj için" değil, o kart açık kaldığı sürece kapatır | Sapma | Daha basit ve tahmin edilebilir; başka karta geçince çip yeniden gelir |
| Gerçek-model kabul adımları (qwen3.5:4b, gemma4:26b; 4 senaryo) | **Yapılmadı** | Ortak kural: bulut yok, local model denemeleri kullanıcıyla yapılır. Onay kartı içeriği testlerle (FakeProvider) doğrulandı |
| Çip için ekran görüntüsü | **Yapılmadı** | Tarayıcı bölmesi ekran çizemedi (zaman aşımı); doğrulama DOM metniyle yapıldı |
| `ruff check`'te kalan E501 uyarıları | Eski | `trello.py:675`, `services/board.py:226`, `test_boards_cards.py:429` — bu faz öncesinden |
| Commit/push, ana plan commit hash'i | Yapılmadı | Kural: ayrı Haiku oturumu |

Kullanıcı: kod değişti → "Ajanda - Durdur" → "Ajanda".
