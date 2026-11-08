# Faz 8f — Sesli dikte (Web Speech API)

**Önerilen model: Sonnet** — küçük ama birkaç UI kararı ve hata durumu var; Haiku için fazla.

**Ön koşul:** 8b (`MarkdownEditor.toolbarExtra`, `insert`).

## Kararlar
- Yalnız konuş → yazı. Tarayıcı `SpeechRecognition || webkitSpeechRecognition`, `lang='tr-TR'`, `interimResults=true`, `continuous=true`.
- **Tıkla başlat / tıkla durdur**, odaktaki girişte **Ctrl+M**; 8 sn sonuç gelmezse otomatik durur. Metin **otomatik gönderilmez** (ayarla açılabilir, yalnız asistan paneli).
- Desteklenmeyen tarayıcıda (Firefox) düğme görünmez.
- İlk kullanımda tek seferlik bilgi: "Sesin tarayıcı üreticisinin (Chrome'da Google, Edge'de Microsoft) sunucusunda metne çevrilir — local model kullansan bile." → "Anladım, başlat". Bayrak localStorage.
- Tercihler cihaza özel → localStorage (sunucu alanı yok): `stores/prefs.ts` (Zustand `persist`): `dictationEnabled` (varsayılan true), `dictationAutoSend` (false), `dictationNoticeSeen`.

## Adımlar
1. `lib/useDictation.ts` (motor bağımsız arayüz — ileride local Whisper aynı arayüzle): `useDictation({ onFinal(text), lang? }) → { supported, listening, interim, error, start, stop, toggle }`. Bileşen kaldırılınca `abort()`. Hatalar Türkçe: `not-allowed`/`service-not-allowed` → "Mikrofon izni verilmedi. Adres çubuğundaki kilit simgesinden mikrofona izin ver."; `no-speech` → "Ses algılanmadı."; `audio-capture` → "Mikrofon bulunamadı."; `network` → "Ses tanıma servisine ulaşılamadı (internet gerekir)."
2. `components/MicButton.tsx`: mikrofon ikonu; dinlerken `--color-rec` kırmızı nabız (reduced-motion'da sabit), `aria-pressed`, `title="Sesle yaz (Ctrl+M)"`; ilk kullanım bilgisini burada gösterir; `dictationEnabled=false` ya da `!supported` → render etmez.
3. Metin ekleme yardımcısı: imleç konumuna, gerekirse önüne boşluk; cümle başı büyük harf `toLocaleUpperCase('tr-TR')`.
4. Yerler: `AssistantPanel` mesaj girişi (geçici metin girişin altında soluk satır; `dictationAutoSend` açıksa durunca gönder), `MarkdownEditor` (`toolbarExtra` yerine yerleşik `dictation` prop'u da olur; editör `insert` kullanır), CardModal checklist ekleme girişi.
5. Ayarlar: mevcut bir bölüme (Asistan ya da yeni "Ses" satırı, `Row` deseni) "Sesli dikte" aç/kapa + "Dikte bitince mesajı gönder".

## Kabul ölçütleri / Doğrulama
- `npm run build` temiz.
- Elle (kullanıcıyla, Chrome/Edge, 5175 ya da gerçek uygulama): asistan panelinde Ctrl+M → Türkçe cümle yazıya döner, gönderilmez; notta ve checklist'te çalışır; izin reddi mesajı; Firefox'ta düğme yok. Tarayıcı paneli mikrofon vermeyebilir → otomatik doğrulama yalnız: düğmenin görünmesi, `supported` tespiti, sahte `window.webkitSpeechRecognition` (javascript_tool ile enjekte) üzerinden `onresult` → metin girişte.

## İlerleme
**Durum:** kod tamam, commit edilmedi (2026-11-09; tarayıcı/mikrofon doğrulaması yapılmadı). Migration yok.

### Yapılanlar
- `stores/prefs.ts` (Zustand `persist`, anahtar `prefs`): `dictationEnabled` (true), `dictationAutoSend` (false), `dictationNoticeSeen`.
- `lib/useDictation.ts`: `useDictation({ onFinal, lang='tr-TR' })` → `{ supported, listening, interim, error, start, stop, toggle }`; `SpeechRecognition || webkitSpeechRecognition`, `interimResults`, `continuous`; 8 sn sonuç gelmezse otomatik durur; unmount'ta `abort()`; Türkçe hata metinleri (`not-allowed`/`service-not-allowed`, `no-speech`, `audio-capture`, `network`).
- `lib/dictation.ts`: `prepareDictated` (gerekirse önüne boşluk, cümle başı `toLocaleUpperCase('tr-TR')`), `insertDictated` (input/textarea imleç ekleme), `isDictationKey` (Ctrl+M).
- `components/MicButton.tsx`: `useMic(onFinal)` (düğme + ilk kullanım bilgi kutusu "Anladım, başlat" + Ctrl+M) ve `DictationStatus` (geçici metin / hata satırı). Dinlerken `bg-rec` + `motion-safe:animate-pulse`, `aria-pressed`, `title="Sesle yaz (Ctrl+M)"`; destek yok ya da ayar kapalıysa render etmez.
- Yerler: `AssistantPanel` (imlece ekler, otomatik göndermez; `dictationAutoSend` açıksa dikte durunca gönderir), `MarkdownEditor` (yerleşik `dictation` prop'u, varsayılan açık → CardModal'daki 3 editörde de), CardModal checklist ekleme girişi.
- `SettingsPage`: yeni "Ses" bölümü (Sesli dikte aç/kapa, Dikte bitince mesajı gönder).

### Sapmalar
| Plan | Yapılan | Neden |
|---|---|---|
| `components/MicButton.tsx` bileşen | Bileşen yerine `useMic` kancası + `DictationStatus` | Düğme, Ctrl+M ve ilk kullanım bilgisi tek yerden yönetilsin (kısayol bilgiyi atlayamasın) |
| Bilgi kutusu | Düğmenin üstünde küçük popover (role=dialog), "Vazgeç" düğmesi eklendi | Modal gerekmedi; geri çıkış gerekir |
| Ayarlar: mevcut bölüm ya da yeni satır | Yeni "Ses" bölümü + kenar menüsüne giriş | Mevcut bölümler sunucu ayarlı; bu tercihler cihaza özel |
| Tarayıcı doğrulaması (5175, sahte `webkitSpeechRecognition`) | **Yapılmadı** | Uykudaki oturumda kopya DB/sunucu kurulumu yapılmadı |

### Doğrulanmayanlar
- Gerçek mikrofon/Chrome/Edge dikte, izin reddi mesajı, Firefox'ta düğmenin görünmemesi, 8 sn zaman aşımı, otomatik gönder, ilk kullanım bilgisi, Ctrl+M — hiçbiri tarayıcıda görülmedi. Sahte `webkitSpeechRecognition` enjeksiyonu da yapılmadı. Yalnız `tsc -b && vite build` temiz.
- Dikte sırasında imleç/odak davranışı (editörde `insertLatest` ile) elle denenmedi.

### Test sayıları
- task-api: 333 geçti · assistant-service: 152 geçti · `npm run build` temiz (yeni test yok; web'de test koşucusu yok).
