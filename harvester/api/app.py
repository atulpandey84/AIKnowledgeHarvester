from fastapi import FastAPI, Query, HTTPException
from typing import List, Dict, Any, Optional
from harvester.config.config import AppConfig
from harvester.database.sqlite_db import SQLiteDatabase
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
