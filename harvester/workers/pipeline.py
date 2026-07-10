import time
import datetime
import concurrent.futures
from typing import List, Dict, Any, Optional
from harvester.config.config import AppConfig
from harvester.core.models import Topic, Article, Metadata, Summary
from harvester.core.topics import parse_topics
from harvester.crawler.downloader import HTTPDownloader
from harvester.rss.manager import RSSManager
from harvester.search.manager import SearchManager
from harvester.extractor.content import ContentExtractor, compute_sha256
from harvester.database.sqlite_db import SQLiteDatabase
from harvester.embeddings.generator import EmbeddingGenerator
from harvester.core.ai import AIService
from harvester.storage.manager import StorageManager
from harvester.logging_util import get_logger

logger = get_logger()

class HarvestingPipeline:
    def __init__(self, config: AppConfig):
        self.config = config
        self.downloader = HTTPDownloader(config)
        self.rss_mgr = RSSManager(config, self.downloader)
        self.search_mgr = SearchManager(config, self.downloader)
        self.extractor = ContentExtractor()
        self.db = SQLiteDatabase(config)
        self.embed_gen = EmbeddingGenerator(config)
        self.ai_service = AIService(config)
        self.storage_mgr = StorageManager(config, self.downloader)

        # Pipeline stats
        self.stats = {
            "articles_downloaded": 0,
            "rss_checked": 0,
            "search_providers_used": len(config.search_providers),
            "duplicates_removed": 0,
            "images_downloaded": 0,
            "storage_consumed_bytes": 0,
            "failures": 0,
            "retries": 0,
            "elapsed_time_seconds": 0.0
        }

    def process_url(self, url: str, topic_name: str, search_provider: Optional[str] = None, rss_feed: Optional[str] = None) -> Optional[str]:
        """
        Executes end-to-end download, extraction, analysis, indexing, and storage of a single URL.
        Thread-safe wrapper.
        """
        try:
            logger.info(f"Pipeline processing URL: {url}")

            # 1. Check DB for URL duplicate
            if self.db.url_exists(url):
                logger.info(f"Duplicate detected: URL already harvested {url}")
                self.stats["duplicates_removed"] += 1
                return None

            # 2. Download content
            response = self.downloader.download(url)
            content_type = response.headers.get("Content-Type", "text/html").lower()

            # Determine if PDF
            is_pdf = "application/pdf" in content_type or url.endswith(".pdf")

            # 3. Extract content and metadata
            if is_pdf:
                extracted = self.extractor.extract_pdf(response.content, url)
                extracted["content_type"] = "application/pdf"
            else:
                extracted = self.extractor.extract_webpage(response.text, url)
                extracted["content_type"] = "text/html"

            # 4. Generate SHA256 and duplicate check content hash
            sha_hash = compute_sha256(extracted["body_text"])
            if self.db.article_exists(sha_hash):
                logger.info(f"Duplicate detected: SHA256 hash already exists for content of {url}")
                self.stats["duplicates_removed"] += 1
                return None

            # 5. Extract additional keywords & entities
            nlp_data = self.extractor.extract_entities_and_keywords(extracted["body_text"])

            # Classify domains
            ai_cats = self.ai_service.classify_and_tag(extracted["title"], extracted["body_text"])

            # 6. Generate Summarization
            summary_obj = self.ai_service.summarize(extracted["body_text"])

            # Build Metadata object
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            meta = Metadata(
                title=extracted["title"],
                source_url=url,
                canonical_url=extracted["canonical_url"],
                author=extracted["author"],
                publisher=extracted.get("publisher") or urlparse(url).netloc,
                published_date=extracted["published_date"],
                language=extracted["language"],
                reading_time_minutes=extracted["reading_time_minutes"],
                word_count=extracted["word_count"],
                sha256=sha_hash,
                harvest_timestamp=now_str,
                topic=topic_name,
                search_provider=search_provider,
                rss_feed=rss_feed,
                keywords=list(set(extracted["keywords"] + nlp_data["keywords"])),
                categories=ai_cats,
                content_type=extracted["content_type"]
            )

            # 7. Generate Embedding
            emb_obj = self.embed_gen.generate(extracted["body_text"])

            # Build Article object
            article = Article(
                title=extracted["title"],
                body_text=extracted["body_text"],
                body_html=extracted["body_html"],
                metadata=meta,
                summary=summary_obj,
                embeddings=[emb_obj]
            )

            if is_pdf:
                # Save PDF locally
                pdf_folder = self.storage_mgr.build_article_path(topic_name, extracted["title"], meta.published_date or now_str)
                os.makedirs(os.path.join(pdf_folder, "pdf"), exist_ok=True)
                pdf_local_path = os.path.join(pdf_folder, "pdf", "original.pdf")
                with open(pdf_local_path, "wb") as f:
                    f.write(response.content)
                article.pdf_path = os.path.join("pdf", "original.pdf")

            # 8. Storage: Write Local Files (rewriting images inside)
            saved_folder = self.storage_mgr.write_article_files(article)

            # Calculate image downloads
            self.stats["images_downloaded"] += len(article.images)
            for img in article.images:
                self.stats["storage_consumed_bytes"] += img.size_bytes

            # 9. Insert to SQLite DB
            self.db.insert_article(article)

            self.stats["articles_downloaded"] += 1
            logger.info(f"Successfully processed and stored article: {extracted['title']}")
            return saved_folder

        except Exception as e:
            logger.error(f"Error processing URL {url}: {e}", exc_info=True)
            self.stats["failures"] += 1
            return None

    def run_pipeline(self) -> Dict[str, Any]:
        """
        Runs the full harvesting lifecycle.
        Reads .topics.txt, harvests from RSS and Search Engine layer using configured ThreadPoolExecutor.
        """
        start_time = time.time()
        logger.info("Starting Enterprise Knowledge Harvester pipeline...")

        # Load and parse active topics
        topics = parse_topics(".topics.txt")
        active_topics = [t for t in topics if t.enabled]
        logger.info(f"Loaded {len(topics)} topics, {len(active_topics)} are active.")

        # 1. Fetch all RSS items first (before search)
        self.stats["rss_checked"] = len(self.config.rss_feeds)
        rss_items = []
        if "rss" in self.config.search_providers:
            rss_items = self.rss_mgr.fetch_all_feeds()
            logger.info(f"Fetched {len(rss_items)} RSS entries.")

        # 2. Gather candidates per active topic
        candidates: List[Dict[str, Any]] = [] # list of dict: {"url": str, "topic": str, "provider": str, "rss_feed": str}

        for topic in active_topics:
            topic_candidates = []

            # Extract from RSS feeds matching topic keywords
            rss_matches = self.rss_mgr.filter_by_topic(rss_items, topic.name)
            for item in rss_matches:
                topic_candidates.append({
                    "url": item["url"],
                    "topic": topic.name,
                    "provider": "rss",
                    "rss_feed": item["rss_feed"]
                })

            # Query web search if allowed and if we have space below limit
            if "duckduckgo" in self.config.search_providers:
                # Query Search Manager
                search_results = self.search_mgr.search(topic.name)
                for res in search_results:
                    topic_candidates.append({
                        "url": res["url"],
                        "topic": topic.name,
                        "provider": "duckduckgo",
                        "rss_feed": None
                    })

            # Deduplicate Candidates by URL for this topic and limit
            seen_urls = set()
            pushed_count = 0
            for cand in topic_candidates:
                if pushed_count >= self.config.max_articles_per_topic:
                    break
                if cand["url"] not in seen_urls:
                    seen_urls.add(cand["url"])
                    candidates.append(cand)
                    pushed_count += 1

        logger.info(f"Collected total of {len(candidates)} candidate URLs to harvest.")

        # 3. Parallel Processing of Candidates
        # Use configured thread count
        workers_count = self.config.thread_count
        logger.info(f"Launching concurrent downloads with {workers_count} threads.")

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers_count) as executor:
            futures = []
            for cand in candidates:
                f = executor.submit(
                    self.process_url,
                    cand["url"],
                    cand["topic"],
                    cand["provider"],
                    cand["rss_feed"]
                )
                futures.append(f)

            for future in concurrent.futures.as_completed(futures):
                # Ensure exceptions are retrieved/logged inside the pool
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Worker thread error: {e}")

        self.downloader.close()

        self.stats["elapsed_time_seconds"] = round(time.time() - start_time, 2)
        logger.info(f"Pipeline finished. Stats: {self.stats}")
        return self.stats

from urllib.parse import urlparse
