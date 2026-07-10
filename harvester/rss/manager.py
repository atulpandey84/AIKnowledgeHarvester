import feedparser
from typing import List, Dict, Any
from harvester.config.config import AppConfig
from harvester.crawler.downloader import HTTPDownloader
from harvester.logging_util import get_logger

logger = get_logger()

class RSSManager:
    def __init__(self, config: AppConfig, downloader: HTTPDownloader):
        self.config = config
        self.downloader = downloader

    def fetch_feed_entries(self, feed_name: str, feed_url: str) -> List[Dict[str, Any]]:
        """
        Fetches entries from a single RSS feed.
        """
        logger.info(f"Fetching RSS feed '{feed_name}' from: {feed_url}")
        try:
            # We can download the feed content via the HTTP downloader
            response = self.downloader.download(feed_url)
            feed_data = feedparser.parse(response.content)

            entries = []
            for entry in feed_data.entries:
                title = entry.get("title", "")
                link = entry.get("link", "")
                published = entry.get("published", entry.get("updated", ""))
                summary = entry.get("summary", "")
                author = entry.get("author", "")

                if link:
                    entries.append({
                        "title": title,
                        "url": link,
                        "published_date": published,
                        "summary": summary,
                        "author": author,
                        "rss_feed": feed_name
                    })
            logger.info(f"Successfully parsed {len(entries)} entries from feed '{feed_name}'")
            return entries
        except Exception as e:
            logger.error(f"Failed to fetch RSS feed '{feed_name}': {e}")
            return []

    def fetch_all_feeds(self) -> List[Dict[str, Any]]:
        """
        Fetches entries from all configured feeds.
        """
        all_entries = []
        for feed in self.config.rss_feeds:
            name = feed.get("name")
            url = feed.get("url")
            if name and url:
                all_entries.extend(self.fetch_feed_entries(name, url))
        return all_entries

    def filter_by_topic(self, entries: List[Dict[str, Any]], topic_name: str) -> List[Dict[str, Any]]:
        """
        Filters entries to keep only those relevant to a specific topic name / keywords.
        """
        keywords = [k.lower() for k in topic_name.split()]
        filtered = []
        for entry in entries:
            # Simple match in title or summary
            text = (entry["title"] + " " + entry["summary"]).lower()
            if any(k in text for k in keywords):
                filtered.append(entry)
        return filtered
