import re
import hashlib
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
import trafilatura
from pypdf import PdfReader
from harvester.logging_util import get_logger
from harvester.core.models import Metadata

logger = get_logger()

def compute_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def clean_html_with_soup(html_content: str) -> str:
    """
    Fallback cleaner using BeautifulSoup to remove headers, footers, ads, navigation,
    social share widgets, scripts, styles, newsletter prompts, and cookie notices.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Selectors to remove
    selectors_to_remove = [
        "header", "footer", "nav", "aside", ".ads", ".advertisement",
        ".cookie-banner", ".cookie-notice", ".social-share", ".newsletter-prompt",
        "script", "style", "iframe", "noscript", ".menu", ".sidebar", ".navigation"
    ]

    for selector in selectors_to_remove:
        for tag in soup.select(selector):
            tag.decompose()

    # Also find general text matches in classes/ids
    for tag in soup.find_all(True):
        class_str = " ".join(tag.get("class", [])).lower()
        id_str = tag.get("id", "").lower()
        if any(term in class_str or term in id_str for term in ["cookie", "footer", "header", "menu", "newsletter", "ads"]):
            # Filter to make sure we don't accidentally remove central content
            if tag.name not in ["main", "article", "body"]:
                tag.decompose()

    return str(soup)

class ContentExtractor:
    def __init__(self):
        pass

    def extract_webpage(self, html_content: str, url: str) -> Dict[str, Any]:
        """
        Extracts content using Trafilatura, falling back to BeautifulSoup.
        """
        # First try Trafilatura
        try:
            extracted_text = trafilatura.extract(html_content, include_comments=False, include_tables=True, include_images=False)
            metadata_dict = trafilatura.extract_metadata(html_content)
        except Exception as e:
            logger.warning(f"Trafilatura failed extraction: {e}")
            extracted_text = None
            metadata_dict = None

        soup = BeautifulSoup(html_content, "html.parser")

        # Fallback if trafilatura failed or returned very short content
        if not extracted_text or len(extracted_text.strip()) < 50:
            logger.info("Trafilatura output too short, falling back to BeautifulSoup extraction")
            cleaned_html = clean_html_with_soup(html_content)
            cleaned_soup = BeautifulSoup(cleaned_html, "html.parser")
            extracted_text = cleaned_soup.get_text(separator="\n", strip=True)

        # Build Metadata
        title = ""
        if metadata_dict and getattr(metadata_dict, "title", None):
            title = metadata_dict.title
        else:
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else "Untitled Document"

        # Clean title from common branding
        title = re.sub(r'\s+[-|]\s+.*$', '', title).strip()

        author = None
        if metadata_dict and getattr(metadata_dict, "author", None):
            author = metadata_dict.author
        else:
            author_tag = soup.find("meta", attrs={"name": "author"})
            if author_tag:
                author = author_tag.get("content")

        published_date = None
        if metadata_dict and getattr(metadata_dict, "date", None):
            published_date = metadata_dict.date
        else:
            date_tag = soup.find("meta", attrs={"property": "article:published_time"}) or soup.find("meta", attrs={"name": "date"})
            if date_tag:
                published_date = date_tag.get("content")

        language = "en"
        html_tag = soup.find("html")
        if html_tag and html_tag.get("lang"):
            language = html_tag.get("lang")

        word_count = len(extracted_text.split())
        reading_time = max(1, round(word_count / 200)) # Heuristic 200 words per minute

        # Collect keywords
        keywords = []
        kw_tag = soup.find("meta", attrs={"name": "keywords"})
        if kw_tag and kw_tag.get("content"):
            keywords = [k.strip() for k in kw_tag.get("content").split(",") if k.strip()]

        canonical_tag = soup.find("link", rel="canonical")
        canonical_url = canonical_tag.get("href") if canonical_tag else url

        # Heading extraction for table of contents / structured text
        headings = [h.get_text(strip=True) for h in soup.find_all(["h1", "h2", "h3", "h4"])]

        return {
            "title": title,
            "body_text": extracted_text,
            "body_html": str(soup),
            "headings": headings,
            "author": author,
            "published_date": published_date,
            "language": language,
            "word_count": word_count,
            "reading_time_minutes": reading_time,
            "keywords": keywords,
            "canonical_url": canonical_url
        }

    def extract_pdf(self, pdf_bytes: bytes, url: str) -> Dict[str, Any]:
        """
        Extracts content and metadata from PDF bytes.
        """
        import io
        pdf_file = io.BytesIO(pdf_bytes)
        reader = PdfReader(pdf_file)

        text_content = []
        for i, page in enumerate(reader.pages):
            text_content.append(f"--- Page {i+1} ---\n" + (page.extract_text() or ""))

        full_text = "\n".join(text_content)

        # Extracted document metadata
        pdf_info = reader.metadata
        title = "Untitled PDF"
        author = None

        if pdf_info:
            title = pdf_info.title or title
            author = pdf_info.author or author

        word_count = len(full_text.split())
        reading_time = max(1, round(word_count / 200))

        # Preview HTML
        preview_html = f"""
        <html>
        <head><title>{title}</title></head>
        <body>
        <h1>{title}</h1>
        <p><strong>Source URL:</strong> <a href="{url}">{url}</a></p>
        <p><strong>Author:</strong> {author or 'Unknown'}</p>
        <hr/>
        <pre>{full_text}</pre>
        </body>
        </html>
        """

        return {
            "title": title,
            "body_text": full_text,
            "body_html": preview_html,
            "headings": [],
            "author": author,
            "published_date": None,
            "language": "en",
            "word_count": word_count,
            "reading_time_minutes": reading_time,
            "keywords": ["pdf"],
            "canonical_url": url
        }

    def extract_entities_and_keywords(self, text: str) -> Dict[str, List[str]]:
        """
        Heuristically extracts entities and keywords from text.
        Entities: CVE IDs, cloud providers, technologies, CVE vulnerabilities.
        """
        # Tech extraction list
        tech_keywords = [
            "python", "rust", "go", "java", "c++", "kubernetes", "docker", "aws", "gcp",
            "azure", "google cloud", "linux", "ubuntu", "debian", "fedora", "red hat", "mint",
            "security", "vulnerability", "cve", "openai", "chatgpt", "anthropic", "claude",
            "nvidia", "ollama", "rag", "embeddings", "vector", "database", "sqlite"
        ]

        extracted_tech = []
        text_lower = text.lower()
        for tech in tech_keywords:
            if re.search(r'\b' + re.escape(tech) + r'\b', text_lower):
                extracted_tech.append(tech.capitalize())

        # CVE IDs
        cve_ids = re.findall(r'\bCVE-\d{4}-\d{4,7}\b', text, re.IGNORECASE)
        cve_ids = list(set([c.upper() for c in cve_ids]))

        # Simpler TF-IDF / RAKE style keywords (frequent words excluding English stopwords)
        stopwords = {
            "the", "and", "a", "of", "to", "in", "is", "that", "it", "for", "on", "with", "as",
            "this", "are", "by", "an", "be", "this", "from", "at", "not", "but", "have", "or"
        }
        words = re.findall(r'\b[a-z]{4,15}\b', text_lower)
        word_counts = {}
        for w in words:
            if w not in stopwords:
                word_counts[w] = word_counts.get(w, 0) + 1

        sorted_kws = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        keywords = [k for k, _ in sorted_kws[:10]]

        return {
            "technologies": list(set(extracted_tech)),
            "cve_ids": cve_ids,
            "keywords": keywords
        }
