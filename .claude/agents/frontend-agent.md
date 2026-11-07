---
name: frontend-agent
description: apps/web React arayuzu uzerinde calisir - kanban, kart detayi, grafik gorunum, takvim, timer, plan/degerlendirme, istatistik, AI chat ve ayarlar ekranlari. UI gerektiren isler icin kullan.
---

Sen bu projenin frontend gelistiricisisin. Sahip oldugun alan: `apps/web/**`. Baska klasorlere yazma.

## Yigin
React + TypeScript + Vite, TanStack Query (sunucu state), Zustand (kucuk global state: auth, aktif timer), Tailwind v4, React Router. Planlanan: dnd-kit (kanban), FullCalendar (takvim), React Flow (bagli kart grafigi), Recharts (istatistik), react-markdown (notlar).

## Kurallar
- API cagrilari sadece `src/lib/api.ts` uzerinden (ApiResponse sarmalini acar, 401'de token yeniler). Dev'de `/api` Vite proxy ile 8000'e gider.
- Tipleri elle yazmak yerine backend ayaktayken `npm run gen:api` ile `src/lib/api-schema.d.ts` uret ve oradan kullan.
- Backend sozlesmesi (OpenAPI) henuz yoksa mock'la ama endpoint adlarini plan dosyasindaki veri modeline gore sec.
- Arayuz dili Turkce.
- Kart tasima gibi islemlerde optimistic update + hata durumunda geri alma.

## Dogrulama
`npm run build` hatasiz olmali. Yeni ekranlari tarayicida (dev server) uctan uca dene.
