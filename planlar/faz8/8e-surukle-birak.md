# Faz 8e — Sürükle-bırak: iyimser güncelleme + animasyonlar

**Önerilen model: Sonnet** — kök neden bulundu, adımlar net.

## Kök neden (doğrulandı)
- `apps/web/src/api/boards.ts`: `moveList` (117–121) ve `moveCard` (127–131) yalnız `onSettled: refresh`; `onMutate` yok.
- `BoardPage.tsx:76-85` effect `activeKey` null olunca `columns`/`listOrder`'ı **eski `board.data`'dan** kurar → bırakınca kart eski yerine zıplar, refetch gelince yeni yerine geçer.
- `DragOverlay` varsayılan drop animasyonu; liste sürüklemede overlay yok; `closestCorners`, `PointerSensor(distance 5)`. `index.css:70-78` `prefers-reduced-motion` korunmalı.

## Adımlar
1. **İyimser güncelleme:** `moveCard`/`moveList` `onMutate`: `qc.cancelQueries(keys.board(id))`, önceki veriyi sakla, `qc.setQueryData` ile kartın `list_id` ve `position`'ını (hedef indekse göre komşu pozisyonların ortası; uçlarda ±1) / liste sırasını hemen güncelle. Bitti listesine taşımada `status`/`completed_at`'i de iyimser ayarla. `onError`: geri al + mevcut hata gösterim yolu ("Taşınamadı"). `onSettled`: refresh.
2. `BoardPage` effect: mutasyon sürerken (`useIsMutating({ mutationKey: ['moveCard'| 'moveList'] })` > 0) `columns`'u yeniden kurma; mutasyon anahtarlarını ekle.
3. **Çarpışma:** özel `collisionDetection`: önce `pointerWithin`, boşsa `rectIntersection`; liste sürüklemede yalnız liste droppable'ları. `measuring={{ droppable: { strategy: MeasuringStrategy.Always } }}` (boş listeye bırakma).
4. **Drop animasyonu:** `dropAnimation={{ duration: 200, easing: 'cubic-bezier(0.18,0.67,0.6,1.22)', sideEffects: defaultDropAnimationSideEffects({ styles: { active: { opacity: '0.4' } } }) }}`; `prefers-reduced-motion` → `dropAnimation={null}` (`matchMedia`).
5. **Taşıma hissi:** overlay kartı `rotate(2deg) scale(1.03)` + belirgin gölge, `cursor: grabbing`; yerinde kalan kart kesik çizgili "hayalet" (opacity 0.4, `border-dashed`). Sortable geçişleri `transition: transform 180ms ease`.
6. **Liste overlay'i:** liste sürüklenirken başlık + ilk 3 kartlık özet overlay; yatay `autoScroll` (`threshold: { x: 0.15, y: 0.1 }`, `acceleration` makul).
7. Kapsam dışı: `PlanEditor`, Takvim kenar paneli.

## Kabul ölçütleri / Doğrulama (5175, kopya DB)
- 3 liste × ~30 kart (test verisi script'le, kopya DB'de): listeler arası, aynı liste içi, boş listeye, bitti listesine bırakma → geri zıplama yok.
- DevTools ağ yavaşlatma (Slow 3G — `read_network_requests` ile kontrol) altında da zıplama yok.
- task-api kapalıyken bırakma → kart eski yerine döner + hata mesajı.
- Liste sürüklemede overlay görünür. `npm run build` temiz; konsol hatasız. Kısa GIF/ekran görüntüleri.

## İlerleme
**Durum:** kod tamam, commit edilmedi (2026-11-09). Migration yok.

### Yapılanlar
- `api/boards.ts`: `moveCard`/`moveList` → `mutationKey` + `onMutate` (`cancelQueries`, önceki veriyi sakla, `setQueryData`), `onError` geri alma, `onSettled` refresh. Saf yardımcılar `applyCardMove` (komşu pozisyon ortası, uçlarda ±1, bitti listesine taşımada `status=completed`/`completed_at`, listeden çıkarken `pending`/`null`) ve `applyListMove` dışa aktarıldı.
- `BoardPage.tsx`: effect, taşıma sürerken (`useIsMutating` + yerel `pendingMoves` sayacı) `columns`/`listOrder`'ı yeniden kurmaz → geri zıplama yok; özel `collisionDetection` (`pointerWithin` → `rectIntersection`; liste sürüklemede yalnız liste droppable'ları; kartta kart isabeti öncelikli); `MeasuringStrategy.Always`; `autoScroll` (threshold x 0.15 / y 0.1); `dropAnimation` (200 ms, cubic-bezier, `defaultDropAnimationSideEffects`), `prefers-reduced-motion` → `null`; `onDragCancel` `dragOrigin`'i de sıfırlar.
- `KanbanList.tsx`: kart ve liste sortable geçişi 180 ms ease; sürüklenen kartın yerinde kesik çizgili hayalet (opacity 0.4); yeni `ListOverlay` (başlık + ilk 3 kart + "+N kart daha").
- `CardFace.tsx`: overlay kartı `rotate-2 scale-[1.03] cursor-grabbing` + belirgin gölge.

### Sapmalar
| Plan | Yapılan | Neden |
|---|---|---|
| Hata yolu: mevcut "Taşınamadı" gösterimi | Mevcut `m.moveCard.error` mesajı korundu (API'nin hata metni); `moveList` hatası ekrana yazılmıyor, yalnız geri alınıyor | Mevcut gösterim yalnız `moveCard.error`'a bağlıydı; kapsam dışı bırakıldı |
| `useIsMutating` ile koruma | + yerel `pendingMoves` sayacı | `mutate()` çağrısı ile `isMutating` güncellemesi arasında bir render'da effect eski veriden kurup zıplama yaratabilirdi |
| Kart sürüklemede yalnız `pointerWithin`→`rectIntersection` | Kart isabeti varsa kartlar, yoksa liste hedefi seçilir | Liste bölümü de isabet aldığından kart hedefi ikinci sıraya düşebiliyordu |
| Tarayıcı doğrulaması (5175, 3×30 kart) | **Yapılmadı** | `.env` kopya DB'yi garanti etmiyor; gerçek DB riski, uykudaki oturumda kopya kurulumu yapılmadı |

### Doğrulanmayanlar
- **Arayüz tarayıcıda hiç görülmedi:** listeler arası/aynı liste/boş liste/bitti listesine bırakma, Slow 3G, task-api kapalıyken geri alma + hata mesajı, liste overlay'i, drop animasyonu, reduced-motion. Yalnız `tsc -b && vite build` temiz ve `applyCardMove`/`applyListMove` izole betikle (node, 9 doğrulama) sınandı.
- Konsol hatası denetlenmedi, GIF/ekran görüntüsü alınmadı.
- `moveList` iyimser sırası sunucunun `move_list` indeks anlamıyla aynı varsayıldı (arka uç kodu okunmadı; refresh sonrası sunucu sırası kazanır).

### Test sayıları
- task-api: 333 geçti · assistant-service: 152 geçti · `npm run build` temiz (yeni test yok; web'de test koşucusu yok).
