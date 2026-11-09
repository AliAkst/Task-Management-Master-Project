# Faz 8g — Dark mode + uygulama zemini + board arka planı

**Önerilen model: Sonnet.** Palet ve belirteç değerleri Opus tarafından aşağıda verildi; Sonnet uygular, toplu dönüşümü yapar, sonunda `frontend-design` skill'iyle eleştiri turu yapar. Sonuç görsel olarak kötüyse (kullanıcı beğenmezse) ayrı kısa Opus tasarım eleştirisi oturumu.

**Ön koşul:** 8a–8f bitti (yeni bileşenler de dönüşsün).

## Mekanizma
- `<html data-theme="light|dark" data-paper="kagit|krem|adacayi|lavanta|gri">`. `index.css`: `@custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *));`.
- Tailwind v4 yardımcıları `var(--color-…)` kullandığı için `[data-theme=dark]` altında değişkenleri yeniden tanımlamak tüm uygulamayı çevirir. `color-scheme: light` / `dark` html'de.
- **Parlama yok:** `index.html` `<head>`'de satır içi script: localStorage `ajanda.theme` / `ajanda.paper` → `data-theme` (system ise `matchMedia`), `data-paper`. Sunucu tercihi gelince eşitlenir; "Sistem" seçiliyken `matchMedia` değişimi dinlenir. `lib/theme.ts`: `applyTheme(theme, paper)`.

## Palet (Opus)
**Koyu mürekkep skalası** (`[data-theme=dark]`):
| değişken | değer | rol |
|---|---|---|
| slate-50 | `#0f1422` | gece zemini |
| slate-100 | `#1a2134` | ince dolgu/hover |
| slate-200 | `#262e45` | çizgi |
| slate-300 | `#363f5a` | güçlü çizgi |
| slate-400 | `#5d6684` | ikon/placeholder |
| slate-500 | `#858da9` | ikincil metin (~5:1 zeminde) |
| slate-600 | `#a5adc5` | soluk metin |
| slate-700 | `#c4cadb` | |
| slate-800 | `#dbe0ec` | |
| slate-900 | `#edf0f7` | mürekkep (metin) |
| slate-950 | `#f8f9fc` | |
| surface | `#161c2d` | kart/panel zemini |
| on-ink | `#0f1422` | açık "mürekkep" düğme üstü yazı |
| blue-50 / 100 | `#1b2350` / `#25306a` | |
| blue-500 / 600 / 700 | `#8196f6` / `#97a8ff` / `#b8c3ff` | bağlantı/odak (koyuda açılır) |
| rec | `#f0606d` | |

**Durum renkleri:** kodda kullanılan `green-*`, `amber-*`, `red-*` tonlarını `grep` ile çıkar; koyuda zemin tonları (`*-50/100`) koyu doygun karşılık (`green-50 #10261b`, `amber-50 #2a2110`, `red-50 #2d151a`), metin tonları (`*-600/700/800`) açık karşılık (`green-700 #74d6a0`, `amber-700/800 #f2c46a`, `red-600/700 #ff8f95`). Her biri `[data-theme=dark]` altında değişken olarak.

