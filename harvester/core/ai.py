import httpx
from typing import List, Dict, Any, Tuple
from harvester.config.config import AppConfig
from harvester.core.models import Summary
from harvester.logging_util import get_logger

logger = get_logger()

class AIService:
    def __init__(self, config: AppConfig):
        self.config = config
        self.ollama_generate_url = f"{config.ollama_base_url}/api/generate"

    def summarize(self, text: str) -> Summary:
        """
        Generates short, long, bulleted, and executive summaries.
        Uses Ollama if enabled and online, otherwise falls back to a deterministic text-trimming summarizer.
        """
        short_summary = ""
        long_summary = ""
        bullet_summary: List[str] = []
        executive_summary = ""

        # Attempt local LLM summarization if enabled
        if self.config.llm_enabled:
            try:
                short_summary = self._ollama_prompt(text, "Write a 1-sentence short summary of the following text:")
                long_summary = self._ollama_prompt(text, f"Write a comprehensive summary of the following text under {self.config.summarization_settings.get('long_len', 500)} words:")
                bullets_raw = self._ollama_prompt(text, "List 5 key bullet points summarizing the main actions/takeaways from this text:")
                bullet_summary = [b.strip("-* ").strip() for b in bullets_raw.split("\n") if b.strip()]
                executive_summary = self._ollama_prompt(text, "Write a professional executive summary of the following text:")

                if short_summary and long_summary:
                    logger.info("Successfully generated AI summaries via Ollama")
                    return Summary(
                        short_summary=short_summary,
                        long_summary=long_summary,
                        bullet_summary=bullet_summary[:self.config.summarization_settings.get('bullets_count', 5)],
                        executive_summary=executive_summary
                    )
            except Exception as e:
                logger.warning(f"Ollama LLM summarization failed: {e}. Falling back to heuristic summary.")

        # Heuristic fallback summarizer (sentence / text manipulation)
        sentences = [s.strip() for s in text.split(".") if s.strip()]

        # Short summary: first sentence
        short_summary = sentences[0] + "." if len(sentences) > 0 else "No content available."

        # Long summary: first 5 sentences
        long_summary = ". ".join(sentences[:5]) + "." if len(sentences) > 0 else "No content available."

        # Bullet summary: up to 5 sentences as bullet points
        bullet_summary = [f"Key Point: {s}." for s in sentences[:5]]

        # Executive summary
        executive_summary = f"This document details high-quality knowledge harvested. Main details cover: {short_summary} Further highlights follow the bulleted summary points."

        return Summary(
            short_summary=short_summary,
            long_summary=long_summary,
            bullet_summary=bullet_summary,
            executive_summary=executive_summary
        )

    def classify_and_tag(self, title: str, text: str) -> List[str]:
        """
        Heuristically classifies articles into domains:
        AI, Cloud, Linux, Security, Programming, Networking, DevOps, Databases, General Technology.
        """
        categories = []
        combined = (title + " " + text).lower()

        # Define keywords for classification
        rules = {
            "AI": ["ai", "artificial intelligence", "llm", "large language", "prompt", "transformer", "neural", "embeddings", "rag", "ollama"],
            "Cloud": ["aws", "cloud", "gcp", "azure", "google cloud", "s3", "ec2", "lambda"],
            "Linux": ["linux", "mint", "ubuntu", "debian", "kernel", "bash", "shell", "red hat"],
            "Security": ["security", "vulnerability", "cve", "cybersecurity", "exploit", "hack", "bypass", "malware", "ransomware"],
            "Programming": ["programming", "python", "rust", "c++", "java", "developer", "coding", "git", "github"],
            "Networking": ["networking", "dns", "http", "tcp", "ip", "router", "switch", "vpn", "cloudflare"],
            "DevOps": ["devops", "kubernetes", "docker", "ci/cd", "terraform", "hashicorp", "ansible"],
            "Databases": ["database", "sqlite", "postgres", "mysql", "mongodb", "sql", "nosql"]
        }

        for cat, keywords in rules.items():
            if any(k in combined for k in keywords):
                categories.append(cat)

        if not categories:
            categories.append("General Technology")

        return categories

    def _ollama_prompt(self, text: str, prompt_prefix: str) -> str:
        payload = {
            "model": self.config.llm_model,
            "prompt": f"{prompt_prefix}\n\n{text[:4000]}",
            "stream": False
        }
        resp = httpx.post(self.ollama_generate_url, json=payload, timeout=25.0)
        if resp.status_code == 200:
            return resp.json().get("response", "").strip()
        raise RuntimeError(f"Ollama returned status code {resp.status_code}")
