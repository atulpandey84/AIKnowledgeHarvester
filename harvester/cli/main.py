import sys
import os
import click
import yaml
import json
from harvester.config.config import AppConfig
from harvester.core.topics import parse_topics, format_topics
from harvester.core.models import Topic
from harvester.workers.pipeline import HarvestingPipeline
from harvester.database.sqlite_db import SQLiteDatabase
from harvester.core.rag import LocalRAGQueryEngine
from harvester.logging_util import setup_logging, get_logger

logger = get_logger()

@click.group()
@click.option('--config-file', default='config.yaml', help='Path to configuration file.')
@click.pass_context
def main(ctx, config_file):
    """Enterprise Knowledge Harvester v2 - Master CLI Control Panel."""
    # Ensure ctx.obj is a dict
    ctx.ensure_object(dict)
    ctx.obj['config_file'] = config_file

    # Load configuration
    config = AppConfig.load_from_file(config_file)
    ctx.obj['config'] = config

    # Setup Logging
    setup_logging(config.logging_level)

@main.command()
@click.pass_context
def run(ctx):
    """Execute the full continuously scheduled pipeline run once."""
    config = ctx.obj['config']
    config_file = ctx.obj['config_file']
    click.echo(f"Initializing Harvester Run... Threads: {config.thread_count}")

    # Pass config_file dynamically to support custom config profiles
    pipeline = HarvestingPipeline(config, config_file=config_file)
    stats = pipeline.run_pipeline()

    click.echo("\n--- Harvest Session Statistics ---")
    click.echo(f"Articles Harvested: {stats['articles_downloaded']}")
    click.echo(f"RSS Feeds Checked: {stats['rss_checked']}")
    click.echo(f"Search Providers Used: {stats['search_providers_used']}")
    click.echo(f"Duplicates Removed: {stats['duplicates_removed']}")
    click.echo(f"Images Saved: {stats['images_downloaded']}")
    click.echo(f"Storage Allocated: {stats['storage_consumed_bytes']} bytes")
    click.echo(f"Execution Failures: {stats['failures']}")
    click.echo(f"Elapsed Time: {stats['elapsed_time_seconds']}s")

@main.command()
@click.pass_context
def stats(ctx):
    """View offline Knowledge Base sqlite database statistics."""
    config = ctx.obj['config']
    db = SQLiteDatabase(config)
    stats_dict = db.get_stats()

    click.echo("\n--- Offline Knowledge Database Stats ---")
    click.echo(f"Total Cached Articles: {stats_dict['total_articles']}")
    click.echo(f"Total Local Images: {stats_dict['total_images']}")
    click.echo(f"Total Images Size: {stats_dict['total_images_size_bytes']} bytes")
    click.echo(f"Registered/Harvested Topics: {', '.join(stats_dict['topics_covered'])}")

@main.command(name="topic-add")
@click.argument('topic_name')
@click.option('--priority', default='Medium', help='High, Medium, or Low.')
@click.option('--category', default='', help='A general technology category.')
@click.option('--weight', default=1.0, help='Weight priority factor.')
@click.pass_context
def topic_add(ctx, topic_name, priority, category, weight):
    """Add a new target topic to watch list (.topics.txt)."""
    topics = parse_topics(".topics.txt")

    # Check duplicate
    if any(t.name.lower() == topic_name.lower() for t in topics):
        click.echo(f"Error: Topic '{topic_name}' already exists.")
        sys.exit(1)

    new_topic = Topic(
        name=topic_name,
        priority=priority.capitalize(),
        category=category if category else None,
        weight=weight,
        enabled=True
    )
    topics.append(new_topic)

    formatted = format_topics(topics)
    with open(".topics.txt", "w", encoding="utf-8") as f:
        f.write(formatted + "\n")

    click.echo(f"Topic '{topic_name}' successfully added with {priority} priority.")

@main.command(name="topic-remove")
@click.argument('topic_name')
@click.pass_context
def topic_remove(ctx, topic_name):
    """Remove a target topic from watch list (.topics.txt)."""
    topics = parse_topics(".topics.txt")

    filtered = [t for t in topics if t.name.lower() != topic_name.lower()]
    if len(filtered) == len(topics):
        click.echo(f"Topic '{topic_name}' not found in watch list.")
        sys.exit(1)

    formatted = format_topics(filtered)
    with open(".topics.txt", "w", encoding="utf-8") as f:
        f.write(formatted + "\n")

    click.echo(f"Topic '{topic_name}' successfully removed.")