**Kod renkleri (8b'deki `--code-*`) koyu:** bg `#1a2134`, fg `#edf0f7`, comment `#858da9`, keyword `#c39bff`, string `#7fd6a3`, number `#f5b26b`, title `#97a8ff`, attr `#ff9cc9`, meta `#a5adc5`.

**Uygulama zemini (data-paper)** — yalnız `--color-slate-50` (sayfa zemini) değişir; surface ve mürekkep aynı kalır:
| anahtar | açık | koyu |
|---|---|---|
| kagit (varsayılan) | `#f2f4f8` | `#0f1422` |
| krem | `#f6f2e9` | `#18150f` |
| adacayi | `#edf3ee` | `#101a15` |
| lavanta | `#f1eff8` | `#16142a` |
| gri | `#f1f1f2` | `#141416` |

**Board arka planı (`boards.background`, hazır anahtarlar):** `null`/`none` (zemin), `tint` (board rengi %10, `color-mix` ile zemine), `deniz` (`linear-gradient(135deg,#d7e6f5,#eaf1f9)`), `orman` (`#dfeadf→#eef4ec`), `gunbatimi` (`#f7e1d3→#f6ecdf`), `alacakaranlik` (`#e3def3→#efeaf7`), `kum` (`#efe7d6→#f6f1e6`), `grafit` (`#dfe2e8→#eceef2`). Koyu temada her biri `color-mix(in srgb, <renk> 22%, var(--color-slate-50))` ile otomatik koyulaşır (CSS değişkeni `--board-bg` + `[data-theme=dark]` kuralı). Liste sütunları `bg-slate-100/90` + `backdrop-blur-sm` ile okunur kalır.

## Adımlar
1. **Migration** `<rev>_theme_settings.py` (`down_revision` = 8d'nin): `user_settings.theme` String(10) default `system`, `user_settings.background` String(20) default `kagit`, `boards.background` String(20) nullable. Modellerde `Literal` doğrulama. Yedek + kopyada upgrade/downgrade/upgrade. Testler: ayar kaydı/geçersiz değer 422, board background (task-api +4).
2. `index.css`: yukarıdaki dark değişkenleri, paper değişkenleri, `--board-bg` kuralları, durum ve kod renkleri, `color-scheme`, `.fc` (`--fc-page-bg-color` ve `--fc-button-bg-color` → `var(--color-surface)`, aktif düğme yazısı `var(--color-on-ink)`), `.react-flow` (`#fff` → surface).
3. **Toplu dönüşüm** (her dosyayı gözle; ~30 dosya):
   - `bg-white` → `bg-surface` (hepsi; `bg-white/xx` → `bg-surface/xx`).
   - `text-white` **yalnız** `bg-slate-700/800/900/950` ya da `bg-blue-600/700` zeminlerde → `text-on-ink` (hover varyantları dahil). Board rengi (inline style), `bg-rec`, `bg-red-*`, `bg-green-*` üstündeki `text-white` aynen kalır.
   - Arka plan perdeleri `bg-black/xx` aynen kalır (koyu temada da koyu olmalı; `bg-slate-950/xx` perde varsa `bg-black/xx`'e çevir).
   - TSX içindeki sabit hex/`#fff` (Recharts, `StatsPage`, dataviz paleti, inline style): `hooks/useThemeColors.ts` — tema değişince `getComputedStyle(document.documentElement)` ile değişkenleri okuyup döndürür; grafik paleti `--chart-1…n` değişkenlerine taşınır (açık değerler mevcut palet, koyuda aynı tonların açık varyantları).
   - Kalan kontrol: `grep -rn "bg-white\|#fff\b\|#ffffff\|text-white" apps/web/src` çıktısı yalnız bilinçli istisnalar.
4. **Etiket çipleri:** `lib/color.ts` `readableTextOn(hex)` (WCAG göreli parlaklık → `#0f1422` ya da `#ffffff`); etiket ve board renkli sekmelerde kullan.
5. **UI:** Ayarlar → yeni **"Görünüm"** bölümü (sol bölüm menüsüne): `Segmented` Sistem/Açık/Koyu; 5 zemin örneği (seçili halka); anında kaydetme (mevcut Ayarlar deseni) + localStorage. Sol rayda hızlı tema düğmesi (Ay/Güneş; tıklayınca açık↔koyu açık seçim). `BoardForm`: "Arka plan" örnek kutucukları (8 anahtar); `BoardPage` kanban alanına uygular.
6. `frontend-design` skill'iyle eleştiri turu: iki temada 1440 px ekran görüntüleri — Bugün, Board (arka planlı ve arka plansız), Kart penceresi (kod bloklu not + ekler), Takvim, İlişkiler, İstatistik, Ayarlar, Profil, Asistan paneli, Giriş. Kontrast: metin ≥ 4.5:1 (mürekkep/zemin, slate-500/surface, blue-600/surface, durum metinleri) — küçük bir Node betiğiyle değişken çiftleri hesaplanır, sonuç ilerleme bölümüne.

## Kabul ölçütleri
- Sistem/Açık/Koyu anında değişir, yenilemede parlama yok; başka cihazda (başka tarayıcı profili) sunucu tercihi gelir.
- Listelenen tüm sayfalar koyu temada okunur; `bg-slate-900` düğmeler koyuda açık zemin + koyu yazı; takvim, grafik, ilişki görünümü, kod blokları koyu.
- 5 zemin ve 8 board arka planı iki temada çalışır; liste sütunları okunur.
- task-api testleri yeşil (+4), `npm run build` temiz, grep kontrolü temiz.

## İlerleme
**Durum:** kod tamam, commit edildi `7ad066f` (2026-11-09, push edilmedi). Migration `c7f1a9d3b5e2_theme_settings` (down = `b6d2f8a4c1e9`), DB kopyasında upgrade → downgrade → upgrade denendi. Testler: task-api 337 passed (+4 `tests/integration/test_theme.py`), assistant-service 152 passed, `npm run build` temiz.

### Yapılanlar
- **Backend:** `user_settings.theme` (String(10), `system`) ve `background` (String(20), `kagit`), `boards.background` (nullable). Pydantic `Literal` doğrulama (geçersiz değer 422): tema `system|light|dark`, zemin `kagit|krem|adacayi|lavanta|gri`, board arka planı `none|tint|deniz|orman|gunbatimi|alacakaranlik|kum|grafit`. `api-schema.d.ts` elle güncellendi.
- **`index.css`:** `@custom-variant dark`, `[data-theme=dark]` altında tüm skala/surface/on-ink/mavi/durum (green/amber/red/indigo)/`--code-*`/`--chart-*` değişkenleri, `data-paper` zeminleri (açık+koyu), `.board-bg` arka plan kuralları (koyuda `color-mix` %22, `tint` %10/%18), `.fc` ve `.react-flow` `#fff` → surface/on-ink.
- **`index.html`** satır içi betik (parlamasız ilk boyama), `lib/theme.ts` (`applyTheme`, `useTheme`, sistem teması dinleme), `hooks/useThemeSync.ts` (sunucu tercihi → yerel; `useSaveTheme`), `hooks/useThemeColors.ts`, `lib/color.ts` (`readableTextOn`).
- **Toplu dönüşüm:** `bg-white` → `bg-surface` (tümü); `text-white` → `text-on-ink` (slate-700/900, blue-600/700 ve ayrıca green/amber/red katı dolguları, çünkü bu tonlar koyuda açılıyor); etiket/board çiplerinde `readableTextOn`; Modal perdesi `bg-slate-900/40` → `bg-black/40`; GraphView ip renkleri CSS değişkenine, handle kenarı `border-surface`; StatsPage renkleri `useThemeColors`; CalendarPage deadline `var(--color-surface)`.
- **UI:** Ayarlar → "Görünüm" (Sistem/Açık/Koyu `Segmented` + 5 zemin örneği, anında uygular, sunucuya ve localStorage'a yazar); sol rayda Ay/Güneş hızlı düğmesi; `BoardForm` "Arka plan" (8 örnek); `BoardPage` kanban alanı `board-bg`, liste sütunları `bg-slate-100/90 backdrop-blur-sm`.

### Tarayıcı doğrulaması (8001/5175, DB kopyası, `dev@example.com`)
Koyu: Board (arka planlı Deniz), İlişkiler, Kart penceresi, Takvim, İstatistik (grafikler), Bugün, Ayarlar, Board formu görüldü; açık: Board (Deniz). Zemin `lavanta` seçimi sunucuya yazıldı, yenilemede koyu+lavanta parlamasız geldi; hızlı düğme açık↔koyu çalıştı. Bulunan/giderilen: React Flow kontrol düğmeleri koyuda beyaz kalıyordu (xyflow stili lazy yüklenip `.react-flow` özgüllüğünü eziyordu) → seçici `.react-flow.react-flow`.

### Kontrast (Node betiği, WCAG)
| çift | açık | koyu |
|---|---|---|
| mürekkep/zemin | 14.67 | 16.10 |
| slate-500/surface | 4.62 | 5.15 |
| slate-500/zemin | **4.20** | 5.58 |
| blue-600/surface | 7.57 | 7.56 |
| yeşil/kırmızı/amber metin/surface | 5.02 / 6.47 / 7.09 | 9.59 / 7.77 / 10.40 |
| kırmızı/red-50, amber/amber-50 | 5.91 / 6.84 | 7.79 / 9.73 |
| on-ink/slate-900 düğme | 16.15 | 16.10 |
Açık temada slate-500 sayfa zemini (slate-50) üzerinde 4.20 ve krem/adaçayı/lavanta/gri zeminlerde 4.06–4.14 (<4.5): **8g öncesinden gelen** değer, plan açık palete dokunmuyor; denetimde karar verilsin (slate-500'ü `#656e8d` civarına koyulaştırmak yeter).

### Sapmalar
| Plan | Yapılan | Neden |
|---|---|---|
| `text-white` yalnız slate/blue-600/700 üstünde → `text-on-ink`; green/red üstünde aynen kalır | green/amber/red katı dolgular (`bg-green-600/700`, `bg-amber-600`, `bg-red-700`) da `text-on-ink` | Koyuda bu tonlar açık (#74d6a0 vb.); beyaz yazı okunmazdı. `bg-rec` üstü beyaz kaldı |
| Durum renkleri koyu tonları | Plandaki değerlere ek olarak green-100/600/800, amber-100/300/400/500/600/900/950, red-100/500, indigo-50/100/700, blue-800/900 tanımlandı | Kodda kullanılan tüm tonlar koyuda ters dönsün |
| Etiket/board çipinde beyaz yazı | `readableTextOn` (CardModal, BoardPage, CalendarPage çipleri + takvim olay yazısı) | Plan adım 4 |
| GraphView renkleri `useThemeColors` | `var(--chart-ok/warn)` / `var(--color-slate-400)` doğrudan | SVG stroke CSS değişkeni kabul ediyor, kanca gereksiz |
| `.react-flow` seçicisi | `.react-flow.react-flow` | Yukarıdaki özgüllük sorunu |
| Modal perdesi | `bg-slate-900/40` → `bg-black/40` | Koyuda slate-900 açık renk; perde açık olurdu |
| Hızlı tema düğmesi | Düğme sunucuya da kaydeder (`useSaveTheme`) | "Başka cihazda gelir" ölçütü |
| `frontend-design` eleştiri turu ve 1440 px tam ekran görüntü seti | Kısmen: kopya portta ekranlar gözle kontrol edildi; Giriş, Profil, Asistan paneli (yalnız açık görüldü), Boards sayfası, board arka planlarının 8'i ve 5 zeminin her biri tek tek görülmedi; `frontend-design` skill'i çağrılmadı | Uykuda oturum, zaman |

### Doğrulanmayanlar
- Giriş, Profil, Kart penceresinde kod bloklu not + ekler, EventDialog, Reminders, DayReviewForm, İnsights, Entegrasyon ayarları koyuda görülmedi (yalnız sınıf dönüşümü yapıldı). 8 board arka planından yalnız `deniz` iki temada görüldü; `tint` ve diğerleri CSS'ten.
- "Sistem" seçiliyken işletim sistemi teması canlı değişimi (matchMedia dinleyicisi) denenmedi; ilk açılışta sistem koyuydu ve doğru çözüldü.
- Başka tarayıcı profilinde sunucu tercihinin gelmesi (useThemeSync) yalnız aynı tarayıcıda yenilemeyle görüldü.
- Gerçek DB'ye migration uygulanmadı (kullanıcı "Ajanda - Durdur" → "Ajanda" yapınca çalışır; öncesinde gerçek DB yedeği alınmalı).

