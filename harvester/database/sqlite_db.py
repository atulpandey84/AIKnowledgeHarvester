import sqlite3
import json
import os
from typing import List, Dict, Any, Optional, Tuple
from harvester.config.config import AppConfig
from harvester.core.models import Article, Metadata, Summary, Embedding, DownloadedAsset
from harvester.logging_util import get_logger

logger = get_logger()

class SQLiteDatabase:
    def __init__(self, config: AppConfig):
        self.config = config
        self.db_path = config.database_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        logger.info(f"Initializing database at: {self.db_path}")
        with self.get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body_text TEXT NOT NULL,
                body_html TEXT,
                markdown TEXT,
                pdf_path TEXT,
                source_url TEXT UNIQUE,
                canonical_url TEXT,
                author TEXT,
                publisher TEXT,
                published_date TEXT,
                updated_date TEXT,
                language TEXT,
                country TEXT,
                reading_time_minutes INTEGER,
                word_count INTEGER,
                sha256 TEXT UNIQUE,
                harvest_timestamp TEXT,
                topic TEXT,
                search_provider TEXT,
                rss_feed TEXT,
                keywords TEXT,
                categories TEXT,
                license TEXT,
                content_type TEXT,
                short_summary TEXT,
                long_summary TEXT,
                bullet_summary TEXT,
                executive_summary TEXT
            )
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER,
                original_url TEXT,
                local_path TEXT,
                mime_type TEXT,
                size_bytes INTEGER,
                FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE CASCADE
            )
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER,
                model TEXT,
                dimensions INTEGER,
                vector BLOB,
                FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE CASCADE
            )
            """)

            # Create indices for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_sha256 ON articles(sha256)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_source_url ON articles(source_url)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_topic ON articles(topic)")
            conn.commit()

    def article_exists(self, sha256_hash: str) -> bool:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM articles WHERE sha256 = ?", (sha256_hash,))
            return cur.fetchone() is not None

    def url_exists(self, url: str) -> bool:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM articles WHERE source_url = ?", (url,))
            return cur.fetchone() is not None

    def insert_article(self, article: Article) -> int:
        """
        Inserts article, metadata, summaries, images, and embeddings.
        """
        meta = article.metadata
        if not meta:
            raise ValueError("Article must have metadata to be inserted.")

        # Serialize keywords / categories as JSON strings
        kws_str = json.dumps(meta.keywords)
        cats_str = json.dumps(meta.categories)

        sum_short = article.summary.short_summary if article.summary else ""
        sum_long = article.summary.long_summary if article.summary else ""
        sum_bullets = json.dumps(article.summary.bullet_summary) if article.summary else "[]"
        sum_exec = article.summary.executive_summary if article.summary else ""

        with self.get_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute("""
                INSERT INTO articles (
                    title, body_text, body_html, markdown, pdf_path,
                    source_url, canonical_url, author, publisher,
                    published_date, updated_date, language, country,
                    reading_time_minutes, word_count, sha256, harvest_timestamp,
                    topic, search_provider, rss_feed, keywords, categories,
                    license, content_type, short_summary, long_summary,
                    bullet_summary, executive_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    article.title, article.body_text, article.body_html, article.markdown, article.pdf_path,
                    meta.source_url, meta.canonical_url, meta.author, meta.publisher,
                    meta.published_date, meta.updated_date, meta.language, meta.country,
                    meta.reading_time_minutes, meta.word_count, meta.sha256, meta.harvest_timestamp,
                    meta.topic, meta.search_provider, meta.rss_feed, kws_str, cats_str,
                    meta.license, meta.content_type, sum_short, sum_long,
                    sum_bullets, sum_exec
                ))
                article_id = cur.lastrowid

                # Insert images
                for img in article.images:
                    cur.execute("""
                    INSERT INTO images (article_id, original_url, local_path, mime_type, size_bytes)
                    VALUES (?, ?, ?, ?, ?)
                    """, (article_id, img.original_url, img.local_path, img.mime_type, img.size_bytes))

                # Insert embeddings
                for emb in article.embeddings:
                    # Store float array as BLOB using json encoding or pickle/float bytes
                    # Simple JSON-to-string-to-blob is extremely cross-platform and reliable.
                    vec_bytes = json.dumps(emb.vector).encode("utf-8")
                    cur.execute("""
                    INSERT INTO embeddings (article_id, model, dimensions, vector)
                    VALUES (?, ?, ?, ?)
                    """, (article_id, emb.model, emb.dimensions, vec_bytes))

                conn.commit()
                article.id = article_id
                return article_id
            except sqlite3.IntegrityError as e:
                logger.warning(f"IntegrityError inserting article: {e}")
                # Fetch existing ID
                cur.execute("SELECT id FROM articles WHERE sha256 = ? OR source_url = ?", (meta.sha256, meta.source_url))
                row = cur.fetchone()
                if row:
                    return row[0]
                return -1

    def search_articles(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Full text database lookup search for articles containing query.
        """
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT id, title, source_url, published_date, topic, short_summary, word_count, sha256
            FROM articles
            WHERE title LIKE ? OR body_text LIKE ? OR keywords LIKE ?
            ORDER BY id DESC LIMIT ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%", limit))

            results = []
            for row in cur.fetchall():
                results.append(dict(row))
            return results

    def get_article(self, article_id: int) -> Optional[Article]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
            row = cur.fetchone()
            if not row:
                return None

            d = dict(row)

            # Map back to model
            meta = Metadata(
                title=d["title"],
                source_url=d["source_url"],
                canonical_url=d["canonical_url"],
                author=d["author"],
                publisher=d["publisher"],
                published_date=d["published_date"],
                updated_date=d["updated_date"],
                language=d["language"],
                country=d["country"],
                reading_time_minutes=d["reading_time_minutes"],
                word_count=d["word_count"],
                sha256=d["sha256"],
                harvest_timestamp=d["harvest_timestamp"],
                topic=d["topic"],
                search_provider=d["search_provider"],
                rss_feed=d["rss_feed"],
                keywords=json.loads(d["keywords"] or "[]"),
                categories=json.loads(d["categories"] or "[]"),
                license=d["license"],
                content_type=d["content_type"]
            )

            sum_obj = Summary(
                short_summary=d["short_summary"] or "",
                long_summary=d["long_summary"] or "",
                bullet_summary=json.loads(d["bullet_summary"] or "[]"),
                executive_summary=d["executive_summary"] or ""
            )

            # Fetch images
            cur.execute("SELECT * FROM images WHERE article_id = ?", (article_id,))
            imgs = []
            for img_row in cur.fetchall():
                imgs.append(DownloadedAsset(
                    original_url=img_row["original_url"],
                    local_path=img_row["local_path"],
                    mime_type=img_row["mime_type"],
                    size_bytes=img_row["size_bytes"]
                ))

            # Fetch embeddings
            cur.execute("SELECT * FROM embeddings WHERE article_id = ?", (article_id,))
            embs = []
            for emb_row in cur.fetchall():
                vec = json.loads(emb_row["vector"].decode("utf-8"))
                embs.append(Embedding(
                    model=emb_row["model"],
                    dimensions=emb_row["dimensions"],
                    vector=vec
                ))

            return Article(
                id=d["id"],
                title=d["title"],
                body_text=d["body_text"],
                body_html=d["body_html"],
                markdown=d["markdown"],
                pdf_path=d["pdf_path"],
                metadata=meta,
                summary=sum_obj,
                embeddings=embs,
                images=imgs
            )

    def get_stats(self) -> Dict[str, Any]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM articles")
            total_articles = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM images")
            total_images = cur.fetchone()[0]

            cur.execute("SELECT SUM(size_bytes) FROM images")
            total_images_size = cur.fetchone()[0] or 0

            cur.execute("SELECT DISTINCT topic FROM articles")
            topics = [row[0] for row in cur.fetchall()]

            return {
                "total_articles": total_articles,
                "total_images": total_images,
                "total_images_size_bytes": total_images_size,
                "topics_covered": topics
            }
