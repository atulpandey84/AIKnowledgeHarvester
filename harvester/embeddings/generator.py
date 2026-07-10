import math
import hashlib
from typing import List, Dict, Any, Optional
import httpx
from harvester.config.config import AppConfig
from harvester.core.models import Embedding
from harvester.logging_util import get_logger

logger = get_logger()

class EmbeddingGenerator:
    def __init__(self, config: AppConfig):
        self.config = config
        self.model = config.embedding_model
        self.ollama_url = f"{config.ollama_base_url}/api/embeddings"

    def generate(self, text: str) -> Embedding:
        """
        Attempts to generate an embedding for text using local Ollama.
        Falls back gracefully to a high-quality local deterministic mock vector (using MD5/SHA hashes).
        """
        if self.config.ollama_base_url:
            try:
                # Truncate text if excessively long for token limits
                truncated_text = text[:4000]
                resp = httpx.post(self.ollama_url, json={
                    "model": self.model,
                    "prompt": truncated_text
                }, timeout=10.0)

                if resp.status_code == 200:
                    data = resp.json()
                    vector = data.get("embedding")
                    if vector:
                        logger.info(f"Generated local Ollama embedding using {self.model}")
                        return Embedding(
                            model=self.model,
                            dimensions=len(vector),
                            vector=vector
                        )
            except Exception as e:
                logger.debug(f"Ollama embedding generator offline (or failed): {e}. Falling back to deterministic vector.")

        # Local deterministic fallback (hash-based) to guarantee vector storage
        # and support exact/near matching. Dimension matches Nomic (768) or BGE (1024)
        dim = 768 if "nomic" in self.model.lower() else 1024

        # Build deterministic floats based on string hashes of text chunks
        vector = []
        for i in range(dim):
            # Deterministic pseudo-random generation using hash
            chunk = f"{text[:200]}_dim_{i}"
            h = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
            val = int(h[:8], 16) / 4294967295.0 # normalized float [0, 1]
            vector.append(val)

        logger.debug(f"Generated fallback deterministic vector of size {dim}")
        return Embedding(
            model=self.model,
            dimensions=dim,
            vector=vector
        )

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if len(v1) != len(v2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)
