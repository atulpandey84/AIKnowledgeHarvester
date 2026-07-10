# Enterprise Knowledge Harvester v2

Welcome to the **Enterprise Knowledge Harvester v2**—a production-grade, modular, high-performance Python application designed to continuously discover, collect, clean, and archive technical knowledge and news articles from the web. It builds a completely self-contained, offline-ready searchable knowledge base designed as a core ingestion backend for Local AI platforms (such as local LLMs, RAG pipelines, or Agentic systems).

Developed using Clean Architecture principles, this enterprise-grade pipeline scales gracefully to millions of documents, executes concurrent tasks concurrently, maintains clean attribution, and generates AI-friendly structured schemas with zero cloud dependencies.

---

## Key Features

- **Continuous Topic Management**: Monitored categories and keywords defined in `.topics.txt` featuring weights, comments, and prioritization (`[High]`, `[Medium]`, `[Low]`).
- **Provider-Independent Search**: Pluggable search layer supporting RSS feed queries, DuckDuckGo HTML scraping, SearXNG, and automatic result scoring, merging, and deduping.
- **Robust Downloader**: Built-in HTTPDownloader with connection pooling (HTTP/2), compression (gzip/deflate/brotli), randomized browser User-Agent rotation, robots.txt awareness, and Retry-After rate-limiting compliance.
- **Dynamic Search Constraints**: Option to dynamically restrict web search results to specific target websites (e.g. `ubuntu.com`, `python.org`), managed seamlessly via CLI and REST API.
- **Auto-Healing & Self-Pruning**: Built-in resilience that automatically intercepts connection and host-resolution errors (such as `[Errno -2] Name or service not known`). It dynamically prunes dead RSS feeds or broken website restrictions from the YAML configuration, ensuring long-term continuous unattended runs.
- **Domain-Specific Adaptive Rate-Limiting**: Intelligently tracks delay intervals and request timestamps for individual domains. When encountering a `403 Forbidden` or `429 Too Many Requests` status, the downloader rotates the User-Agent, backs off, scales up domain delays to prevent blocking, and gracefully cools delays down once success is restored.
- **Noise-Free Content Extraction**: Utilizes Trafilatura with a BeautifulSoup4-based fallback cleaner to strip cookies, popups, newsletter prompts, header/footer elements, and menus.
- **Local Asset Isolation**: Downloads images locally (under `images/`), discards tracking pixels/icons, and rewrites HTML links to maintain absolute offline compatibility.
- **Full PDF Parsing**: Automated PDF detection, text extraction, HTML preview generation, and original document archiving.
- **Beautiful Document Generation**: Automatically produces:
  - Responsive, dark-mode `article.html` with structured tables and syntax highlights.
  - LLM-ready `article.md` (Markdown format).
  - Machine-readable `article.json` containing the full article text and structured metadata.
  - `metadata.json` tracking SHA256 hashes, harvested timestamps, author, keyword arrays, reading time, and categories.
  - `summary.md` detailing executive summaries, bulleted highlights, and short/long summaries.
- **Deduplication Engine**: Identifies exact and near-duplicate articles via SHA256 hashes and URL normalization before storing.
- **SQLite Database Index**: A high-performance structured database to query cached metadata, download stats, images, and keywords.
- **Local Embedding Generation**: Out-of-the-box support for Ollama models (e.g. `nomic-embed-text` or `bge-large`) with deterministic, robust vector fallbacks to ensure flawless offline indexing.
- **Dual Operational Interfaces**:
  - **CLI Control Panel**: Rich CLI built with Click (`harvester run`, `harvester stats`, `harvester doctor`, etc.).
  - **REST API Server**: High-performance FastAPI server to execute search queries, view statistics, and retrieve serialized JSON outputs.

---

## Architectural Layout

```
KnowledgeHarvester/
│
├── harvester/
│   ├── config/             # YAML/JSON & Environment Variable configurations
│   ├── core/               # Data Models, parsing rules, and Topic Management
│   ├── crawler/            # HTTPDownloader with UA rotation and rate limiting
│   ├── search/             # Multi-provider search adapters & relevance scoring
│   ├── rss/                # Multi-feed RSS manager
│   ├── extractor/          # Trafilatura / BeautifulSoup webpage & PDF extraction
│   ├── storage/            # Local folder structure layout and image downloading
│   ├── database/           # SQLite schema, indexing, and transactional lookups
│   ├── embeddings/         # Ollama and fallback vector embeddings
│   ├── logging_util/       # Rotating JSON structured file & stream logger
│   ├── api/                # FastAPI endpoint routes
│   └── cli/                # Command-line commands and subcommands
│
├── tests/                  # Pytest unit and integration suite
├── config.yaml             # Main configuration file
└── .topics.txt             # Target watchlist topics
```

---

## Getting Started

### Prerequisites

- **Python**: v3.12 or newer.
- **Ollama** (Optional): Run `ollama serve` and fetch an embedding model (e.g., `ollama pull nomic-embed-text`) to enable AI embeddings.

### Installation

1. **Clone and Install in Editable Mode**:
   ```bash
   pip install -e .
   ```

2. **Verify Dependencies**:
   Ensure `h2` is installed to support secure HTTP/2 downloads:
   ```bash
   pip install h2
   ```

---

## Configuration & Setup

### 1. Main Configuration: `config.yaml`
Settings can be fully customized directly in the `config.yaml` file at the repository root, or overridden via environment variables prefixed with `HARVESTER_` (e.g. `HARVESTER_THREAD_COUNT=8`).

