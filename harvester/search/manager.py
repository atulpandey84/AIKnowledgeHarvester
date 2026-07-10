import re
import urllib.parse
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from harvester.config.config import AppConfig
from harvester.crawler.downloader import HTTPDownloader
from harvester.logging_util import get_logger

logger = get_logger()

class SearchManager:
    def __init__(self, config: AppConfig, downloader: HTTPDownloader):
        self.config = config
        self.downloader = downloader

    def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Executes search across enabled provider adapters.
        Removes duplicates, fallbacks gracefully, scores and merges results.
        """
        results: List[Dict[str, Any]] = []
        for provider in self.config.search_providers:
            if provider == "rss":
                # Handled separately or skipped in direct web search
                continue

            try:
                logger.info(f"Querying search provider '{provider}' for query: '{query}'")
                if provider == "duckduckgo":
                    provider_results = self._search_duckduckgo(query)
                elif provider == "searxng":
                    provider_results = self._search_searxng(query)
                else:
                    logger.warning(f"Unsupported search provider: {provider}")
                    provider_results = []

                results.extend(provider_results)
            except Exception as e:
                logger.error(f"Search provider '{provider}' failed for query '{query}': {e}")

        # Deduplicate by url and normalize scores
        unique_results = {}
        for r in results:
            url = r["url"]
            # Clean url trailing slash/params for normalization
            parsed = urllib.parse.urlparse(url)
            norm_url = f"{parsed.netloc}{parsed.path}"

            if norm_url not in unique_results:
                unique_results[norm_url] = r
            else:
                # Keep highest score
                if r.get("score", 0) > unique_results[norm_url].get("score", 0):
                    unique_results[norm_url] = r

        sorted_results = sorted(unique_results.values(), key=lambda x: x.get("score", 0), reverse=True)
        return sorted_results

    def _search_duckduckgo(self, query: str) -> List[Dict[str, Any]]:
        """
        HTML scraping implementation for DuckDuckGo (Lite HTML version).
        Refers to DuckDuckGo HTML without heavy JavaScript requirements.
        """
        encoded_query = urllib.parse.quote_plus(query)
        # Use DDG HTML/Lite endpoint
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

        try:
            response = self.downloader.download(url)
            soup = BeautifulSoup(response.content, "html.parser")

            results = []
            links = soup.find_all("a", class_="result__url")
            titles = soup.find_all("a", class_="result__snippet") # snippet or title link

            # Better element targeting
            result_blocks = soup.find_all("div", class_="result")
            for i, block in enumerate(result_blocks):
                title_elem = block.find("a", class_="result__a")
                snippet_elem = block.find("a", class_="result__snippet")
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    raw_href = title_elem.get("href", "")

                    # Extract final URL if wrapped in DuckDuckGo redirect
                    final_url = raw_href
                    if "uddg=" in raw_href:
                        parsed_href = urllib.parse.urlparse(raw_href)
                        qs = urllib.parse.parse_qs(parsed_href.query)
                        if "uddg" in qs:
                            final_url = qs["uddg"][0]

                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                    # Heuristic relevance score based on query words matching in title/snippet
                    score = self._calculate_score(query, title, snippet, i)

                    results.append({
                        "title": title,
                        "url": final_url,
                        "summary": snippet,
                        "score": score,
                        "search_provider": "duckduckgo"
                    })
            return results
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            return []

    def _search_searxng(self, query: str) -> List[Dict[str, Any]]:
        # Future/SearXNG adapter stub, falls back to empty or mock
        return []

    def _calculate_score(self, query: str, title: str, snippet: str, index: int) -> float:
        score = 100.0 - (index * 5.0) # Position discount
        if score < 10.0:
            score = 10.0

        words = [w.lower() for w in query.split() if len(w) > 2]
        matches = 0
        text = (title + " " + snippet).lower()
        for w in words:
            if w in text:
                matches += 1

        # Word match boost
        if words:
            score += (matches / len(words)) * 50.0

        return score
