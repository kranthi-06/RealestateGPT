"""RealEstateGPT - Embeddings service.

Provider abstraction around text embeddings.
- local:   lightweight hashed TF-IDF vectors computed in-process (fully offline)
- openai:  remote embeddings via OpenAI-compatible API when configured

Vectors are currently computed in process; a future embedding persistence
implementation must use MongoDB-compatible storage and remain optional.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Dict, List, Optional, Sequence

from app.core.config import settings

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "of", "for", "to", "with",
    "near", "close", "within", "want", "need", "looking", "under", "over", "this",
    "that", "is", "are", "be", "it", "at", "by", "from", "as", "not", "my", "me",
    "property", "properties", "bhk", "sqft", "rs", "inr", "price", "around",
    "about", "preferably", "preferably", "have", "has", "should", "would",
}

_DIM = 256


def _hash_index(token: str, dim: int) -> int:
    return int(hashlib.md5(token.encode("utf-8")).hexdigest()[:8], 16) % dim


def tokenize(text: str) -> List[str]:
    tokens = []
    for match in _TOKEN_RE.findall(text.lower()):
        if match not in _STOPWORDS and len(match) > 1:
            tokens.append(match)
    return tokens


def _tf_idf_vector(tokens: Sequence[str], doc_freq: Optional[Dict[str, int]] = None,
                   total_docs: int = 1, dim: int = _DIM) -> List[float]:
    """Basic frequency vector with optional IDF weighting (no huge memory use)."""
    tf: Dict[str, int] = {}
    for token in tokens:
        tf[token] = tf.get(token, 0) + 1
    total = len(tokens) or 1
    vector = [0.0] * dim
    for token, count in tf.items():
        tfv = count / total
        if doc_freq:
            df = doc_freq.get(token, 1)
            idf = math.log((1 + total_docs) / (1 + df)) + 1.0
            tfv *= idf
        vector[_hash_index(token, dim)] += tfv
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [round(v / norm, 6) for v in vector]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return float(dot)  # vectors are L2 normalized


def build_document_frequencies(texts: Sequence[str]) -> Dict[str, int]:
    df: Dict[str, int] = {}
    for text in texts:
        for token in set(tokenize(text)):
            df[token] = df.get(token, 0) + 1
    return df


class EmbeddingService:
    """Computes embeddings and similarities. Thread-safe for reads after construction."""

    def __init__(self) -> None:
        self._provider = settings.EMBEDDING_PROVIDER
        self._explicit_vectors: Dict[str, List[float]] = {}
        self._doc_freq: Dict[str, int] = {}

    @property
    def provider(self) -> str:
        return self._provider

    def fit_documents(self, texts: Sequence[str]) -> None:
        """Precompute global IDF stats over the document corpus."""
        self._doc_freq = build_document_frequencies(texts)
        logger.info("EmbeddingService fitted over %d documents", len(texts))

    def embed(self, text: str) -> List[float]:
        key = text.strip().lower()
        if key in self._explicit_vectors:
            return self._explicit_vectors[key]
        if self._provider == "openai":
            vector = self._embed_openai(text)
        else:
            vector = _tf_idf_vector(tokenize(text), self._doc_freq, total_docs=max(1, len(self._doc_freq)))
        self._explicit_vectors[key] = vector
        return vector

    def _embed_openai(self, text: str) -> List[float]:
        # Real API embeddings when configured; graceful fallback to local vectors.
        api_key = settings.AI_API_KEY
        if not api_key:
            return _tf_idf_vector(tokenize(text), self._doc_freq)
        try:
            import httpx

            base = (settings.AI_BASE_URL or "https://api.openai.com/v1").rstrip("/")
            resp = httpx.post(
                f"{base}/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": settings.EMBEDDING_MODEL, "input": text},
                timeout=float(settings.AI_TIMEOUT_SECONDS),
            )
            resp.raise_for_status()
            data = resp.json()["data"][0]["embedding"]
            if not isinstance(data, list) or not all(isinstance(value, (int, float)) for value in data):
                raise ValueError("Embedding provider returned an invalid vector")
            norm = math.sqrt(sum(v * v for v in data)) or 1.0
            return [round(v / norm, 6) for v in data]
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAI embeddings failed (%s); falling back to local", exc)
            return _tf_idf_vector(tokenize(text), self._doc_freq)

    def similarity(self, a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        return cosine_similarity(self.embed(a), self.embed(b))

    def similarity_batch(self, query: str, documents: Sequence[str]) -> List[float]:
        qv = self.embed(query)
        return [cosine_similarity(qv, self.embed(doc)) for doc in documents]


_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    global _service
    if _service is None:
        _service = EmbeddingService()
    return _service
