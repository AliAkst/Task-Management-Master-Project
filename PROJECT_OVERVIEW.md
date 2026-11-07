# Task Management Master Project — Proje Dokümantasyonu

> **Oluşturma Tarihi:** 2026-11-07  
> **Durum:** Aktif Geliştirme (Kişisel Kullanım)

---

## İçindekiler

1. [Proje Genel Bakış](#1-proje-genel-bakış)
2. [Mimari](#2-mimari)
3. [Servisler](#3-servisler)
4. [Teknoloji Stack'i](#4-teknoloji-stacki)
5. [Klasör Yapısı](#5-klasör-yapısı)
6. [API Endpoint'leri](#6-api-endpointleri)
7. [Veri Modelleri](#7-veri-modelleri)
8. [Temel Tasarım Desenleri](#8-temel-tasarım-desenleri)
9. [Altyapı ve Çalıştırma](#9-altyapı-ve-çalıştırma)
10. [Test Yapısı](#10-test-yapısı)
11. [Konfigürasyon](#11-konfigürasyon)
12. [Bilinen Sorunlar ve Eksikler](#12-bilinen-sorunlar-ve-eksikler)

---

## 1. Proje Genel Bakış

Kişisel kullanım için geliştirilmiş bir **Task (Görev) Yönetim API**'si. Temel amacı To-Do yönetimi olmakla birlikte, proje aynı zamanda modern mikroservis mimarisi, event-driven iletişim ve production-grade dayanıklılık (resilience) pattern'lerini öğrenmek/uygulamak için bir platform olarak kullanılmaktadır.

### Neler Yapılabiliyor

- Kullanıcı kaydı ve JWT tabanlı kimlik doğrulama (access + refresh token)
- Görev oluşturma, listeleme, güncelleme, silme
- Görev filtreleme (durum, öncelik, metin arama) ve sayfalama
- Her işlemde RabbitMQ → notification-service üzerinden bildirim gönderme (email/webhook simülasyonu)
- Redis ile response caching (TTL: 300sn)
- Kural tabanlı rate limiting (Token Bucket, 100 req/60sn)
- Request bazlı correlation ID ile distributed tracing

---

## 2. Mimari

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT (HTTP)                            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │  task-api   │  FastAPI · Port: ?
                    │             │
                    │ Middleware: │
                    │  - CorrelationId (UUID per request)
                    │  - RateLimit  (Token Bucket / Redis)
                    └──┬──────┬───┘
                       │      │
              ┌────────▼┐    ┌▼──────────────┐
              │PostgreSQL│   │  Redis Cache  │
              │(SQLAlchemy│   │  TTL: 300s    │
              │  async)  │   │  Token Bucket │
              └──────────┘   └───────────────┘
                       │
                 ┌─────▼─────┐
                 │   Dapr    │  Sidecar · Port: 3500
                 │ Pub/Sub   │  Component: taskpubsub
                 └─────┬─────┘
                       │  RabbitMQ AMQP
                       │  Exchange: task_events (TOPIC)
                       │  Routing: task.*
                 ┌─────▼──────────────┐
                 │ notification-service│  FastAPI · Dapr Subscriber
                 │                    │
                 │  /dapr/subscribe   │  ← Dapr'a subscription bildirir
                 │  /events/task      │  ← Event gelince burası çağrılır
                 │                    │
                 │  Handlers:         │
                 │   task.created     │  → Email + Webhook simülasyonu
                 │   task.updated     │  → Email simülasyonu
                 │   task.deleted     │  → Email simülasyonu
                 │   task.completed   │  → Email + Webhook simülasyonu
                 └────────────────────┘

  NOT: notification-service ayrıca doğrudan RabbitMQ consumer (consumer.py)
  da içeriyor. Şu an Dapr subscriber (main.py) kullanılıyor.
  consumer.py ise DLQ (Dead Letter Queue) destekli bağımsız consumer.
```

### Veri Akışı (Örnek: Task Oluşturma)

```
POST /api/v1/tasks/
  → CorrelationIdMiddleware (UUID üret, context'e kaydet)
  → RateLimitMiddleware (Redis'ten token bucket kontrol)
  → get_current_user (JWT decode → DB'den kullanıcı getir)
  → TaskService.create()
      → DB'ye kaydet (PostgreSQL)
      → Redis cache invalidate (tasks:user:{id}:*)
      → TaskEventPublisher → Dapr sidecar HTTP → RabbitMQ
  → ApiResponse{success: true, data: TaskResponse}
```

---

## 3. Servisler

### 3.1 task-api

Ana iş mantığını barındıran servis.

| Katman | Dosya(lar) | Sorumluluk |
|--------|-----------|------------|
| **API** | `app/api/v1/tasks.py` | Task CRUD endpoint'leri |
| **API** | `app/api/v1/auth.py` | Register, Login, Refresh, /me |
| **API** | `app/api/v1/health.py` | Liveness / Readiness probe |
| **API** | `app/api/dependencies.py` | FastAPI Dependency Injection tanımları |
| **Service** | `app/services/task.py` | Task iş mantığı (cache + DB + event) |
| **Service** | `app/services/auth.py` | Kayıt, giriş, token yenileme mantığı |
| **Repository** | `app/db/repositories/base.py` | Generic CRUD + retry decorator |
| **Repository** | `app/db/repositories/task.py` | Task-specific sorgular |
| **Repository** | `app/db/repositories/user.py` | User-specific sorgular |
| **Repository** | `app/db/repositories/specifications.py` | Specification pattern filtreleri |
| **UoW** | `app/db/unit_of_work.py` | Transaction yönetimi (commit + refresh) |
| **Entity** | `app/db/entities/task.py` | SQLAlchemy Task modeli |
| **Entity** | `app/db/entities/user.py` | SQLAlchemy User modeli |
| **Entity** | `app/db/entities/base.py` | Base + TimestampMixin |
| **Core** | `app/core/security.py` | bcrypt hash + JWT encode/decode |
| **Core** | `app/core/cache.py` | Redis async client wrapper |
| **Core** | `app/core/cache_keys.py` | Cache key oluşturma fonksiyonları |
| **Core** | `app/core/messaging.py` | RabbitMQ client (aio-pika) |
| **Core** | `app/core/events.py` | TaskEventPublisher (Dapr üzerinden) |
| **Core** | `app/core/dapr_client.py` | Dapr Service Invocation client |
| **Core** | `app/core/dapr_pubsub.py` | Dapr Pub/Sub HTTP client |
| **Core** | `app/core/resilience.py` | Retry, CircuitBreaker, Bulkhead, Timeout, FeatureFlag |
| **Core** | `app/core/rate_limiter.py` | Token Bucket rate limiter |
| **Core** | `app/core/middleware.py` | RateLimitMiddleware |
| **Core** | `app/core/correlation.py` | CorrelationIdMiddleware + ContextVar |
| **Core** | `app/core/health.py` | DB / Redis / Disk health check'leri |
| **Core** | `app/core/logging.py` | Structured logging + CorrelationIdFilter |
| **Core** | `app/core/exceptions.py` | Tüm custom exception sınıfları |
| **Core** | `app/core/handlers.py` | AppException → HTTP response dönüştürücü |
| **Models** | `app/models/task.py` | TaskCreate, TaskUpdate, TaskResponse, TaskFilter |
| **Models** | `app/models/user.py` | UserCreate, UserLogin, UserResponse, TokenResponse |
| **Models** | `app/models/common.py` | ApiResponse[T], PaginatedResponse[T], PaginationParams |
| **Models** | `app/models/events.py` | TaskEventType (enum), TaskEvent (dataclass) |
| **Config** | `app/config.py` | Pydantic Settings (env dosyasından yükleme) |

### 3.2 notification-service

Görev event'lerini dinleyen ve bildirim gönderen servis.

| Dosya | Sorumluluk |
|-------|-----------|
| `app/main.py` | FastAPI app, `/dapr/subscribe`, `/events/task` endpoint'leri |
| `app/handlers.py` | `handle_task_created/updated/deleted/completed` fonksiyonları |
| `app/consumer.py` | Bağımsız RabbitMQ consumer (DLQ + retry destekli) |
| `app/config.py` | RabbitMQ bağlantı ayarları (os.getenv tabanlı) |

> **İki mod:** `main.py` Dapr subscriber olarak çalışır (öncelikli). `consumer.py` ise doğrudan RabbitMQ'ya bağlanan, DLQ destekli bağımsız consumer; Dapr olmadan çalışabilmek için alternatif.

---

## 4. Teknoloji Stack'i

| Kategori | Teknoloji | Versiyon |
|----------|-----------|---------|
| **Dil** | Python | ≥ 3.12 |
| **Web Framework** | FastAPI | ≥ 0.128 |
| **ASGI Server** | Uvicorn | ≥ 0.40 |
| **ORM** | SQLAlchemy (async) | ≥ 2.0 |
| **Veritabanı** | PostgreSQL | 16 (Docker) |
| **Migration** | Alembic | ≥ 1.18 |
| **Cache** | Redis (asyncio) | 7 (Docker) |
| **Message Broker** | RabbitMQ | 3.13 (Docker) |
| **Servis Mesh** | Dapr | Sidecar (HTTP 3500) |
| **HTTP Client** | httpx (async) | — |
| **Message Client** | aio-pika | ≥ 9.4 |
| **Auth** | PyJWT + bcrypt | — |
| **Validation** | Pydantic v2 | ≥ 2.12 |
| **Settings** | pydantic-settings | ≥ 2.12 |
| **Resilience** | tenacity | ≥ 8.2 |
| **Linter** | ruff | ≥ 0.14 |
| **Type Check** | mypy | ≥ 1.19 |
| **Test** | pytest + pytest-asyncio | — |
| **Test HTTP** | httpx (ASGITransport) | — |
| **Test DB** | SQLite (aiosqlite) | — |
| **Paket Yöneticisi** | uv | — |

---

## 5. Klasör Yapısı

```
Task-Management-Master-Project/
├── infrastructure/
│   ├── dapr/
│   │   ├── components/
│   │   │   ├── pubsub.yaml       # Dapr pub/sub component (RabbitMQ)
│   │   │   ├── secretstore.yaml  # Secret store tanımı
│   │   │   └── statestore.yaml   # State store tanımı
│   │   └── secrets.json          # Dapr secrets
│   └── docker/
│       └── docker-compose.yml    # PostgreSQL + Redis + RabbitMQ
│
└── services/
    ├── task-api/
    │   ├── alembic/
    │   │   └── versions/         # Migration dosyaları
    │   ├── app/
    │   │   ├── api/
    │   │   │   ├── dependencies.py
    │   │   │   └── v1/
    │   │   │       ├── auth.py
    │   │   │       ├── tasks.py
    │   │   │       └── health.py
    │   │   ├── core/             # Altyapı bileşenleri
    │   │   ├── db/
    │   │   │   ├── entities/     # SQLAlchemy modelleri
    │   │   │   └── repositories/ # Repository + Specification
    │   │   ├── models/           # Pydantic şemaları
    │   │   ├── services/         # İş mantığı
    │   │   ├── config.py
    │   │   └── main.py
    │   └── tests/
    │       ├── conftest.py
    │       ├── integration/
    │       │   ├── test_auth.py
    │       │   └── test_tasks.py
    │       └── unit/
    │           ├── test_models.py
    │           └── test_security.py
    │
    └── notification-service/
        └── app/
            ├── config.py
            ├── consumer.py       # Bağımsız RabbitMQ consumer
            ├── handlers.py       # Event handler fonksiyonları
            ├── main.py           # Dapr subscriber (FastAPI)
            └── monitor.py
```

---

## 6. API Endpoint'leri

Base URL: `http://localhost:{port}/api/v1`

### Auth

| Method | Endpoint | Auth | Açıklama |
|--------|----------|------|---------|
| POST | `/auth/register` | ❌ | Yeni kullanıcı kaydı |
| POST | `/auth/login` | ❌ | Giriş → access + refresh token |
| POST | `/auth/refresh` | ❌ | Refresh token ile yeni token çifti |
| GET | `/auth/me` | ✅ Bearer | Giriş yapan kullanıcı bilgileri |

### Tasks

| Method | Endpoint | Auth | Açıklama |
|--------|----------|------|---------|
| POST | `/tasks/` | ✅ Bearer | Görev oluştur |
| GET | `/tasks/` | ✅ Bearer | Görevleri listele (filtre + sayfalama) |
| GET | `/tasks/{task_id}` | ✅ Bearer | Belirli görevi getir |
| PUT | `/tasks/{task_id}` | ✅ Bearer | Görevi güncelle |
| DELETE | `/tasks/{task_id}` | ✅ Bearer | Görevi sil (204) |

**GET /tasks/ Query Parametreleri:**
- `status`: `pending` / `in_progress` / `completed`
- `priority`: `low` / `medium` / `high`
- `search`: başlık veya açıklamada metin arama
- `page`: sayfa numarası (default: 1)
- `page_size`: sayfa başı kayıt (1-100, default: 10)

### Health

| Method | Endpoint | Açıklama |
|--------|----------|---------|
| GET | `/health` | Genel sağlık durumu (DB + Redis + Disk) |
| GET | `/health/live` | Liveness probe |
| GET | `/health/ready` | Readiness probe |

### Response Formatı

Tüm başarılı yanıtlar `ApiResponse[T]` sarmalında gelir:
```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "timestamp": "2026-11-07T10:00:00Z"
}
```

Hata yanıtı:
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "Task with id 99 not found"
  }
}
```

---

## 7. Veri Modelleri

### Veritabanı Tabloları

#### users
| Kolon | Tip | Kısıt |
|-------|-----|-------|
| id | int | PK, auto |
| email | varchar(255) | UNIQUE, INDEX |
| hashed_password | varchar(255) | — |
| full_name | varchar(100) | nullable |
| is_active | bool | default: true |
| is_superuser | bool | default: false |
| created_at | timestamptz | auto |
| updated_at | timestamptz | auto |

#### tasks
| Kolon | Tip | Kısıt |
|-------|-----|-------|
| id | int | PK, auto |
| user_id | int | FK → users.id |
| title | varchar(200) | — |
| description | varchar(1000) | nullable |
| status | enum | pending / in_progress / completed |
| priority | enum | low / medium / high |
| due_date | timestamptz | nullable |
| created_at | timestamptz | auto |
| updated_at | timestamptz | auto |

### Event Modeli

```python
@dataclass(frozen=True)
class TaskEvent:
    event_type: TaskEventType   # task.created / .updated / .deleted / .completed
    task_id: int
    user_id: int
    timestamp: datetime
    correlation_id: str | None
    data: dict | None
```

### Cache Key Formatları

| Amaç | Format |
|------|--------|
| Görev listesi | `tasks:user:{id}:list:{status}:{priority}:{search}:{page}` |
| Görev detayı | `tasks:user:{id}:detail:{task_id}` |
| Rate limit | `ratelimit:{ip_adresi}` |
| Invalidation pattern | `tasks:user:{id}:*` |

---

## 8. Temel Tasarım Desenleri

### Repository + Specification Pattern
`BaseRepository[T]` → tüm CRUD işlemleri + retry decorator.
Filtreler `Specification` soyut sınıfından türetilir ve `query.where(...)` zinciri olarak uygulanır.

```
TaskUserSpecification   → user_id'ye göre filtrele
TaskStatusSpecification → status'e göre filtrele
TaskPrioritySpecification
TaskSearchSpecification → ilike (başlık + açıklama)
PaginationSpecification → offset + limit
OrderBySpecification    → asc/desc sıralama
AndSpecification        → iki specification'ı birleştir
```

### Unit of Work Pattern
`TaskUnitOfWork` → tek transaction altında `TaskRepository` + `UserRepository`.
Commit sonrası tüm nesneler `session.refresh()` ile DB'den güncellenir.

### Resilience Patterns (`core/resilience.py`)

| Decorator / Sınıf | Ne Yapar |
|-------------------|---------|
| `@with_db_retry` | DB işlemleri için 3 deneme, exponential backoff |
| `@with_retry(...)` | Özelleştirilebilir retry |
| `@with_sync_retry` | Senkron fonksiyonlar için retry |
| `CircuitBreaker` | CLOSED → OPEN → HALF_OPEN geçişleri. Threshold aşılınca istekleri reddeder |
| `@with_circuit_breaker(breaker)` | Circuit breaker decorator |
| `Bulkhead` | Semaphore tabanlı eşzamanlılık limiti |
| `@with_bulkhead(bulkhead)` | Bulkhead decorator |
| `@with_timeout(seconds)` | asyncio.wait_for sarmalı timeout |
| `@with_fallback(...)` | Hata durumunda alternatif değer/fonksiyon |
| `FeatureFlag` | Runtime'da özellik açma/kapatma |
| `@with_feature_flag(flag)` | Flag kapalıysa fonksiyonu atla |
| `@with_resilience(...)` | Bulkhead + Timeout + CircuitBreaker + Retry birlikte |

**Global instance'lar:**
- `db_circuit_breaker`, `redis_circuit_breaker`
- `db_bulkhead` (max 10, timeout 5s), `redis_bulkhead` (max 50, timeout 1s), `external_api_bulkhead`
- `cache_feature`, `ai_feature`, `notifications_feature`

### Event-Driven Mimari
Task işlemleri sonrası `TaskEventPublisher` Dapr sidecar'a HTTP POST atar. Dapr, event'i `taskpubsub` component'i üzerinden RabbitMQ'ya iletir. `notification-service` Dapr subscriber olarak `/events/task` endpoint'inde dinler.

### Dependency Injection
FastAPI `Depends()` ile:
- `get_db_session` → `TaskUnitOfWork` → `TaskService` / `AuthService`
- `get_current_user` → JWT decode → DB lookup → `UserEntity`
- `CurrentUserDep`, `TaskServiceDep`, `AuthServiceDep` type alias olarak tanımlı

---

## 9. Altyapı ve Çalıştırma

### Docker Compose

```bash
cd infrastructure/docker
docker compose up -d
```

Başlatılan servisler:
| Servis | Port | Kullanıcı / Şifre |
|--------|------|-----------------|
| PostgreSQL | 5432 | postgres / postgres |
| Redis | 6379 | — |
| RabbitMQ | 5672 (AMQP), 15672 (UI) | taskuser / taskpass |

### task-api'yi Çalıştırma

```bash
cd services/task-api
cp .env.example .env   # .env.example'ı düzenle
uv run uvicorn app.main:app --reload
```

### Dapr ile Çalıştırma

```bash
dapr run \
  --app-id task-api \
  --app-port 8000 \
  --dapr-http-port 3500 \
  --components-path ../../infrastructure/dapr/components \
  -- uv run uvicorn app.main:app --port 8000
```

### notification-service Dapr Subscriber

```bash
dapr run \
  --app-id notification-service \
  --app-port 8001 \
  --dapr-http-port 3501 \
  --components-path ../../infrastructure/dapr/components \
  -- uv run uvicorn app.main:app --port 8001
```

---

## 10. Test Yapısı

**Test veritabanı:** SQLite in-memory (aiosqlite) — test çalışırken otomatik oluşturulur ve silinir.  
**Test HTTP client:** `httpx.AsyncClient` + `ASGITransport` — gerçek HTTP sunucusu gerekmez.  
**Fixture zinciri:** `test_engine` → `test_session` → `client` → `test_user` → `auth_headers`

### Test Kategorileri

#### Integration Tests (`tests/integration/`)

| Dosya | Test Sınıfları |
|-------|---------------|
| `test_tasks.py` | TestCreateTask, TestGetTasks, TestGetTaskById, TestUpdateTask, TestDeleteTask, TestTaskAuthorization |
| `test_auth.py` | Register, Login, Refresh testleri |

**TestTaskAuthorization** özellikle önemli: başka kullanıcının görevine erişim / güncelleme / silme girişimleri test edilir.

#### Unit Tests (`tests/unit/`)

| Dosya | Kapsam |
|-------|--------|
| `test_models.py` | Pydantic model validasyon testleri |
| `test_security.py` | hash_password, verify_password, create_access_token, decode_token |

### Testleri Çalıştırma

```bash
cd services/task-api
uv run pytest --cov=app tests/
```

---

## 11. Konfigürasyon

`services/task-api/app/config.py` — Pydantic Settings, `.env` dosyasından okur.

| Parametre | Default | Açıklama |
|-----------|---------|---------|
| `app_name` | "Task Management API" | — |
| `debug` | false | Debug modu |
| `database_url` | SQLite (local) | Prod'da PostgreSQL |
| `jwt_secret_key` | "super-secret-key..." | **Mutlaka değiştir** |
| `jwt_access_token_expire_minutes` | 30 | — |
| `jwt_refresh_token_expire_days` | 7 | — |
| `redis_host` | localhost | — |
| `cache_ttl_seconds` | 300 | 5 dakika |
| `rate_limiting_requests` | 100 | Pencere başına max istek |
| `rate_limit_window_seconds` | 60 | Rate limit penceresi |
| `retry_max_attempts` | 3 | DB retry sayısı |
| `circuit_breaker_failure_threshold` | 5 | Kaç hatadan sonra açılsın |
| `circuit_breaker_recovery_timeout` | 30 | Kaç saniye açık kalsın |
| `feature_cache_enabled` | true | Redis cache feature flag |
| `feature_notifications_enabled` | true | Bildirim feature flag |

---

## 12. Bilinen Sorunlar ve Eksikler

### Buglar

1. **`messaging.py` — `health_check` metodu** (`services/task-api/app/core/messaging.py:115`)  
   `self` parametresi eksik: `async def health_check()` → `async def health_check(self)` olmalı.  
   Şu an bu metod çağrılmıyor, ancak ileride çağrılırsa `NameError: name 'self' is not defined` hatası verir.

2. **`dapr_client.py` — `get_correlation_id` çağrısı** (`services/task-api/app/core/dapr_client.py:96`)  
   `correlation_id = get_correlation_id` → parantez eksik, fonksiyon çağrılmıyor, obje atanıyor.  
   Doğrusu: `correlation_id = get_correlation_id()`.

3. **`dapr_client.py` — `response.json` çağrısı** (satır 123)  
   `return response.json if response.content else {}` → `response.json()` olmalı (parantez eksik).

4. **`dapr_client.py` — Convenience metotları** (satır 151-165)  
   `get`, `post`, `put`, `delete` fonksiyonları `DaprClient` sınıfı dışında tanımlanmış, bağımsız fonksiyon gibi görünüyor ama `self` kullanıyor. Sınıfın içine alınmalı.

5. **`notification-service/app/config.py` — `rabbitmq_password` tip hatası** (satır 14)  
   `rabbitmq_password: int = os.getenv(...)` → `str` olmalı.

6. **`cache.py` — `date.isoformat` çağrısı** (satır 24)  
   `return obj.isoformat` → `return obj.isoformat()` olmalı (parantez eksik).

### Eksikler / Yapılacaklar

- [ ] `notification-service`: Email ve webhook entegrasyonları simülasyon, gerçek implementasyon yok
- [ ] `app/servicess/user_client.py` — klasör adı yanlış (`servicess`), içerik boş/taslak
- [ ] `README.md` — boş
- [ ] `dapr_client.py` convenience metotları sınıf dışında kalmış
- [ ] Rate limiter şu an IP bazlı; JWT `user_id` bazlı güncellenmesi için `middleware.py`'de yorum var
- [ ] `FeatureFlag` class'ı global dict kullanıyor — uygulama restart'ta sıfırlanır (Redis'e taşınabilir)
- [ ] `notification-service/app/monitor.py` — boş/taslak
- [ ] `RabbitMQClient` ve `DaprPubSubClient` aynı anda `messaging.py` ve `dapr_pubsub.py`'de var; `TaskEventPublisher` şu an Dapr kullanıyor ama `messaging.py`'deki `rabbitmq_client` hâlâ `main.py`'de bağlanıyor (gereksiz bağlantı)