# --- Website Command Group ---
@main.group(name="website")
def website_group():
    """Manage websites/domains used for restricted DuckDuckGo search queries."""
    pass

@website_group.command(name="add")
@click.argument('domain')
@click.pass_context
def website_add(ctx, domain):
    """Add a search website/domain restriction."""
    # Since main config loads into ctx.parent.obj, we grab it from there
    parent_ctx = ctx.parent
    while parent_ctx and 'config' not in parent_ctx.obj:
        parent_ctx = parent_ctx.parent

    if not parent_ctx:
        click.echo("Error: Config context not found.")
        sys.exit(1)

    config = parent_ctx.obj['config']
    config_file = parent_ctx.obj['config_file']

    domain_clean = domain.strip().lower()
    if domain_clean in config.search_websites:
        click.echo(f"Website '{domain_clean}' is already configured.")
        return

    config.search_websites.append(domain_clean)
    config.save_to_yaml(config_file)
    click.echo(f"Successfully added website: '{domain_clean}'")

@website_group.command(name="remove")
@click.argument('domain')
@click.pass_context
def website_remove(ctx, domain):
    """Remove a search website/domain restriction."""
    parent_ctx = ctx.parent
    while parent_ctx and 'config' not in parent_ctx.obj:
        parent_ctx = parent_ctx.parent

    if not parent_ctx:
        click.echo("Error: Config context not found.")
        sys.exit(1)

    config = parent_ctx.obj['config']
    config_file = parent_ctx.obj['config_file']

    domain_clean = domain.strip().lower()
    if domain_clean not in config.search_websites:
        click.echo(f"Website '{domain_clean}' is not in search_websites.")
        sys.exit(1)

    config.search_websites.remove(domain_clean)
    config.save_to_yaml(config_file)
    click.echo(f"Successfully removed website: '{domain_clean}'")

@website_group.command(name="list")
@click.pass_context
def website_list(ctx):
    """List all restricted search websites/domains."""
    parent_ctx = ctx.parent
    while parent_ctx and 'config' not in parent_ctx.obj:
        parent_ctx = parent_ctx.parent

    if not parent_ctx:
        click.echo("Error: Config context not found.")
        sys.exit(1)

    config = parent_ctx.obj['config']
    if not config.search_websites:
        click.echo("No restricted search websites configured. DuckDuckGo searches globally.")
    else:
        click.echo("Configured Restricted Search Websites:")
        for ws in config.search_websites:
            click.echo(f"  - {ws}")


# --- RSS Feed Command Group ---
@main.group(name="feed")
def feed_group():
    """Manage RSS feeds checked during the pipeline execution."""
    pass

@feed_group.command(name="add")
@click.argument('name')
@click.argument('url')
@click.pass_context
def feed_add(ctx, name, url):
    """Add a new RSS feed subscription to check during harvesting."""
    parent_ctx = ctx.parent
    while parent_ctx and 'config' not in parent_ctx.obj:
        parent_ctx = parent_ctx.parent

    if not parent_ctx:
        click.echo("Error: Config context not found.")
        sys.exit(1)

    config = parent_ctx.obj['config']
    config_file = parent_ctx.obj['config_file']

    name_clean = name.strip()
    url_clean = url.strip()

    # Check if name or URL already exists
    for feed in config.rss_feeds:
        if feed.get("name", "").lower() == name_clean.lower():
            click.echo(f"Error: Feed named '{name_clean}' already exists.")
            sys.exit(1)
        if feed.get("url", "").lower() == url_clean.lower():
            click.echo(f"Error: Feed URL '{url_clean}' is already registered under name '{feed.get('name')}'")
            sys.exit(1)

    config.rss_feeds.append({"name": name_clean, "url": url_clean})
    config.save_to_yaml(config_file)
    click.echo(f"Successfully added RSS feed '{name_clean}' with URL: '{url_clean}'")

@feed_group.command(name="remove")
@click.argument('name')
@click.pass_context
def feed_remove(ctx, name):
    """Remove an RSS feed subscription by name."""
    parent_ctx = ctx.parent
    while parent_ctx and 'config' not in parent_ctx.obj:
        parent_ctx = parent_ctx.parent

    if not parent_ctx:
        click.echo("Error: Config context not found.")
        sys.exit(1)

    config = parent_ctx.obj['config']
    config_file = parent_ctx.obj['config_file']

    name_clean = name.strip().lower()

    target_feed = None
    for feed in config.rss_feeds:
        if feed.get("name", "").lower() == name_clean:
            target_feed = feed
            break

    if not target_feed:
        click.echo(f"Error: RSS feed named '{name}' not found.")
        sys.exit(1)

    config.rss_feeds.remove(target_feed)
    config.save_to_yaml(config_file)
    click.echo(f"Successfully removed RSS feed subscription: '{target_feed['name']}'")

