# web — React arayüzü

React + TypeScript + Vite, TanStack Query, Zustand, Tailwind v4, React Router.

## Çalıştırma

Tüm sistemi birlikte başlatmak için repo kökünden:

```powershell
./scripts/dev.ps1
```

Sadece frontend:

```powershell
npm install
npm run dev        # http://localhost:5173  (/api -> http://localhost:8000 proxy)
```

## API tipleri

task-api ayaktayken OpenAPI şemasından TypeScript tipleri üretilir:

```powershell
npm run gen:api    # src/lib/api-schema.d.ts
```

## Yerel test hesabı

Yerel SQLite veritabanında (`services/task-api/task_management.db`) geliştirme sırasında oluşturulmuş test hesabı:

- E-posta: `dev@example.com`
- Şifre: `devpassword123`

Sadece yerel geliştirme içindir. `.test` / `.local` gibi özel alan adları e-posta doğrulamasından geçmez; test hesaplarında `example.com` kullan.
