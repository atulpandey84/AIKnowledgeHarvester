from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class Topic:
    name: str
    priority: str = "Medium" # High, Medium, Low
    category: Optional[str] = None
    weight: float = 1.0
    enabled: bool = True
    raw_line: str = ""

@dataclass
class Metadata:
    title: str
    source_url: str
    canonical_url: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    published_date: Optional[str] = None
    updated_date: Optional[str] = None
    language: Optional[str] = "en"
    country: Optional[str] = None
    reading_time_minutes: Optional[int] = None
    word_count: Optional[int] = None
    sha256: str = ""
    harvest_timestamp: str = ""
    topic: str = ""
    search_provider: Optional[str] = None
    rss_feed: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    license: Optional[str] = None
    content_type: str = "text/html"

@dataclass
class DownloadedAsset:
    original_url: str
    local_path: str
    mime_type: str
    size_bytes: int

@dataclass
class Summary:
    short_summary: str = ""
    long_summary: str = ""
    bullet_summary: List[str] = field(default_factory=list)
    executive_summary: str = ""

@dataclass
class Embedding:
    model: str
    dimensions: int
    vector: List[float]

@dataclass
class Article:
    id: Optional[int] = None
    title: str = ""
    body_text: str = ""
    body_html: str = ""
    markdown: str = ""
    metadata: Optional[Metadata] = None
    summary: Optional[Summary] = None
    embeddings: List[Embedding] = field(default_factory=list)
    images: List[DownloadedAsset] = field(default_factory=list)
    pdf_path: Optional[str] = None
