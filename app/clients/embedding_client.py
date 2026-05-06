import logging
import time
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 100
MAX_INPUT_CHARS = 2048
MAX_RETRY = 3
RETRY_BASE_DELAY = 2.0
EMBEDDING_DIM = 768
COST_PER_1K_CHARS_USD = 0.000025


class EmbeddingClient:
    def __init__(self) -> None:
        self._model = None
        self._init_error: Optional[str] = None
        try:
            from vertexai.language_models import TextEmbeddingModel
            import vertexai

            vertexai.init(
                project=settings.GCP_PROJECT_ID,
                location=settings.VERTEX_LOCATION,
            )
            self._model = TextEmbeddingModel.from_pretrained(settings.EMBEDDING_MODEL)
            logger.info(
                "Initialized Vertex Embedding Client (model=%s, location=%s)",
                settings.EMBEDDING_MODEL,
                settings.VERTEX_LOCATION,
            )
        except Exception as exc:
            self._init_error = str(exc)
            logger.error("Failed to initialize Vertex Embedding Client: %s", exc)

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    def embed_batch(
        self,
        texts: list[str],
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> tuple[list[Optional[list[float]]], list[int], int]:
        """
        Returns (embeddings_or_none, failed_indices, total_chars).
        embeddings_or_none[i] is None if that text failed.
        """
        if not self.is_ready:
            raise RuntimeError(f"Embedding client not initialized: {self._init_error}")

        prepared = [_prepare_text(t) for t in texts]
        results: list[Optional[list[float]]] = [None] * len(prepared)
        failed: list[int] = []
        total_chars = sum(len(t) for t in prepared)

        for start in range(0, len(prepared), batch_size):
            chunk = prepared[start : start + batch_size]
            indices = list(range(start, start + len(chunk)))
            valid_pairs = [(i, t) for i, t in zip(indices, chunk) if t]
            if not valid_pairs:
                failed.extend(indices)
                continue

            valid_indices = [i for i, _ in valid_pairs]
            valid_texts = [t for _, t in valid_pairs]
            try:
                vectors = self._call_with_retry(valid_texts)
                for i, vec in zip(valid_indices, vectors):
                    results[i] = vec
                empty_indices = [i for i in indices if i not in set(valid_indices)]
                failed.extend(empty_indices)
            except Exception as exc:
                logger.error(
                    "Embedding batch failed (start=%d, size=%d): %s",
                    start,
                    len(chunk),
                    exc,
                )
                failed.extend(indices)

        return results, failed, total_chars

    def _call_with_retry(self, texts: list[str]) -> list[list[float]]:
        last_exc: Optional[Exception] = None
        for attempt in range(MAX_RETRY):
            try:
                response = self._model.get_embeddings(texts)
                return [r.values for r in response]
            except Exception as exc:
                last_exc = exc
                if attempt + 1 < MAX_RETRY:
                    delay = RETRY_BASE_DELAY * (2**attempt)
                    logger.warning(
                        "Embedding call attempt %d/%d failed: %s — retrying in %.1fs",
                        attempt + 1,
                        MAX_RETRY,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
        raise last_exc if last_exc else RuntimeError("Embedding call failed without exception")


def _prepare_text(raw: str) -> str:
    if not raw:
        return ""
    text = raw.strip()
    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS]
    return text


def estimate_cost_usd(total_chars: int) -> float:
    return round(total_chars / 1000 * COST_PER_1K_CHARS_USD, 6)
