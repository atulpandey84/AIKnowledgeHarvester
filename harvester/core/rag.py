import httpx
import json
from typing import List, Dict, Any, Optional
from harvester.config.config import AppConfig
from harvester.database.sqlite_db import SQLiteDatabase
from harvester.embeddings.generator import EmbeddingGenerator, cosine_similarity
from harvester.logging_util import get_logger

logger = get_logger()

class LocalRAGQueryEngine:
    def __init__(self, config: AppConfig, db: SQLiteDatabase):
        self.config = config
        self.db = db
        self.embed_gen = EmbeddingGenerator(config)

    def query(self, user_question: str, top_k: int = 3) -> Dict[str, Any]:
        """
        Coordinates full end-to-end Local RAG flow:
        1. Generate query vector from user question using embedding model.
        2. Query SQLite embeddings table and compute cosine similarity against stored articles.
        3. Retrieve context and build context-grounded prompt.
        4. Query local Ollama LLM to formulate offline response.
        """
        logger.info(f"RAG query received: '{user_question}'")

        # 1. Generate Query Embedding
        query_emb = self.embed_gen.generate(user_question)

        # 2. Retrieve all stored article embeddings from database
        candidates = []
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT a.id, a.title, a.source_url, a.published_date, a.body_text, e.vector, e.model
                FROM articles a
                JOIN embeddings e ON a.id = e.article_id
            """)
            for row in cur.fetchall():
                try:
                    vec = json.loads(row["vector"].decode("utf-8"))
                    candidates.append({
                        "id": row["id"],
                        "title": row["title"],
                        "source_url": row["source_url"],
                        "published_date": row["published_date"],
                        "body_text": row["body_text"],
                        "vector": vec,
                        "model": row["model"]
                    })
                except Exception as e:
                    logger.error(f"Error parsing candidate vector: {e}")

        # Calculate cosine similarity against candidate articles
        ranked_results = []
        for cand in candidates:
            sim = cosine_similarity(query_emb.vector, cand["vector"])
            ranked_results.append((sim, cand))

        # Sort descending by similarity
        ranked_results = sorted(ranked_results, key=lambda x: x[0], reverse=True)
        top_matches = ranked_results[:top_k]

        # Build contextual prompt
        context_blocks = []
        sources = []
        for sim, cand in top_matches:
            # Only include context if it is reasonably semantically related
            if sim > 0.15:
                context_blocks.append(
                    f"--- START SOURCE: {cand['title']} ({cand['source_url']}) ---\n"
                    f"Published Date: {cand['published_date'] or 'Unknown'}\n"
                    f"Content: {cand['body_text'][:1500]}\n"
                    f"--- END SOURCE ---"
                )
                sources.append({
                    "id": cand["id"],
                    "title": cand["title"],
                    "source_url": cand["source_url"],
                    "score": round(sim, 4)
                })

        context_text = "\n\n".join(context_blocks)

        # Ground prompt with context rules
        prompt = f"""You are a professional local AI assistant. Use strictly only the retrieved local context below to answer the user's question.
If the retrieved context is empty, does not contain the answer, or is not relevant, rely on your general pre-existing knowledge but clearly state that the answer was not found in the freshly harvested local knowledge base.

--- START LOCAL CONTEXT ---
{context_text or "No relevant fresh local knowledge was found."}
--- END LOCAL CONTEXT ---

User Question: {user_question}

Answer:"""

        # 4. Generate answer with Ollama
        response_text = ""
        if self.config.ollama_base_url:
            try:
                payload = {
                    "model": self.config.llm_model,
                    "prompt": prompt,
                    "stream": False
                }
                resp = httpx.post(f"{self.config.ollama_base_url}/api/generate", json=payload, timeout=30.0)
                if resp.status_code == 200:
                    response_text = resp.json().get("response", "").strip()
            except Exception as e:
                logger.warning(f"Failed to query Ollama LLM: {e}")

        if not response_text:
            # Heuristic fallback if LLM is offline
            if sources:
                response_text = (
                    f"[Local Offline Fallback Engine]: Found {len(sources)} semantically relevant articles matching your query. "
                    f"The top source is '{sources[0]['title']}'. Please start Ollama server to get full AI synthesis answers."
                )
            else:
                response_text = "[Local Offline Fallback Engine]: No freshly harvested articles found matching this query. Please trigger 'harvester run' to crawl updates."

        return {
            "query": user_question,
            "answer": response_text,
            "sources": sources
        }
