import os
import yaml
import json
from dataclasses import dataclass, field, fields
from typing import List, Dict, Any, Optional

@dataclass
class AppConfig:
    # Base paths
    base_storage_path: str = "KnowledgeBase"
    database_path: str = "KnowledgeBase/harvester.db"

    # Engine Settings
    thread_count: int = 4
    timeout: float = 30.0
    retry_count: int = 3
    scheduling_interval_seconds: int = 3600
    logging_level: str = "INFO"

    # Image options
    download_images: bool = True
    max_image_size_bytes: int = 5 * 1024 * 1024 # 5MB
    min_image_dimension: int = 100

    # Crawler Limits
    max_articles_per_topic: int = 10
    minimum_article_length_words: int = 100
    max_crawl_depth: int = 2
    rate_limiting_delay_seconds: float = 1.0

    # Search & RSS config
    search_providers: List[str] = field(default_factory=lambda: ["rss", "duckduckgo"])
    rss_feeds: List[Dict[str, str]] = field(default_factory=lambda: [
        {"name": "Linux Mint", "url": "https://linuxmint-se.org/feed"},
        {"name": "Ubuntu", "url": "https://ubuntu.com/blog/feed"},
        {"name": "Google Cloud", "url": "https://cloud.google.com/blog/rss"},
        {"name": "OpenAI", "url": "https://openai.com/blog/rss"},
        {"name": "Anthropic", "url": "https://www.anthropic.com/index.xml"},
        {"name": "Microsoft", "url": "https://blogs.microsoft.com/feed/"},
        {"name": "NVIDIA", "url": "https://blogs.nvidia.com/feed/"},
        {"name": "Reuters", "url": "http://feeds.reuters.com/reuters/topNews"},
        {"name": "BBC", "url": "http://feeds.bbci.co.uk/news/rss.xml"},
        {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml"},
        {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index"},
        {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
        {"name": "KrebsOnSecurity", "url": "https://krebsonsecurity.com/feed/"},
        {"name": "Cloudflare", "url": "https://blog.cloudflare.com/rss/"},
        {"name": "AWS", "url": "https://aws.amazon.com/blogs/aws/feed/"},
        {"name": "Red Hat", "url": "https://www.redhat.com/en/blog/rss"},
        {"name": "HashiCorp", "url": "https://www.hashicorp.com/blog/feed.xml"},
        {"name": "Python.org", "url": "https://www.python.org/blogs/feed/"},
        {"name": "GitHub Blog", "url": "https://github.blog/feed/"}
    ])
    ignored_domains: List[str] = field(default_factory=lambda: ["doubleclick.net", "googleadservices.com"])
    allowed_domains: List[str] = field(default_factory=list)
    search_websites: List[str] = field(default_factory=list) # Websites to restrict search to

    # Embedding settings
    embedding_model: str = "nomic-embed-text"
    ollama_base_url: str = "http://localhost:11434"
    vector_db_type: str = "sqlite" # sqlite fallback, faiss, chromadb, etc.

    # LLM & AI settings
    llm_enabled: bool = False
    llm_model: str = "llama3"
    summarization_enabled: bool = True
    summarization_settings: Dict[str, Any] = field(default_factory=lambda: {
        "short_len": 150,
        "long_len": 500,
        "bullets_count": 5
    })

    # Duplication settings
    duplicate_detection_method: str = "sha256" # sha256 or simhash
    simhash_threshold: int = 3 # bits distance

    user_agent_pool: List[str] = field(default_factory=lambda: [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/119.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0"
    ])

    @classmethod
    def load_from_file(cls, filepath: str) -> "AppConfig":
        if not os.path.exists(filepath):
            return cls()

        _, ext = os.path.splitext(filepath)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                if ext.lower() in (".yaml", ".yml"):
                    data = yaml.safe_load(f) or {}
                elif ext.lower() == ".json":
                    data = json.load(f) or {}
                else:
                    data = {}
        except Exception:
            return cls()

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        valid_keys = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_keys}

        # Override with env variables if present
        for f in fields(cls):
            env_key = f"HARVESTER_{f.name.upper()}"
            if env_key in os.environ:
                val = os.environ[env_key]
                # Cast val according to field type
                if f.type is int:
                    filtered[f.name] = int(val)
                elif f.type is float:
                    filtered[f.name] = float(val)
                elif f.type is bool:
                    filtered[f.name] = val.lower() in ("true", "1", "yes")
                elif f.type is list or getattr(f.type, "__origin__", None) is list:
                    try:
                        filtered[f.name] = json.loads(val)
                    except Exception:
                        filtered[f.name] = [x.strip() for x in val.split(",") if x.strip()]
                elif f.type is dict or getattr(f.type, "__origin__", None) is dict:
                    try:
                        filtered[f.name] = json.loads(val)
                    except Exception:
                        pass
                else:
                    filtered[f.name] = val

        return cls(**filtered)

    def save_to_yaml(self, filepath: str):
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.__dict__, f, default_flow_style=False, sort_keys=False)
