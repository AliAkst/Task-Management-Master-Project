# assistant-service — kişisel AI asistan

Modelden bağımsız LLM katmanı + task-api üzerinden araç kullanan sohbet asistanı.

## Çalıştırma

```powershell
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8100
```

Gereksinimler: task-api 8000'de çalışıyor olmalı; local modeller için [Ollama](https://ollama.com).
Frontend `/api/v1/assistant` isteklerini Vite proxy ile buraya yönlendirir.

## Mimari

```
POST /api/v1/assistant/chat (SSE)
  → JWT task-api /auth/me ile doğrulanır
  → ToolBox (okuma araçları; task-api REST, kullanıcının kendi token'ı)
  → ContextBuilder (kısa sistem mesajı: tarih/saat, board'lar, kronometre, bugünün planı)
  → run_agent: model stream → araç çağrısı → sonuç modele → … (en fazla 6 tur)
  → mesajlar assistant.db'ye (conversations, messages)
```

- `app/llm/types.py` — nötr tipler (`Msg`, `ToolSpec`, `ToolCall`, `ChatChunk`). Uygulamanın geri kalanı sadece bunları görür.
- `app/llm/ollama_provider.py` — Ollama **native** `/api/chat` (bkz. aşağıdaki ölçüm).
- `app/llm/openai_provider.py` — OpenAI ve OpenAI-uyumlu servisler.
- `app/llm/registry.py` — model listesi (Ollama modelleri otomatik keşfedilir) ve provider üretimi.
- Claude adaptörü, yazma araçları + izin/onay akışı, kullanıcı hafızası: **Faz 5**.

## Gizlilik

- Model bulut ise `local_only` board'ların verisi (board, kart, takvim, plan, istatistik satırları) araç sonuçlarından çıkarılır (`app/tools/privacy.py`).
- Local modelle üretilmiş mesajlar (gizli veri içerebilir) aynı sohbette bulut modele geçilse bile **gönderilmez**; arayüz bunu bildirir.

## Ölçülen kararlar (RTX 4060 Laptop, 8 GB VRAM)

| Ayar | Ölçüm | Karar |
|---|---|---|
| Düşünme modu | Aynı kısa soru: kapalı 56 token, açık 2.347 token (~2× süre) | Sohbette **kapalı** (`OLLAMA_THINK=false`) |
| Bağlam penceresi | Varsayılan 262K: 4B model 14.3 GB, %38 GPU. `num_ctx=16384`: 3.6 GB, %100 GPU | **16K** (`OLLAMA_NUM_CTX`) |
| `/v1` (OpenAI-uyumlu) uç nokta | `num_ctx`'i yok sayıyor | Ollama için **native API** adaptörü |

Model karşılaştırması: `uv run python -m scripts.benchmark_models` → `benchmark_results/` (rapor, puanlama alanlarıyla).

## Ayarlar (.env)

| Değişken | Varsayılan |
|---|---|
| `TASK_API_URL` | `http://localhost:8000/api/v1` |
| `OLLAMA_URL` | `http://localhost:11434` |
| `OLLAMA_NUM_CTX` | `16384` |
| `OLLAMA_THINK` | `false` |
| `DEFAULT_MODEL` | `ollama:qwen3.5:4b` |
| `OPENAI_API_KEY`, `OPENAI_MODELS` | boş (ör. `OPENAI_MODELS=["gpt-..."]`) |
