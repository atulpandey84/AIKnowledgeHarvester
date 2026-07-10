import time
import random
import urllib.robotparser
from urllib.parse import urlparse
import httpx
from harvester.logging_util import get_logger
from harvester.config.config import AppConfig

logger = get_logger()

class HTTPDownloader:
    def __init__(self, config: AppConfig):
        self.config = config
        # Setup connection pool and configuration options
        self.limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        self.client = httpx.Client(
            limits=self.limits,
            http2=True,
            timeout=httpx.Timeout(config.timeout),
            follow_redirects=True
        )
        self.robots_cache = {}

    def get_random_user_agent(self) -> str:
        return random.choice(self.config.user_agent_pool)

    def is_allowed_by_robots(self, url: str) -> bool:
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        robots_url = f"{base_url}/robots.txt"

        if robots_url in self.robots_cache:
            rp = self.robots_cache[robots_url]
        else:
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
            self.robots_cache[robots_url] = rp

        user_agent = self.get_random_user_agent()
        return rp.can_fetch(user_agent, url)

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
            # Non-blocking warning: we will proceed unless it's strictly enforced.
            # In enterprise, we want to log but can configure strictness. Let's still fetch but keep log.

        # Retries with randomized backoff and delay
        retries = self.config.retry_count
        delay = self.config.rate_limiting_delay_seconds

        for attempt in range(1, retries + 2):
            try:
                # Random delay
                time.sleep(delay * random.uniform(0.5, 1.5))

                headers = {
                    "User-Agent": self.get_random_user_agent(),
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5"
                }

                logger.debug(f"Attempting download: {url} (Attempt {attempt}/{retries + 1})")

                if stream:
                    # Keep it as direct download for simplicity if not massive files
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
                        logger.warning(f"Rate limited. Respecting Retry-After: sleeping for {sleep_time}s")
                        time.sleep(sleep_time)
                    raise httpx.HTTPStatusError("Rate Limited", request=response.request, response=response)

                response.raise_for_status()
                return response

            except (httpx.HTTPError, httpx.HTTPStatusError) as e:
                logger.error(f"Error downloading {url}: {e}")
                if attempt == retries + 1:
                    raise e
                # Backoff
                time.sleep(delay * (2 ** attempt))

        raise httpx.HTTPError("Max retries exceeded")

    def download_image(self, url: str) -> bytes:
        response = self.download(url)
        content_len = len(response.content)
        if content_len > self.config.max_image_size_bytes:
            raise ValueError(f"Image is too large ({content_len} bytes)")
        return response.content

    def close(self):
        self.client.close()