```yaml
base_storage_path: "KnowledgeBase"
database_path: "KnowledgeBase/harvester.db"
thread_count: 4
timeout: 30.0
retry_count: 3
scheduling_interval_seconds: 3600
logging_level: "INFO"
download_images: true
max_image_size_bytes: 5242880
min_image_dimension: 100
max_articles_per_topic: 10
minimum_article_length_words: 100
max_crawl_depth: 2
rate_limiting_delay_seconds: 1.0
search_providers:
  - "rss"
  - "duckduckgo"
ignored_domains:
  - "doubleclick.net"
  - "googleadservices.com"
allowed_domains: []
search_websites: []
embedding_model: "nomic-embed-text"
ollama_base_url: "http://localhost:11434"
vector_db_type: "sqlite"
llm_enabled: false
llm_model: "llama3"
summarization_enabled: true
summarization_settings:
  short_len: 150
  long_len: 500
  bullets_count: 5
duplicate_detection_method: "sha256"
```

### 2. Topic Watchlist: `.topics.txt`
Assign priorities, categorize, weight, and toggle enabling flags:
```text
[High]
Artificial Intelligence (category:AI, weight:2.0)
Large Language Models (category:AI, weight:1.8)
Linux Mint Security (category:Security, weight:1.5)

[Medium]
Google Cloud AI (category:Cloud, weight:1.2)
Cybersecurity Vulnerabilities (category:Security)
Python 3.12 (category:Programming, enabled:true)

[Low]
Local RAG Pipelines (category:AI, weight:0.8)
Linux Mint Customization (category:Linux, enabled:false)
```

---

## CLI Control Panel

The primary operational interface is the Click command-line utility. Run the `harvester` tool:

- **System Diagnostics**: Check environment, dependencies, local Ollama endpoints, and directories:
  ```bash
  harvester doctor
  ```

- **Run Harvester**: Execute the multi-threaded extraction pipeline:
  ```bash
  harvester run
  ```

- **Database Stats**: View article caches and image statistics:
  ```bash
  harvester stats
  ```

- **Add a Topic**: Add a new prioritized topic:
  ```bash
  harvester topic-add "Enterprise Linux" --priority "High" --category "OS"
  ```

- **Remove a Topic**: Remove an item from the watchlist:
  ```bash
  harvester topic-remove "Linux Mint Customization"
  ```

- **Manage Search Website Restrictions**:
  - Add domain: `harvester website add ubuntu.com`
  - Remove domain: `harvester website remove ubuntu.com`
  - List domains: `harvester website list`

- **Manage RSS Subscriptions**:
  - Add Feed: `harvester feed add "Ubuntu Blog" "https://ubuntu.com/blog/feed"`
  - Remove Feed: `harvester feed remove "Ubuntu Blog"`
  - List Feeds: `harvester feed list`

- **Integrity Verification**: Scan local files to ensure formatting and metadata validation:
  ```bash
  harvester verify
  ```

---

## REST API Server

Expose the offline knowledge base to downstream applications (e.g. Chat UIs, Obsidian, local search portals) using FastAPI:

### Start the Server:
```bash
uvicorn harvester.api.app:app --host 127.0.0.1 --port 8000 --reload
```

### Endpoints:
- **Health Check**: `GET /health`
- **Database Stats**: `GET /stats`
- **Article Full-Text Search**: `GET /search?q=Python&limit=5`
- **Article Details**: `GET /articles/{article_id}`
- **Websites Constraints**:
  - `GET /websites` (List domains)
  - `POST /websites` (Add domain, body: `{"domain": "ubuntu.com"}`)
  - `DELETE /websites/{domain}` (Remove domain)
- **RSS Subscriptions**:
  - `GET /feeds` (List feeds)
  - `POST /feeds` (Add subscription, body: `{"name": "Ubuntu Blog", "url": "https://ubuntu.com/blog/feed"}`)
  - `DELETE /feeds/{name}` (Remove subscription)

---

## Storage Layout Structure

Knowledge documents are saved dynamically inside organized structures that maintain chronological tracking:

```
KnowledgeBase/
├── 2026/
│   └── 07/
│       └── Artificial_Intelligence/
│           └── Deep_Learning_Guide/
│               ├── article.html       # Responsive dark-mode reader
│               ├── article.md         # Pure clean Markdown for LLMs
│               ├── article.json       # Serialized structured document
│               ├── metadata.json      # Structured tags, timestamps, entities
│               ├── summary.md         # Exec summary and bulleted overview
│               └── images/
│                   ├── img001.png     # Localized offline images
│                   └── img002.jpg
```

---

## Testing

Ensure code stability and check coverage using `pytest`:

```bash
pytest -v --cov=harvester
```

All integration test units covering extraction, config, topic parsing, cosine vector similarity, database caching, search restrictions, and feed managers should pass with zero warnings.

---

## Code Quality Standards

The project relies strictly on:
- **Type Hints**: Fully-defined type annotations for clean linting and autocomplete.
- **Clean Architecture & SOLID Rules**: High cohesion, decoupled service components, and robust single-responsibility adapters.
- **Graceful Error Handling**: Individual crawl or extraction failures are logged safely to rotating JSON logs without crashing the active harvesting session.
- **Zero Cloud Dependencies**: Designed to run indefinitely in safe sandbox environments (e.g., Linux Mint/Enterprise Linux) with completely local fallbacks.
