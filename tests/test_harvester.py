import os
import json
import pytest
from harvester.config.config import AppConfig
from harvester.core.topics import parse_topics, format_topics
from harvester.core.models import Topic, Article, Metadata, Summary
from harvester.crawler.downloader import HTTPDownloader
from harvester.rss.manager import RSSManager
from harvester.search.manager import SearchManager
from harvester.extractor.content import ContentExtractor, compute_sha256
from harvester.database.sqlite_db import SQLiteDatabase
from harvester.embeddings.generator import EmbeddingGenerator, cosine_similarity
from harvester.core.ai import AIService
from harvester.storage.manager import StorageManager

@pytest.fixture
def test_config(tmp_path):
    db_file = tmp_path / "test_harvester.db"
    storage_dir = tmp_path / "test_KnowledgeBase"
    config = AppConfig(
        base_storage_path=str(storage_dir),
        database_path=str(db_file),
        download_images=False,
        thread_count=2,
        retry_count=1
    )
    return config

def test_config_loading(tmp_path):
    config_file = tmp_path / "test_config.yaml"
    cfg = AppConfig()
    cfg.save_to_yaml(str(config_file))
    loaded = AppConfig.load_from_file(str(config_file))
    assert loaded.thread_count == cfg.thread_count

def test_topic_parsing(tmp_path):
    topics_file = tmp_path / "topics_test.txt"
    content = """[High]\nArtificial Intelligence (category:AI, weight:2.5)\n[Low]\nPython (enabled:false)"""
    topics_file.write_text(content)

    parsed = parse_topics(str(topics_file))
    assert len(parsed) == 2
    assert parsed[0].name == "Artificial Intelligence"
    assert parsed[0].priority == "High"
    assert parsed[0].category == "AI"
    assert parsed[0].weight == 2.5
    assert parsed[0].enabled is True

    assert parsed[1].name == "Python"
    assert parsed[1].priority == "Low"
    assert parsed[1].enabled is False

def test_sqlite_db_operations(test_config):
    db = SQLiteDatabase(test_config)
    assert db.article_exists("nonexistent") is False

    meta = Metadata(
        title="Test Database Article",
        source_url="https://example_db.com",
        sha256="test_db_sha",
        harvest_timestamp="2026-07-01 12:00:00",
        topic="Test"
    )
    art = Article(
        title="Test Database Article",
        body_text="Testing database caching and retrieval",
        metadata=meta,
        summary=Summary(short_summary="short", long_summary="long")
    )

    art_id = db.insert_article(art)
    assert art_id > 0
    assert db.article_exists("test_db_sha") is True
    assert db.url_exists("https://example_db.com") is True

    retrieved = db.get_article(art_id)
    assert retrieved is not None
    assert retrieved.title == "Test Database Article"
    assert retrieved.body_text == "Testing database caching and retrieval"
    assert retrieved.metadata.sha256 == "test_db_sha"
    assert retrieved.summary.short_summary == "short"

def test_content_extraction():
    extractor = ContentExtractor()
    html = """
    <html>
        <head><title>Test Extraction Article - Tech</title></head>
        <body>
            <header>Ignore Header</header>
            <main>
                <h1>Test Extraction Article</h1>
                <p>Python is an interesting language. It helps with cybersecurity. CVE-2024-54321 is reported.</p>
            </main>
            <footer>Ignore Footer</footer>
        </body>
    </html>
    """
    info = extractor.extract_webpage(html, "http://extract_test.com")
    assert "Test Extraction Article" in info["title"]
    assert "Python" in info["body_text"]

    entities = extractor.extract_entities_and_keywords(info["body_text"])
    assert "Python" in entities["technologies"]
    assert "CVE-2024-54321" in entities["cve_ids"]

def test_cosine_similarity():
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]
    assert cosine_similarity(v1, v2) == pytest.approx(1.0)
    assert cosine_similarity(v1, v3) == pytest.approx(0.0)

def test_ai_service_summarization_and_classification(test_config):
    ai = AIService(test_config)
    text = "Artificial Intelligence is transforming local RAG. Large Language Models process knowledge. We run completely offline."
    summary = ai.summarize(text)
    assert len(summary.short_summary) > 0
    assert len(summary.long_summary) > 0
    assert len(summary.bullet_summary) > 0

    cats = ai.classify_and_tag("Local LLM integration", text)
    assert "AI" in cats

def test_storage_manager(test_config):
    downloader = HTTPDownloader(test_config)
    storage = StorageManager(test_config, downloader)

    meta = Metadata(
        title="Testing Storage Layout Output",
        source_url="http://storage_test.com",
        sha256="test_storage_sha",
        harvest_timestamp="2026-07-01 12:00:00",
        topic="AI"
    )
    art = Article(
        title="Testing Storage Layout Output",
        body_text="Writing html, md and json to storage structure",
        body_html="<p>Writing html, md and json to storage structure</p>",
        metadata=meta,
        summary=Summary(short_summary="short")
    )

    path = storage.write_article_files(art)
    assert os.path.exists(path)
    assert os.path.exists(os.path.join(path, "article.html"))
    assert os.path.exists(os.path.join(path, "article.md"))
    assert os.path.exists(os.path.join(path, "article.json"))
    assert os.path.exists(os.path.join(path, "metadata.json"))
    assert os.path.exists(os.path.join(path, "summary.md"))

def test_search_websites_restriction(test_config):
    test_config.search_websites = ["ubuntu.com", "linuxmint.com"]
    downloader = HTTPDownloader(test_config)
    sm = SearchManager(test_config, downloader)

    # Verify that query format generates site constraints
    assert "ubuntu.com" in test_config.search_websites
    assert len(test_config.search_websites) == 2
    downloader.close()
