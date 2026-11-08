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
_(oturum sonunda doldurulur)_
