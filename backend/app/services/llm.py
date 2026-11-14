"""Gemini client (REST, structured JSON output) plus embeddings.

Every caller must handle `None` (LLM unavailable) with a deterministic fallback and label
the result's `engine` field accordingly, so nothing is ever presented as AI output when it isn't.
"""
import hashlib
import logging
import math
import re

import httpx

from ..config import get_settings

log = logging.getLogger("skillforge.llm")
settings = get_settings()
BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def llm_available() -> bool:
    return bool(settings.gemini_api_key)


def engine_label() -> str:
    return f"gemini:{settings.gemini_model}" if llm_available() else "deterministic-fallback"


async def generate_json(prompt: str, schema: dict, system: str = "", temperature: float = 0.2) -> dict | None:
    """Ask Gemini for a JSON object matching `schema`. Returns None on any failure."""
    if not llm_available():
        return None
    body: dict = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{BASE}/{settings.gemini_model}:generateContent",
                headers={"x-goog-api-key": settings.gemini_api_key},
                json=body,
            )
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        import json

        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception as exc:  # network, quota, malformed output -> fallback
        log.warning("Gemini call failed, using fallback: %s", type(exc).__name__)
        return None


# ---------- embeddings ----------

_TOKEN = re.compile(r"[a-z0-9+#]+")


def hash_embedding(text: str, dim: int | None = None) -> list[float]:
    """Deterministic feature-hashing embedding (unigrams + bigrams), L2-normalised."""
    dim = dim or settings.embedding_dim
    vec = [0.0] * dim
    toks = _TOKEN.findall(text.lower())
    grams = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
    for g in grams:
        h = int.from_bytes(hashlib.blake2b(g.encode(), digest_size=8).digest(), "big")
        vec[h % dim] += 1.0 if (h >> 63) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embedding_model_name() -> str:
    return settings.gemini_embedding_model if llm_available() else "hash-v1"


async def embed(text: str) -> tuple[list[float], str]:
    """Returns (vector, model_name). Falls back to hashing if Gemini is unavailable."""
    if llm_available():
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(
                    f"{BASE}/{settings.gemini_embedding_model}:embedContent",
                    headers={"x-goog-api-key": settings.gemini_api_key},
                    json={
                        "content": {"parts": [{"text": text[:8000]}]},
                        "outputDimensionality": settings.embedding_dim,
                    },
                )
                r.raise_for_status()
                vec = r.json()["embedding"]["values"]
                norm = math.sqrt(sum(v * v for v in vec)) or 1.0
                return [v / norm for v in vec], settings.gemini_embedding_model
        except Exception as exc:
            log.warning("Gemini embedding failed, using hash embedding: %s", type(exc).__name__)
    return hash_embedding(text), "hash-v1"


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
