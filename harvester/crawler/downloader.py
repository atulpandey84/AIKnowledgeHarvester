import time
import random
import threading
import urllib.robotparser
from urllib.parse import urlparse
import httpx
from harvester.logging_util import get_logger
from harvester.config.config import AppConfig

logger = get_logger()

class HTTPDownloader:
    def __init__(self, config: AppConfig, config_file: str = "config.yaml"):
        self.config = config
        self.config_file = config_file
        # Setup connection pool and configuration options
        self.limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        self.client = httpx.Client(
            limits=self.limits,
            http2=True,
            timeout=httpx.Timeout(config.timeout),
            follow_redirects=True
        )
        self.robots_cache = {}

        # Domain-specific rate limiting and delay scaling with threading Lock protection
        self.lock = threading.Lock()
        self.domain_delays = {} # domain -> current delay in seconds
        self.last_request_times = {} # domain -> timestamp of last request

    def get_random_user_agent(self) -> str:
        return random.choice(self.config.user_agent_pool)

    def is_allowed_by_robots(self, url: str) -> bool:
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        robots_url = f"{base_url}/robots.txt"

        with self.lock:
            if robots_url in self.robots_cache:
                rp = self.robots_cache[robots_url]
                cached = True
            else:
                cached = False

        if cached:
            user_agent = self.get_random_user_agent()
            return rp.can_fetch(user_agent, url)

        rp = urllib.robotparser.RobotFileParser()
        try:
            # Set a custom user agent to fetch robots.txt
            headers = {"User-Agent": self.get_random_user_agent()}
            resp = httpx.get(robots_url, headers=headers, timeout=5.0, follow_redirects=True)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            else:
                rp.allow_all = True
        except Exception:
            rp.allow_all = True

        with self.lock:
            self.robots_cache[robots_url] = rp

        user_agent = self.get_random_user_agent()
        return rp.can_fetch(user_agent, url)

    def _auto_prune_failed_service(self, url: str):
        """
        Dynamically removes unresolved or non-existent feeds or search website domains from the config.
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        with self.lock:
            # 1. Check & remove from search_websites
            if domain in self.config.search_websites:
                logger.warning(f"Auto-pruning invalid search website: {domain}")
                self.config.search_websites.remove(domain)
                self.config.save_to_yaml(self.config_file)

            # 2. Check & remove from rss_feeds
            feed_to_remove = None
            for feed in self.config.rss_feeds:
                feed_url = feed.get("url", "")
                if feed_url == url or urlparse(feed_url).netloc.lower() == domain:
                    feed_to_remove = feed
                    break
            if feed_to_remove:
                logger.warning(f"Auto-pruning invalid RSS feed: {feed_to_remove['name']} ({feed_to_remove['url']})")
                self.config.rss_feeds.remove(feed_to_remove)
                self.config.save_to_yaml(self.config_file)

    def download(self, url: str, stream: bool = False) -> httpx.Response:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Domain check
        if domain in self.config.ignored_domains:
            raise ValueError(f"Domain {domain} is ignored in settings.")

        if self.config.allowed_domains and domain not in self.config.allowed_domains:
            raise ValueError(f"Domain {domain} is not in the allowed list.")

        # Respect robots.txt
        if not self.is_allowed_by_robots(url):
            logger.warning(f"Robots.txt forbids crawling url: {url}")

        # Domain-specific adaptive rate limiting
        with self.lock:
            # Determine base delay for this domain
            if domain not in self.domain_delays:
                self.domain_delays[domain] = self.config.rate_limiting_delay_seconds

            last_time = self.last_request_times.get(domain, 0.0)
            required_delay = self.domain_delays[domain]

        elapsed = time.time() - last_time
        if elapsed < required_delay:
            wait_time = required_delay - elapsed
            logger.info(f"Enforcing rate limit spacing for domain '{domain}': sleeping {wait_time:.2f}s")
            time.sleep(wait_time)

        # Retries with randomized backoff and delay
        retries = self.config.retry_count

        for attempt in range(1, retries + 2):
            with self.lock:
                # Update last request time
                self.last_request_times[domain] = time.time()

            try:
                # Add slight random jitter
                time.sleep(random.uniform(0.1, 0.5))

                headers = {
                    "User-Agent": self.get_random_user_agent(),
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5"
                }

                logger.debug(f"Attempting download: {url} (Attempt {attempt}/{retries + 1})")

                if stream:
                    response = self.client.get(url, headers=headers)
                else:
                    response = self.client.get(url, headers=headers)

                # Check for Retry-After
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            sleep_time = int(retry_after)
                        except ValueError:
                            sleep_time = 5
                        logger.warning(f"Rate limited (429). Respecting Retry-After: sleeping for {sleep_time}s")
                        time.sleep(sleep_time)
                    raise httpx.HTTPStatusError("Rate Limited", request=response.request, response=response)

                response.raise_for_status()

                with self.lock:
                    # Success: gradually cool down the delay towards config default
                    self.domain_delays[domain] = max(
                        self.config.rate_limiting_delay_seconds,
                        self.domain_delays[domain] * 0.8
                    )
                return response

            except (httpx.HTTPError, httpx.HTTPStatusError) as e:
                error_msg = str(e)
                status_code = getattr(e, "response", None) and getattr(e.response, "status_code", None)

                # Catch unresolved domain DNS failures or connection failures
                if "Name or service not known" in error_msg or "gai_error" in error_msg or "unresolved" in error_msg.lower():
                    logger.error(f"downloader: Error downloading {url}: [Errno -2] Name or service not known")
                    self._auto_prune_failed_service(url)
                    raise httpx.HTTPError(f"downloader: Error downloading {url}: [Errno -2] Name or service not known") from e

                # Catch 403 Forbidden or 429 Rate Limited
                if status_code in (403, 429):
                    with self.lock:
                        # Backoff and scale up delays adaptively
                        current_delay = self.domain_delays[domain]
                        new_delay = max(5.0, current_delay * 2.0)
                        self.domain_delays[domain] = new_delay

                    logger.warning(
                        f"Encountered status {status_code} for domain '{domain}'. "
                        f"Scaling up adaptive delay to {new_delay:.1f}s. Rotating User-Agent..."
                    )

                    if attempt < retries + 1:
                        # Sleep before retry
                        time.sleep(new_delay)
                        continue

                logger.error(f"Error downloading {url}: {e}")
                if attempt == retries + 1:
                    raise e
                # General Backoff
                time.sleep(required_delay * (2 ** attempt))

        raise httpx.HTTPError("Max retries exceeded")

    def download_image(self, url: str) -> bytes:
        response = self.download(url)
        content_len = len(response.content)
        if content_len > self.config.max_image_size_bytes:
            raise ValueError(f"Image is too large ({content_len} bytes)")
        return response.content

    def close(self):
        self.client.close()
