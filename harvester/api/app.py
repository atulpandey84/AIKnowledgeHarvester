from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from harvester.config import config as app_conf_module
from harvester.config.config import AppConfig
from harvester.database.sqlite_db import SQLiteDatabase
from harvester.core.rag import LocalRAGQueryEngine
from harvester.logging_util import get_logger

logger = get_logger()

# Create AppConfig and database connection
config = AppConfig.load_from_file("config.yaml")
db = SQLiteDatabase(config)

app = FastAPI(
    title="Enterprise Knowledge Harvester v2 API",
    description="Offline REST API layer to browse, search, and monitor offline harvested enterprise documents.",
    version="2.0.0"
)

class WebsiteRequest(BaseModel):
    domain: str

class FeedRequest(BaseModel):
    name: str
    url: str

class RAGRequest(BaseModel):
    question: str
    top_k: int = 3

@app.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "healthy", "service": "harvester-api"}

@app.get("/stats")
def get_stats() -> Dict[str, Any]:
    try:
        return db.get_stats()
    except Exception as e:
        logger.error(f"Failed to fetch database stats for API: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/search")
def search_articles(
    q: str = Query(..., description="Full text search term"),
    limit: int = Query(10, description="Max results limit")
) -> List[Dict[str, Any]]:
    try:
        results = db.search_articles(q, limit=limit)
        return results
    except Exception as e:
        logger.error(f"Search API query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/articles/{article_id}")
def get_article(article_id: int) -> Dict[str, Any]:
    try:
        article = db.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        # Build clean JSON serializable response
        return {
            "id": article.id,
            "title": article.title,
            "body_text": article.body_text,
            "body_html": article.body_html,
            "markdown": article.markdown,
            "pdf_path": article.pdf_path,
            "metadata": article.metadata.__dict__ if article.metadata else None,
            "summary": article.summary.__dict__ if article.summary else None,
            "images": [{"original_url": i.original_url, "local_path": i.local_path} for i in article.images]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve article ID {article_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Website API Management ---
@app.get("/websites")
def get_websites() -> List[str]:
    # reload config to get latest saved file states
    global config
    config = AppConfig.load_from_file("config.yaml")
    return config.search_websites

@app.post("/websites")
def add_website(payload: WebsiteRequest) -> Dict[str, Any]:
    global config
    config = AppConfig.load_from_file("config.yaml")

    clean_domain = payload.domain.strip().lower()
    if not clean_domain:
        raise HTTPException(status_code=400, detail="Invalid domain")

    if clean_domain in config.search_websites:
        return {"status": "already_exists", "domain": clean_domain}

    config.search_websites.append(clean_domain)
    config.save_to_yaml("config.yaml")
    return {"status": "added", "domain": clean_domain}

@app.delete("/websites/{domain}")
def remove_website(domain: str) -> Dict[str, Any]:
    global config
    config = AppConfig.load_from_file("config.yaml")

    clean_domain = domain.strip().lower()
    if clean_domain not in config.search_websites:
        raise HTTPException(status_code=404, detail=f"Website {clean_domain} not found")

    config.search_websites.remove(clean_domain)
    config.save_to_yaml("config.yaml")
    return {"status": "removed", "domain": clean_domain}

# --- RSS Feed API Management ---
@app.get("/feeds")
def get_feeds() -> List[Dict[str, str]]:
    global config
    config = AppConfig.load_from_file("config.yaml")
    return config.rss_feeds

@app.post("/feeds")
def add_feed(payload: FeedRequest) -> Dict[str, Any]:
    global config
    config = AppConfig.load_from_file("config.yaml")

    name_clean = payload.name.strip()
    url_clean = payload.url.strip()

    if not name_clean or not url_clean:
        raise HTTPException(status_code=400, detail="Name and URL must not be empty.")

    for f in config.rss_feeds:
        if f.get("name", "").lower() == name_clean.lower():
            raise HTTPException(status_code=400, detail=f"Feed with name '{name_clean}' already exists.")
        if f.get("url", "").lower() == url_clean.lower():
            raise HTTPException(status_code=400, detail=f"Feed URL '{url_clean}' is already registered under name '{f.get('name')}'")

    config.rss_feeds.append({"name": name_clean, "url": url_clean})
    config.save_to_yaml("config.yaml")
    return {"status": "added", "feed": {"name": name_clean, "url": url_clean}}

@app.delete("/feeds/{name}")
def remove_feed(name: str) -> Dict[str, Any]:
    global config
    config = AppConfig.load_from_file("config.yaml")

    name_clean = name.strip().lower()

    target_feed = None
    for f in config.rss_feeds:
        if f.get("name", "").lower() == name_clean:
            target_feed = f
            break

    if not target_feed:
        raise HTTPException(status_code=404, detail=f"Feed with name '{name}' not found.")

    config.rss_feeds.remove(target_feed)
    config.save_to_yaml("config.yaml")
    return {"status": "removed", "feed_name": target_feed["name"]}

# --- Local RAG Grounded Query REST Endpoint ---
@app.post("/ask")
def ask_local_rag(payload: RAGRequest) -> Dict[str, Any]:
    """
    Exposes Local RAG Query Engine to retrieve semantically matching context blocks
    and synthesize an answer grounded strictly in local harvested knowledge.
    """
    try:
        global config
        config = AppConfig.load_from_file("config.yaml")
        rag_engine = LocalRAGQueryEngine(config, db)
        return rag_engine.query(payload.question, top_k=payload.top_k)
    except Exception as e:
        logger.error(f"Local RAG ask endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
