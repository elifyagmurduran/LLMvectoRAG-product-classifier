# Configuration & Components Reference

## Table of Contents

- [Config split: config.yaml vs .env](#config-split-configyaml-vs-env)
- [config.yaml — full reference](#configyaml--full-reference)
  - [pipeline](#pipeline)
  - [system](#system)
  - [source](#source)
  - [embedding](#embedding) — config fields + all providers
  - [vector_store](#vector_store) — config fields + all providers
  - [database](#database) — config fields + all providers
  - [row_embedding](#row_embedding)
  - [llm](#llm) — config fields + all providers
  - [classification](#classification)
- [.env — secrets reference](#env--secrets-reference)
- [How to swap a component](#how-to-swap-a-component)

---

## Config split: config.yaml vs .env

| What goes here | File |
|---|---|
| All tunables: batch sizes, thresholds, column names, template paths, retry settings, model dimensions | `config.yaml` |
| All secrets: API keys, endpoints, deployment names, DB server, DB credentials | `.env` |

`config.yaml` is committed to the repository. `.env` is git-ignored and never committed.

Inside `config.yaml` you can reference environment variables using `${VAR_NAME}` syntax. At load time, `load_config()` substitutes these with the actual values from the environment.

---

## config.yaml — full reference

All four component interfaces live in `src/*/base.py`. Each component has a set of ready-to-use implementations and a set of scaffolded implementations (file exists, but methods raise `NotImplementedError`).

**Legend:** ✅ implemented and registered · ⬜ scaffold exists (not yet implemented) · 📄 no scaffold — see implementation guide

### pipeline

```yaml
pipeline:
  name: "gs1-vectoRAG-classifier"
  description: "..."
```

Metadata only. Name is used in log output headers. No functional effect.

---

### system

```yaml
system:
  log_level: "INFO"       # DEBUG | INFO | WARNING | ERROR
  max_workers: 5          # thread pool size for parallel embedding API calls
  batch_size: 256         # fallback batch size (overridden by section-specific batch_size values)
  retry:
    max_attempts: 3       # total attempts (1 initial + 2 retries)
    backoff_factor: 1.5   # multiplier applied to each successive wait
    min_wait: 30.0        # minimum wait between retries (seconds)
    max_wait: 120.0       # maximum wait between retries (seconds)
```

**retry** applies to all Azure OpenAI API calls (both embedding and LLM). With these defaults: first retry waits ~30s, second waits ~45s. Increase `min_wait` and `max_wait` if you hit sustained rate limits.

**log_level:** Set to `DEBUG` to see per-batch timing, individual API call counts, and raw LLM responses. `INFO` is appropriate for production runs.

---

### source

```yaml
source:
  type: "file_json"
  path: "data/input/GS1.json"
  encoding: "utf-8"
  parser: "gs1"
  batch_size: 50
```

Used by: `build-vectors` only.

| Field | Purpose |
|---|---|
| `path` | Path to the GS1 GPC taxonomy JSON file. Relative to the project root. |
| `encoding` | File encoding. `utf-8` works for the standard GS1 GPC export. |
| `batch_size` | Number of documents sent to the embedding API per call. Lower values reduce memory pressure and API request size. Higher values may be faster. |

---

### embedding

**Interface:** `src/services/embedding/base.py` — `EmbeddingProvider`
**Config key:** `embedding.type`
**Used by:** all three modes (`build-vectors`, `embed-rows`, `classify`)

```yaml
embedding:
  type: "azure_openai"
  dimensions: 1024
  batch_size: 256
  max_workers: 5
```

| Field | Purpose |
|---|---|
| `type` | Embedding provider. See [available providers](#embedding-providers) below. |
| `dimensions` | Output vector size. **Must match across all modes.** The FAISS index (`build-vectors`) and the DB row vectors (`embed-rows`) must have the same dimensions. If you switch providers or change dimensions, rebuild the FAISS index and re-run `embed-rows`. |
| `batch_size` | Texts per API call (Azure OpenAI, Cohere) or per local inference batch (HuggingFace, Ollama). |
| `max_workers` | Thread pool size for parallel API calls. Only applies to providers that support parallel calls. |

> **Critical:** All three modes share the same `embedding` section. This guarantees that the GS1 taxonomy vectors (built by `build-vectors`) and the product row vectors (written by `embed-rows`) are always produced by the same model — a requirement for RAG similarity search to be valid. Switching models requires rebuilding the FAISS index (`build-vectors`) and re-running `embed-rows`.

#### Embedding providers

##### ✅ `azure_openai` — Azure OpenAI Embedder
**File:** `src/services/embedding/azure_openai_embedder.py`
**Class:** `AzureOpenAIEmbeddingProvider`

Calls the Azure OpenAI `text-embedding-3-large` deployment (or any other deployment you configure). Uses the `openai` Python SDK with an `AzureOpenAI` client. Batches texts in parallel using `ThreadPoolExecutor`. Retries on `RateLimitError` with configurable exponential backoff.

**When to use:** Default choice. You already have an Azure OpenAI resource. Produces high-quality 1024-dim vectors. Works for both taxonomy (FAISS) and product rows (DB).

```yaml
embedding:
  type: "azure_openai"
  dimensions: 1024
  batch_size: 256
  max_workers: 5
```

Secrets in `.env`: `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`

---

##### ✅ `huggingface` — HuggingFace Local Embedder
**File:** `src/services/embedding/huggingface.py`
**Class:** `HuggingFaceEmbeddingProvider`

Runs a `sentence-transformers` model locally (no API calls, no cost). Model is downloaded from HuggingFace Hub on first use and cached locally. Good for development, testing, or air-gapped environments. No retry logic needed — it's local. Dimensions vary by model (e.g., `all-MiniLM-L6-v2` → 384 dims, `all-mpnet-base-v2` → 768 dims).

**When to use:** Local dev/testing, cost-sensitive runs, or experimenting with different models without spending API credits. Rebuild the FAISS index if you switch models.

```yaml
embedding:
  type: "huggingface"
  dimensions: 384        # must match the chosen model's output dims
  model_name: "all-MiniLM-L6-v2"
```

Common models: `all-MiniLM-L6-v2` (384 dims, fast), `all-mpnet-base-v2` (768 dims, better quality).
No `.env` secrets needed.

---

##### ⬜ `openai` — Direct OpenAI Embedder
**File:** `src/services/embedding/openai_embedder.py`
**Class:** `OpenAIEmbeddingProvider`

Same as the Azure provider but hits the standard OpenAI API (`api.openai.com`) directly. No `azure_endpoint` or `api_version` needed — just an API key. Uses the same `openai` SDK. Useful if you have a direct OpenAI subscription but no Azure OpenAI resource.

```yaml
embedding:
  type: "openai"
  dimensions: 1024
  model: "text-embedding-3-large"
```

Secrets in `.env`: `OPENAI_API_KEY`

---

##### 📄 `ollama` — Ollama Local Embedder
**Implementation guide:** `docs/IMPL_GUIDE_EMBEDDING.md`
**Class:** `OllamaEmbeddingProvider`

Sends embedding requests to a locally running [Ollama](https://ollama.com) server via its REST API (`POST /api/embeddings`). No external API costs. Supports models like `nomic-embed-text` (768 dims) and `mxbai-embed-large` (1024 dims). Requires Ollama to be installed and running.

```yaml
embedding:
  type: "ollama"
  dimensions: 1024
  model_name: "mxbai-embed-large"
  base_url: "http://localhost:11434"
```

No `.env` secrets needed.

---

##### 📄 `cohere` — Cohere Embedder
**Implementation guide:** `docs/IMPL_GUIDE_EMBEDDING.md`
**Class:** `CohereEmbeddingProvider`

Uses the Cohere Embed API. Optimised for retrieval tasks. Supports `search_document` vs `search_query` input type hints.

```yaml
embedding:
  type: "cohere"
  dimensions: 1024
  model: "embed-multilingual-v3.0"
  input_type: "search_document"
```

Secrets in `.env`: `COHERE_API_KEY`

---

### vector_store

**Interface:** `src/services/vectorstore/base.py` — `VectorStore`
**Config key:** `vector_store.type`
**Used by:** `build-vectors` (write), `classify` (read/search)

```yaml
vector_store:
  type: "faiss"
  output_dir: "data/vector_store"
  filename_prefix: "gs1"
  lookup_metadata_fields:
    - level
    - code
    - title
    - hierarchy_path
    - hierarchy_string
```

| Field | Purpose |
|---|---|
| `type` | Vector store implementation. See [available providers](#vector-store-providers) below. |
| `output_dir` | Directory where FAISS artefacts are written and read from. |
| `filename_prefix` | Prefix for all artefact filenames (e.g. `gs1` → `faiss_gs1.index`). |
| `lookup_metadata_fields` | Which metadata fields to include in the compact `{prefix}_lookup.pkl` file loaded at classify time. Omitting fields reduces memory use but makes them unavailable in search results. |

> The vector store is responsible for building from embedded documents, saving all artefacts to disk, loading them back at query time, and executing similarity search. Switching stores means the new implementation handles all of this end-to-end.

#### Vector store providers

##### ✅ `faiss` — FAISS Local Index
**File:** `src/services/vectorstore/faiss_store.py`
**Class:** `FAISSVectorStore`

Builds and queries a Facebook FAISS index stored on local disk. Exact nearest-neighbor search — no approximation. Loads entirely into memory at query time. At build time produces five artefacts in `data/vector_store/`: the binary `.index` file, a `_metadata.json` lookup, a `build_manifest.json`, an `embeddings_{prefix}.parquet` archive, and a `{prefix}_lookup.pkl` compact pickle.

Always uses `IndexFlatL2` (squared L2 distance on L2-normalised vectors). Vectors are normalised in-place for consistent magnitude before indexing and searching. Scores are squared L2 distances in `[0, 4]` for unit vectors — lower = more similar.

**When to use:** Default choice. The GS1 taxonomy has ~200k nodes — FAISS handles this comfortably in memory. Zero infrastructure, no server needed.

```yaml
vector_store:
  type: "faiss"
  output_dir: "data/vector_store"
  filename_prefix: "gs1"
  lookup_metadata_fields: [level, code, title, hierarchy_path, hierarchy_string]
```

---

##### ⬜ `pgvector` — PostgreSQL + pgvector
**File:** `src/services/vectorstore/pgvector_store.py`
**Class:** `PgVectorVectorStore`

Stores vectors directly in a PostgreSQL table using the `pgvector` extension. No additional infrastructure if you already run PostgreSQL. The FAISS index is replaced by a `CREATE INDEX USING hnsw` or `ivfflat` index on the vector column. Search is a SQL query: `ORDER BY embedding <-> $1 LIMIT $k`. Supports filtering by metadata columns alongside the ANN search.

**When to use:** When you want your vector index co-located with your product database, need metadata filtering at search time, or want to avoid loading a full index into memory.

```yaml
vector_store:
  type: "pgvector"
  table: "gs1_taxonomy"
  schema: "vectors"
```

Secrets in `.env`: same PostgreSQL credentials as the `postgresql` database connector.

---

##### 📄 `chromadb` — ChromaDB
**Implementation guide:** `docs/IMPL_GUIDE_VECTORSTORE.md`
**Class:** `ChromaDBVectorStore`

Lightweight vector database that runs either in-process (no server) or as a client-server. Good for development, experimentation, and smaller datasets. Python-native API with built-in metadata filtering. Persistent storage to a local directory.

**When to use:** Quick local prototyping or testing classification without setting up infrastructure. Not recommended for production with large indexes.

```yaml
vector_store:
  type: "chromadb"
  persist_dir: "data/vector_store/chroma"
  collection_name: "gs1_taxonomy"
```

---

##### 📄 `qdrant` — Qdrant
**Implementation guide:** `docs/IMPL_GUIDE_VECTORSTORE.md`
**Class:** `QdrantVectorStore`

Qdrant is a dedicated vector database with strong payload (metadata) filtering, HNSW indexing, and both in-memory and persistent modes. Available as a local server (Docker) or cloud. The `qdrant-client` Python SDK supports uploading, searching, and filtering in one call.

**When to use:** When you need rich metadata filtering on results (e.g., filter by GS1 level, or scope a search to a specific segment), or when you want a purpose-built vector DB with a REST/gRPC API.

```yaml
vector_store:
  type: "qdrant"
  collection_name: "gs1_taxonomy"
  url: "http://localhost:6333"
```

No `.env` secrets needed (add an API key for cloud deployments).

---

##### 📄 `azure_search` — Azure AI Search
**Implementation guide:** `docs/IMPL_GUIDE_VECTORSTORE.md`
**Class:** `AzureAISearchVectorStore`

Uses Azure AI Search (formerly Cognitive Search) as a managed vector store. Upload documents to a search index and query via the `azure-search-documents` SDK. Supports hybrid search (vector + keyword) and built-in filtering. Fully managed, no server to maintain, scales automatically.

**When to use:** Production-grade managed solution in Azure. Useful when the index exceeds available memory, or when hybrid keyword+vector search is needed out of the box.

```yaml
vector_store:
  type: "azure_search"
  index_name: "gs1-taxonomy"
```

Secrets in `.env`: `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_API_KEY`

---

### database

**Interface:** `src/services/db/base.py` — `DatabaseConnector`
**Config key:** `database.type`
**Used by:** `embed-rows` (read + write embeddings), `classify` (read rows + write GS1 columns)

```yaml
database:
  type: "azure_sql"
  schema_name: "playground"
  table: "promo_bronze"
  primary_key: "id"
```

| Field | Purpose |
|---|---|
| `type` | Database connector. See [available connectors](#database-connectors) below. |
| `schema_name` | SQL schema name (e.g. `dbo`, `public`, `playground`). |
| `table` | Table to read from and write to. |
| `primary_key` | Column used as the row identifier in `update_rows()` calls. |

> The connector hides all SQL syntax differences. Azure SQL and PostgreSQL have different vector casting syntax — each connector handles this internally. Azure SQL uses `CAST(CAST(:col AS VARCHAR(MAX)) AS VECTOR(1024))`. PostgreSQL uses `:col::vector(1024)`. When adding a new connector, that connector is responsible for all embedding storage syntax specific to that database.

#### Database connectors

##### ✅ `azure_sql` — Azure SQL (Service Principal)
**File:** `src/services/db/azure_sql_connector.py`
**Class:** `AzureSQLConnector`

Connects to Azure SQL Database using Azure AD Service Principal authentication (`ActiveDirectoryServicePrincipal` via ODBC Driver 18). Uses `pyodbc` + `SQLAlchemy`. Embedding vectors are written using Azure SQL's native `VECTOR(1024)` type with the cast pattern: `CAST(CAST(:col AS VARCHAR(MAX)) AS VECTOR(1024))`. Pagination uses `OFFSET … FETCH NEXT` syntax.

**When to use:** Default. Your production database is Azure SQL. Service Principal auth means no passwords to rotate.

```yaml
database:
  type: "azure_sql"
  schema_name: "playground"
  table: "promo_bronze"
  primary_key: "id"
```

Secrets in `.env`: `AZURE_SQL_SERVER`, `AZURE_SQL_DATABASE`, `AZURE_SQL_CLIENT_ID`, `AZURE_SQL_CLIENT_SECRET`

---

##### ⬜ `postgresql` — PostgreSQL (Username/Password)
**File:** `src/services/db/postgresql.py`
**Class:** `PostgreSQLConnector`

Connects to PostgreSQL using standard username/password auth via `psycopg2` + `SQLAlchemy`. Embedding vectors are written using the `pgvector` extension cast: `:col::vector(1024)`. Pagination uses `LIMIT … OFFSET` SQL. Works with any PostgreSQL 14+ instance (local, cloud, managed).

**When to use:** When your database is PostgreSQL instead of Azure SQL. Change `database.type` in config, set PG env vars, done.

```yaml
database:
  type: "postgresql"
  schema_name: "public"
  table: "promo_bronze"
  primary_key: "id"
```

Secrets in `.env`: `PG_HOST`, `PG_PORT`, `PG_DATABASE`, `PG_USERNAME`, `PG_PASSWORD`

---

##### ⬜ `sqlite` — SQLite
**File:** `src/services/db/sqlite_connector.py`
**Class:** `SQLiteConnector`

Serverless, zero-infrastructure, file-based database. No native vector type — embeddings are stored as `TEXT` (JSON string). The connector handles serialization/deserialization internally. Good for local development and testing without any database server.

**When to use:** Local testing, unit test fixtures, or running the pipeline on a laptop with no database server. Not suitable for production or large datasets.

```yaml
database:
  type: "sqlite"
  db_path: "data/local.db"
  schema_name: ""      # SQLite has no schemas
  table: "promo_bronze"
  primary_key: "id"
```

No `.env` secrets needed.

---

##### 📄 `mysql` — MySQL / MariaDB
**Implementation guide:** `docs/IMPL_GUIDE_DATABASE.md`
**Class:** `MySQLConnector`

Connects via `pymysql` + `SQLAlchemy`. MySQL 9.0+ has a native `VECTOR` type; older versions store embeddings as `LONGTEXT`. Pagination uses `LIMIT … OFFSET` syntax (different from SQL Server / PostgreSQL).

**When to use:** When your existing data warehouse runs on MySQL or MariaDB.

```yaml
database:
  type: "mysql"
  schema_name: "your_schema"
  table: "promo_bronze"
  primary_key: "id"
```

Secrets in `.env`: `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USERNAME`, `MYSQL_PASSWORD`

---

##### 📄 `duckdb` — DuckDB
**Implementation guide:** `docs/IMPL_GUIDE_DATABASE.md`
**Class:** `DuckDBConnector`

Serverless analytical database. Can query Parquet, CSV, or `.duckdb` files. No native vector type. Can query the `data/vector_store/*.parquet` artefacts from `build-vectors`.

**When to use:** Batch analytics, exploring classification results, fast local development.

```yaml
database:
  type: "duckdb"
  db_path: "data/local.duckdb"
  table: "promo_bronze"
  primary_key: "id"
```

No `.env` secrets needed.

---

### row_embedding

```yaml
row_embedding:
  batch_size: 50
  columns:
    - store
    - country
    - product_name
    - product_name_en
    - category
    - packaging_type
    - packaging_value
    - packaging_unit
  separator: " * "
  target_column: "embedding_context"
```

Used by: `embed-rows` only.

| Field | Purpose |
|---|---|
| `batch_size` | Rows processed per DB fetch + embed cycle. |
| `columns` | Columns concatenated to produce the embedding text. Columns are joined in listed order. `NULL` values are treated as empty strings. |
| `separator` | String inserted between column values. Default `" * "` separates fields visually. |
| `target_column` | Column where the embedding vector is written. Must exist in the table. |

The resulting text string (e.g. `"SuperStore * DE * Bio Tomaten * Organic Tomatoes * Fresh Produce * Punnet * 500 * g"`) is what gets embedded. The quality of the RAG search depends on how informative this text is — include columns that describe the product and exclude columns with irrelevant data.

---

### llm

**Interface:** `src/services/llm/base.py` — `LLMProvider`
**Config key:** `llm.type`
**Used by:** `classify` only

```yaml
llm:
  type: "azure_openai"
  max_completion_tokens: 4096
  rate_limit:
    rpm_limit: 30
    tpm_limit: 60000
```

| Field | Purpose |
|---|---|
| `type` | LLM provider. See [available providers](#llm-providers) below. |
| `max_completion_tokens` | Token budget for the LLM response. The classify prompt can be long (up to ~12 candidates × 10 products) — keep this at 4096 or higher. |
| `rate_limit.rpm_limit` | Maximum requests per minute. The rate limiter sleeps proactively before sending a request that would exceed this quota. Set to `0` for unlimited. Find your deployment's RPM limit in the Azure Portal → your OpenAI resource → Deployments → Quotas. |
| `rate_limit.tpm_limit` | Maximum tokens per minute. Same proactive pacing. Set to `0` for unlimited. Find your deployment's TPM limit in the same Azure Portal page. |

**Rate limiting strategy:** The `RateLimiter` (a sliding-window token bucket in `src/utils/rate_limiter.py`) runs *before* each API call. It tracks actual requests and token usage over a 60-second window and sleeps only the minimum time needed to stay within budget. This prevents 429 errors proactively. The tenacity retry decorator (`system.retry.*`) stays as a safety net — if a 429 still occurs, the call is retried with exponential backoff.

> All LLM providers must support forced JSON output. The `classify` mode always calls with `response_format={"type": "json_object"}`. Providers that do not natively support this (e.g. Anthropic) must emulate it via prompt engineering — the orchestrator's regex fallback handles imperfect JSON.

#### LLM providers

##### ✅ `azure_openai` — Azure OpenAI Chat
**File:** `src/services/llm/azure_openai_chat.py`
**Class:** `AzureOpenAILLMProvider`

Calls an Azure-hosted OpenAI chat model (`o4-mini` or any other deployment) via the `openai` SDK's `AzureOpenAI` client. Supports `response_format={"type": "json_object"}`. Retries on `RateLimitError`. Proactive rate limiting via a token-bucket `RateLimiter` that paces requests within configurable RPM and TPM budgets. Returns response content + token usage counts.

**When to use:** Default choice. `o4-mini` gives a good cost/quality tradeoff for structured classification tasks.

```yaml
llm:
  type: "azure_openai"
  max_completion_tokens: 4096
  rate_limit:
    rpm_limit: 30
    tpm_limit: 60000
```

Secrets in `.env`: `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`

---

##### ⬜ `openai` — Direct OpenAI Chat
**File:** `src/services/llm/openai_chat.py`
**Class:** `OpenAILLMProvider`

Same as the Azure provider but targets `api.openai.com` directly. No `azure_endpoint` or `api_version`. Supports the same `response_format` JSON mode. Useful if you have a direct OpenAI subscription but no Azure resource.

```yaml
llm:
  type: "openai"
  model: "gpt-4o-mini"
  max_completion_tokens: 4096
```

Secrets in `.env`: `OPENAI_API_KEY`

---

##### ⬜ `anthropic` — Anthropic Claude
**File:** `src/services/llm/anthropic_chat.py`
**Class:** `AnthropicLLMProvider`

Uses the `anthropic` Python SDK to call Claude models (e.g., `claude-3-5-haiku`, `claude-opus-4`). Anthropic does not have a `response_format` parameter — JSON mode is enforced via prompt instruction and by pre-filling the assistant turn with `{`. The orchestrator's regex fallback handles cases where the JSON is imperfect.

**When to use:** When comparing Claude's classification quality against GPT, or when you have Anthropic credits. Claude follows complex structured instructions well.

```yaml
llm:
  type: "anthropic"
  model: "claude-3-5-haiku-20241022"
  max_completion_tokens: 4096
```

Secrets in `.env`: `ANTHROPIC_API_KEY`

---

##### 📄 `ollama` — Ollama Local LLM
**Implementation guide:** `docs/IMPL_GUIDE_LLM.md`
**Class:** `OllamaLLMProvider`

Sends chat requests to a locally running Ollama server. Ollama exposes an OpenAI-compatible REST API (`/v1/chat/completions`), so this can be implemented with the same `openai` SDK using `base_url="http://localhost:11434/v1"`. Models like `llama3.2`, `mistral`, and `qwen2.5` run locally with no API cost. JSON mode support varies by model.

**When to use:** Fully offline runs, zero-cost experimentation, or testing pipeline logic without spending API credits. Classification quality will be lower than GPT-4o-class models for complex tasks.

```yaml
llm:
  type: "ollama"
  model: "llama3.2"
  base_url: "http://localhost:11434"
  max_completion_tokens: 4096
```

No `.env` secrets needed.

---

##### 📄 `google` — Google Gemini
**Implementation guide:** `docs/IMPL_GUIDE_LLM.md`
**Class:** `GoogleGeminiLLMProvider`

Uses the `google-generativeai` SDK to call Gemini models (`gemini-2.0-flash`, `gemini-2.5-pro`, etc.). Supports structured JSON output via `response_mime_type="application/json"`. Competitive quality and a generous free tier on lower-tier models.

```yaml
llm:
  type: "google"
  model: "gemini-2.0-flash"
  max_completion_tokens: 4096
```

Secrets in `.env`: `GOOGLE_API_KEY`

---

##### 📄 `mistral` — Mistral AI
**Implementation guide:** `docs/IMPL_GUIDE_LLM.md`
**Class:** `MistralLLMProvider`

Uses the `mistralai` Python SDK to call Mistral models (`mistral-small-latest`, `mistral-large-latest`, etc.). Supports `response_format={"type": "json_object"}` on `mistral-small` and `mistral-large`. Strong multilingual support and competitive pricing. Good alternative to GPT for European workloads.

**When to use:** When you want a cost-effective European-hosted LLM with strong multilingual capabilities, or when comparing classification quality across different model families.

```yaml
llm:
  type: "mistral"
  model: "mistral-small-latest"
  max_completion_tokens: 4096
```

Secrets in `.env`: `MISTRAL_API_KEY`

---

##### 📄 `qwen` — Alibaba Qwen
**Implementation guide:** `docs/IMPL_GUIDE_LLM.md`
**Class:** `QwenLLMProvider`

Calls Alibaba's Qwen models via the DashScope API or the OpenAI-compatible endpoint (`https://dashscope.aliyuncs.com/compatible-mode/v1`). Because DashScope exposes an OpenAI-compatible API, this can be implemented using the `openai` SDK with a custom `base_url`. Models like `qwen-plus`, `qwen-turbo`, and `qwen-max` support JSON mode. Strong performance on multilingual and structured tasks.

**When to use:** When comparing classification quality against Western models, when working with CJK product descriptions, or when DashScope pricing is advantageous.

```yaml
llm:
  type: "qwen"
  model: "qwen-plus"
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  max_completion_tokens: 4096
```

Secrets in `.env`: `DASHSCOPE_API_KEY`

---

##### 📄 `deepseek` — DeepSeek
**Implementation guide:** `docs/IMPL_GUIDE_LLM.md`
**Class:** `DeepSeekLLMProvider`

Calls DeepSeek models via their OpenAI-compatible API (`https://api.deepseek.com`). Can be implemented using the `openai` SDK with `base_url="https://api.deepseek.com"`. Models like `deepseek-chat` and `deepseek-reasoner` support JSON output via `response_format={"type": "json_object"}`. Extremely cost-effective with strong reasoning capabilities.

**When to use:** When you want the most cost-effective API option, or when comparing DeepSeek's reasoning-focused models on structured classification tasks. `deepseek-chat` is a good budget alternative to GPT-4o-class models.

```yaml
llm:
  type: "deepseek"
  model: "deepseek-chat"
  base_url: "https://api.deepseek.com"
  max_completion_tokens: 4096
```

Secrets in `.env`: `DEEPSEEK_API_KEY`

---

### classification

```yaml
classification:
  rag_top_k: 30
  batch_size: 10
  prompt_columns:
    - store
    - country
    - product_name
    - product_name_en
    - packaging_type
    - packaging_value
    - packaging_unit
  target_columns:
    - gs1_segment
    - gs1_family
    - gs1_class
    - gs1_brick
    - gs1_attribute
    - gs1_attribute_value
  system_template_file: "templates/gs1_system.j2"
  prompt_template_file: "templates/gs1_classification.j2"
```

Used by: `classify` only.

| Field | Purpose |
|---|---|
| `rag_top_k` | How many nearest FAISS results to retrieve per product. All results are passed to the candidate builder — there is no score threshold filter. 30 is a good default. |
| `batch_size` | Products sent in one LLM call. Each call contains all products in a batch plus their candidate lists. Larger batches reduce API call overhead but make prompts longer. 10 is a practical default. |
| `prompt_columns` | Columns from the DB row that are included in the LLM prompt as product context. These should be the most descriptive fields. Not used by FAISS search — RAG always uses the pre-computed `embedding_context` vector. |
| `target_columns` | Columns written back to the DB after classification. Order matters — these must match the GS1 hierarchy: segment, family, class, brick, attribute, attribute_value. |
| `system_template_file` | Path to the Jinja2 system message template. |
| `prompt_template_file` | Path to the Jinja2 user message template. |

---

## .env — secrets reference

Create a `.env` file in the project root. It is git-ignored. All values are plain strings (no quotes needed unless the value contains spaces).

### Azure OpenAI (embedding + LLM)

```env
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-01
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
AZURE_OPENAI_CHAT_DEPLOYMENT=o4-mini
```

Both the embedding provider and the LLM provider read from these variables. They can point to the same Azure OpenAI resource or different ones.

### Azure SQL Database

```env
AZURE_SQL_SERVER=your-server.database.windows.net
AZURE_SQL_DATABASE=your-database
AZURE_SQL_CLIENT_ID=your-service-principal-client-id
AZURE_SQL_CLIENT_SECRET=your-service-principal-client-secret
```

Authentication uses Azure AD Service Principal (`ActiveDirectoryServicePrincipal` via ODBC Driver 18). No password rotation needed after initial setup.

### PostgreSQL

```env
PG_HOST=your-host
PG_PORT=5432
PG_DATABASE=your-database
PG_USERNAME=your-user
PG_PASSWORD=your-password
```

Only needed if `database.type: "postgresql"` is set in `config.yaml`.

### Other providers (when activated)

| Provider | Required variables |
|---|---|
| `openai` embedding / LLM | `OPENAI_API_KEY` |
| `cohere` embedding | `COHERE_API_KEY` |
| `anthropic` LLM | `ANTHROPIC_API_KEY` |
| `google` LLM | `GOOGLE_API_KEY` |
| `mistral` LLM | `MISTRAL_API_KEY` |
| `qwen` LLM | `DASHSCOPE_API_KEY` |
| `deepseek` LLM | `DEEPSEEK_API_KEY` |
| `azure_search` vector store | `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_API_KEY` |
| `mysql` database | `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USERNAME`, `MYSQL_PASSWORD` |

`huggingface`, `ollama`, `sqlite`, and `duckdb` require no secrets.

---

## How to swap a component

### Switching to an already-implemented provider

1. Change the `type:` key in `config.yaml` to the new value.
2. Add the required secrets to `.env`.
3. Run.

Example — switch from Azure OpenAI embedding to HuggingFace:

```yaml
# config.yaml
embedding:
  type: "huggingface"
  dimensions: 384
  model_name: "all-MiniLM-L6-v2"
```

Then rebuild the FAISS index and re-run embed-rows (dimensions changed):

```bash
python vectorize.py build-vectors
python vectorize.py embed-rows
```

### Activating a scaffold provider

1. Open the scaffold file and implement the abstract methods (they currently raise `NotImplementedError`).
2. Register in `src/factory.py` inside `build_default_factory()`:
   ```python
   from src.services.embedding.openai_embedder import OpenAIEmbeddingProvider
   factory.register_embedding("openai", OpenAIEmbeddingProvider)
   ```
3. Set `type: "openai"` in `config.yaml`.
4. Add secrets to `.env`.

### Adding a brand-new provider

1. Create a new file in the appropriate `src/services/<category>/` directory.
2. Inherit from the ABC in `base.py` and implement all abstract methods.
3. Register and configure as above.
