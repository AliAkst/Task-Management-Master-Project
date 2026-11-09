# Task Management — AI Destekli Yaşam ve Görev Yönetimi

Trello benzeri kanban panoları, takvim ve bir yapay zekâ asistanını tek uygulamada birleştiren kişisel görev/yaşam yönetim platformu. Asistan, panolarınızı ve takviminizi okuyabilir; izin verdiğiniz işlemleri sizin adınıza yapabilir.

## Özellikler

- **Kanban panoları:** pano, liste ve kartlar; sürükle-bırak ile taşıma, alt kartlar ve kart bağımlılıkları
- **Kart ekleri** ve **Markdown not editörü**
- **Takvim ve günlük plan**, zaman takibi (kronometre), istatistikler
- **Entegrasyonlar:** Google Takvim, Microsoft Takvim ve Microsoft To Do (OAuth), Trello içe aktarma
- **Teams toplantıları:** etkinliklere toplantı bağlantısı
- **Yapay zekâ asistanı:** local (Ollama) ve bulut (OpenAI, Anthropic) modeller; araç kullanımı, izin/onay akışı, kullanıcı hafızası
- **Gizlilik:** bulut modele gidildiğinde `local_only` panoların verisi gönderilmez
- **Sesli dikte** (mikrofon düğmesi) ve **koyu tema**

## Mimari

```
apps/web                  React 19 + Vite + TypeScript (TanStack Query, Zustand, Tailwind)   :5173
services/task-api         FastAPI + SQLAlchemy + SQLite (Alembic)                            :8000
services/assistant-service FastAPI, modelden bağımsız LLM katmanı (SSE sohbet)               :8100
services/notification-service  RabbitMQ tüketicisi (opsiyonel)
```

Frontend, `/api` isteklerini Vite proxy ile servislere yönlendirir. Docker gerekmez: task-api SQLite ile çalışır; Redis ve RabbitMQ yoksa önbellek ve olay bildirimleri devre dışı kalır, uygulama çalışmaya devam eder. (`infrastructure/docker/docker-compose.yml` isteğe bağlı PostgreSQL/Redis/RabbitMQ içindir.)

## Gereksinimler

- Python 3.12+ ve [uv](https://docs.astral.sh/uv/)
- Node.js ve npm
- Local modeller için [Ollama](https://ollama.com) (isteğe bağlı)

## Kurulum ve çalıştırma

Tüm sistemi tek komutla (Windows PowerShell):

```powershell
./scripts/dev.ps1
```

Ya da servisleri ayrı ayrı:

```bash
# task-api  → http://localhost:8000/docs
cd services/task-api
cp .env.example .env          # değerleri düzenleyin
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# assistant-service → http://localhost:8100/docs
cd services/assistant-service
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8100

# web → http://localhost:5173
cd apps/web
npm install
npm run dev
```

Ayrıntılar: [apps/web](apps/web/README.md), [assistant-service](services/assistant-service/README.md), [notification-service](services/notification-service/README.md).

## Yapılandırma

Ortam değişkenleri `services/task-api/.env.example` dosyasında listelenmiştir (JWT, veritabanı, RabbitMQ/Redis, Google ve Microsoft OAuth istemcileri). Gerçek değerleri `.env` dosyasına yazın; `.env` repoya eklenmez. Asistan ayarları için `services/assistant-service/README.md` dosyasına bakın.

## Testler

```bash
cd services/task-api && uv run pytest -q
cd services/assistant-service && uv run pytest -q
cd apps/web && npm run build     # tsc + vite build
cd apps/web && npm run lint
```

## Lisans

Henüz bir lisans dosyası eklenmemiştir; lisans seçilene kadar tüm haklar saklıdır.
