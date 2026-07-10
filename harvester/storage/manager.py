import os
import re
import json
import mimetypes
from urllib.parse import urlparse, urljoin
from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup
from harvester.config.config import AppConfig
from harvester.core.models import Article, Metadata, DownloadedAsset, Summary
from harvester.crawler.downloader import HTTPDownloader
from harvester.logging_util import get_logger

logger = get_logger()

# HTML template with dark mode and styling
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="{language}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <style>
        :root {{
            --bg-color: #121212;
            --text-color: #e0e0e0;
            --primary-color: #29b6f6;
            --card-bg: #1e1e1e;
            --border-color: #333333;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            background-color: var(--bg-color);
            color: var(--text-color);
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        h1, h2, h3, h4 {{
            color: var(--primary-color);
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 8px;
        }}
        .metadata-box {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 30px;
            font-size: 0.9em;
        }}
        .metadata-box table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .metadata-box td {{
            padding: 4px 8px;
        }}
        .metadata-box td.label {{
            font-weight: bold;
            color: var(--primary-color);
            width: 150px;
        }}
        pre, code {{
            background-color: #272727;
            border-radius: 4px;
            font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace;
            font-size: 0.9em;
        }}
        pre {{
            padding: 15px;
            overflow-x: auto;
            border: 1px solid var(--border-color);
        }}
        code {{
            padding: 2px 4px;
        }}
        img {{
            max-width: 100%;
            height: auto;
            border-radius: 6px;
            display: block;
            margin: 20px auto;
            border: 1px solid var(--border-color);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            border: 1px solid var(--border-color);
            padding: 8px 12px;
            text-align: left;
        }}
        th {{
            background-color: var(--card-bg);
            color: var(--primary-color);
        }}
        a {{
            color: var(--primary-color);
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <h1>{title}</h1>

    <div class="metadata-box">
        <table>
            <tr>
                <td class="label">Source URL:</td>
                <td><a href="{source_url}" target="_blank">{source_url}</a></td>
            </tr>
            <tr>
                <td class="label">Publisher:</td>
                <td>{publisher}</td>
            </tr>
            <tr>
                <td class="label">Published Date:</td>
                <td>{published_date}</td>
            </tr>
            <tr>
                <td class="label">Harvest Date:</td>
                <td>{harvest_timestamp}</td>
            </tr>
            <tr>
                <td class="label">Topic:</td>
                <td>{topic}</td>
            </tr>
            <tr>
                <td class="label">Keywords:</td>
                <td>{keywords}</td>
            </tr>
        </table>
    </div>

    <article>
        {body_html}
    </article>
</body>
</html>
"""

class StorageManager:
    def __init__(self, config: AppConfig, downloader: HTTPDownloader):
        self.config = config
        self.downloader = downloader

    def sanitize_filename(self, name: str) -> str:
        """Sanitizes names into filesystem friendly strings."""
        return re.sub(r'[^a-zA-Z0-9_\-]', '_', name).strip('_')

    def build_article_path(self, topic: str, title: str, date_str: str = "") -> str:
        """
        Builds local folder path: KnowledgeBase/YYYY/MM/Topic_Name/Article_Name/
        """
        # Parse date
        year = "2026"
        month = "01"
        if date_str:
            # simple extract YYYY and MM
            match = re.search(r'(\d{4})[-/](\d{2})', date_str)
            if match:
                year, month = match.groups()

        safe_topic = self.sanitize_filename(topic)
        safe_title = self.sanitize_filename(title)

        path = os.path.join(
            self.config.base_storage_path,
            year,
            month,
            safe_topic,
            safe_title
        )
        return path

    def download_and_rewrite_images(self, html_content: str, folder_path: str, url: str) -> Tuple[str, List[DownloadedAsset]]:
        """
        Downloads webpage images locally, rewrites HTML/Markdown paths, and discards tracking pixels.
        """
        if not self.config.download_images:
            return html_content, []

        soup = BeautifulSoup(html_content, "html.parser")
        images_dir = os.path.join(folder_path, "images")
        downloaded_assets: List[DownloadedAsset] = []

        os.makedirs(images_dir, exist_ok=True)
        img_tags = soup.find_all("img")

        counter = 1
        for tag in img_tags:
            src = tag.get("src") or tag.get("data-src")
            if not src:
                continue

            img_url = urljoin(url, src)

            # Simple tracking pixel check
            width = tag.get("width")
            height = tag.get("height")
            if width == "1" or height == "1" or "pixel" in img_url.lower():
                tag.decompose()
                continue

            # Parse extension
            parsed = urlparse(img_url)
            ext = os.path.splitext(parsed.path)[1].lower()
            if ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"]:
                ext = ".jpg" # Default fallback

            filename = f"img{counter:03d}{ext}"
            local_img_path = os.path.join(images_dir, filename)

            try:
                img_data = self.downloader.download_image(img_url)

                # Check minimum dimension size if specified
                if len(img_data) < 1000: # Discard extremely tiny images < 1KB (probably icons/tracking)
                    continue

                with open(local_img_path, "wb") as f:
                    f.write(img_data)

                # Rewrite HTML src tag to relative path
                tag["src"] = f"images/{filename}"
                if "data-src" in tag.attrs:
                    del tag["data-src"]
                if "srcset" in tag.attrs:
                    del tag["srcset"]

                mime_type, _ = mimetypes.guess_type(local_img_path)

                asset = DownloadedAsset(
                    original_url=img_url,
                    local_path=os.path.join("images", filename),
                    mime_type=mime_type or "image/jpeg",
                    size_bytes=len(img_data)
                )
                downloaded_assets.append(asset)
                counter += 1

            except Exception as e:
                logger.warning(f"Failed to download image {img_url}: {e}")
                # Fallback: remove or leave source intact

        return str(soup), downloaded_assets

    def generate_markdown(self, title: str, text_content: str, metadata: Metadata) -> str:
        """Generates clean Markdown for RAG or Obsidian."""
        md_lines = [
            f"# {title}",
            "",
            f"**Source:** [{metadata.source_url}]({metadata.source_url})",
            f"**Topic:** {metadata.topic}",
            f"**Publisher:** {metadata.publisher or 'Unknown'}",
            f"**Published Date:** {metadata.published_date or 'Unknown'}",
            f"**Harvest Date:** {metadata.harvest_timestamp}",
            f"**Keywords:** {', '.join(metadata.keywords)}",
            "",
            "---",
            "",
            text_content
        ]
        return "\n".join(md_lines)

    def write_article_files(self, article: Article) -> str:
        """
        Saves article files: article.html, article.md, article.json, summary.md, metadata.json.
        Returns the article folder path.
        """
        meta = article.metadata
        if not meta:
            raise ValueError("Article metadata must not be None")

        folder_path = self.build_article_path(meta.topic, article.title, meta.published_date or meta.harvest_timestamp)
        os.makedirs(folder_path, exist_ok=True)

        # Download images and rewrite html path
        rewritten_html, downloaded_imgs = self.download_and_rewrite_images(
            article.body_html, folder_path, meta.source_url
        )
        article.images = downloaded_imgs
        article.body_html = rewritten_html

        # Render clean offline HTML
        html_output = HTML_TEMPLATE.format(
            title=article.title,
            language=meta.language or "en",
            source_url=meta.source_url,
            publisher=meta.publisher or "Unknown",
            published_date=meta.published_date or "Unknown",
            harvest_timestamp=meta.harvest_timestamp,
            topic=meta.topic,
            keywords=", ".join(meta.keywords),
            body_html=article.body_html
        )

        # Build Markdown
        article.markdown = self.generate_markdown(article.title, article.body_text, meta)

        # Save HTML
        with open(os.path.join(folder_path, "article.html"), "w", encoding="utf-8") as f:
            f.write(html_output)

        # Save Markdown
        with open(os.path.join(folder_path, "article.md"), "w", encoding="utf-8") as f:
            f.write(article.markdown)

        # Save Metadata JSON
        meta_dict = {
            "title": meta.title,
            "source_url": meta.source_url,
            "canonical_url": meta.canonical_url,
            "author": meta.author,
            "publisher": meta.publisher,
            "published_date": meta.published_date,
            "updated_date": meta.updated_date,
            "language": meta.language,
            "country": meta.country,
            "reading_time_minutes": meta.reading_time_minutes,
            "word_count": meta.word_count,
            "sha256": meta.sha256,
            "harvest_timestamp": meta.harvest_timestamp,
            "topic": meta.topic,
            "search_provider": meta.search_provider,
            "rss_feed": meta.rss_feed,
            "keywords": meta.keywords,
            "categories": meta.categories,
            "license": meta.license,
            "content_type": meta.content_type,
            "images": [{"original_url": img.original_url, "local_path": img.local_path, "size": img.size_bytes} for img in downloaded_imgs]
        }
        with open(os.path.join(folder_path, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(meta_dict, f, indent=4, ensure_ascii=False)

        # Save Article JSON (full structure)
        article_dict = {
            "title": article.title,
            "body_text": article.body_text,
            "markdown": article.markdown,
            "metadata": meta_dict
        }
        with open(os.path.join(folder_path, "article.json"), "w", encoding="utf-8") as f:
            json.dump(article_dict, f, indent=4, ensure_ascii=False)

        # Save Summary Markdown
        if article.summary:
            sum_lines = [
                f"# Executive Summary: {article.title}",
                "",
                f"### Short Summary",
                article.summary.short_summary,
                "",
                f"### Executive Overview",
                article.summary.executive_summary,
                "",
                f"### Key Highlights",
            ]
            for bullet in article.summary.bullet_summary:
                sum_lines.append(f"- {bullet}")
            sum_lines.append("")
            sum_lines.append(f"### Long Summary")
            sum_lines.append(article.summary.long_summary)

            with open(os.path.join(folder_path, "summary.md"), "w", encoding="utf-8") as f:
                f.write("\n".join(sum_lines))

        # If PDF copy is available locally, move or download original PDF
        # That logic can be handled in downloader or pipeline
        return folder_path