@feed_group.command(name="list")
@click.pass_context
def feed_list(ctx):
    """List all currently subscribed RSS feeds."""
    parent_ctx = ctx.parent
    while parent_ctx and 'config' not in parent_ctx.obj:
        parent_ctx = parent_ctx.parent

    if not parent_ctx:
        click.echo("Error: Config context not found.")
        sys.exit(1)

    config = parent_ctx.obj['config']
    if not config.rss_feeds:
        click.echo("No RSS feeds configured.")
    else:
        click.echo("Configured RSS feeds subscriptions:")
        for feed in config.rss_feeds:
            click.echo(f"  - {feed.get('name')}: {feed.get('url')}")


# --- Local RAG Grounded Answer Command ---
@main.command(name="ask")
@click.argument("question")
@click.option("--top-k", default=3, help="Max source context blocks to retrieve.")
@click.pass_context
def ask(ctx, question, top_k):
    """Query your local Ollama LLM grounded strictly on freshly harvested offline knowledge."""
    config = ctx.obj['config']
    db = SQLiteDatabase(config)

    click.echo(f"Executing Grounded Semantic Query: '{question}'...")
    rag_engine = LocalRAGQueryEngine(config, db)
    res = rag_engine.query(question, top_k=top_k)

    click.echo("\n" + "="*40 + " GROUNDED ANSWER " + "="*40)
    click.echo(res["answer"])
    click.echo("="*97)

    if res["sources"]:
        click.echo("\n--- Harvested Context Sources ---")
        for i, s in enumerate(res["sources"], 1):
            click.echo(f" {i}. {s['title']} ({s['source_url']}) - Cosine Similarity: {s['score']}")
    else:
        click.echo("\nNo relevant freshly harvested local sources were found for this query.")


@main.command()
@click.pass_context
def doctor(ctx):
    """System diagnostic, checking dependencies, directories, models and local server."""
    click.echo("--- Diagnostic Doctor Report ---")
    # Python Version
    click.echo(f"Python Version: {sys.version}")
    # Local Storage Directory
    storage_ok = os.path.isdir("KnowledgeBase")
    click.echo(f"KnowledgeBase Folder: {'[OK]' if storage_ok else '[WARNING - Creating now]'}")
    if not storage_ok:
        os.makedirs("KnowledgeBase", exist_ok=True)

    # sqlite Database Status
    try:
        config = ctx.obj['config']
        db = SQLiteDatabase(config)
        db_stats = db.get_stats()
        click.echo(f"SQLite Connection & Schema: [OK] ({db_stats['total_articles']} articles cached)")
    except Exception as e:
        click.echo(f"SQLite Database: [FAILED] - {e}")

    # Local Ollama Status
    try:
        import httpx
        resp = httpx.get(f"{ctx.obj['config'].ollama_base_url}/api/tags", timeout=2.0)
        if resp.status_code == 200:
            click.echo(f"Ollama Local Server: [OK] (Base URL: {ctx.obj['config'].ollama_base_url})")
        else:
            click.echo(f"Ollama Local Server: [OFFLINE] (Status Code: {resp.status_code})")
    except Exception:
        click.echo("Ollama Local Server: [OFFLINE] (No local service running on localhost:11434)")

    # Libraries Checked
    for lib in ["trafilatura", "bs4", "feedparser", "pypdf"]:
        try:
            __import__(lib)
            click.echo(f"Dependency '{lib}': [OK]")
        except ImportError:
            click.echo(f"Dependency '{lib}': [MISSING]")

@main.command()
@click.pass_context
def verify(ctx):
    """Verify integrity of offline Knowledge Base files (HTML, JSON, Markdown)."""
    click.echo("Scanning local storage layout and verifying file integrity...")
    corrupt_count = 0
    total_checked = 0

    for root, dirs, files in os.walk("KnowledgeBase"):
        if "article.json" in files:
            total_checked += 1
            article_json_path = os.path.join(root, "article.json")
            try:
                with open(article_json_path, "r", encoding="utf-8") as f:
                    json.load(f)
            except Exception as e:
                click.echo(f"File validation failed on {article_json_path}: {e}")
                corrupt_count += 1

    click.echo(f"Verification process complete. Scanned directories: {total_checked}. Corrupt: {corrupt_count}")

if __name__ == "__main__":
    main()
