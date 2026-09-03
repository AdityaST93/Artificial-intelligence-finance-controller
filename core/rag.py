"""
Vector RAG (ChromaDB) for smart Q&A over reconciled finance data.

Provides:
  - index_reconciled_data(): one-time ingestion of the 4 source CSVs
    into a persistent ChromaDB collection, with metadata = the
    original row (so a hit tells us exactly which row matched).
  - retrieve_context(query, k=5): embed the query and return the
    top-k most similar documents with their metadata and scores.

Embeddings:
  - Primary: sentence-transformers/all-MiniLM-L6-v2 (small, fast, free)
  - Fallback: a deterministic hash-based pseudo-embedding so the
    pipeline still works fully offline (no model download, no network).

Storage:
  - chromadb.PersistentClient at ./chroma_db (no server, no docker).
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent.parent / "data" / "synthetic"
CHROMA_DIR = Path(__file__).parent.parent / "chroma_db"
COLLECTION_NAME = "reconciled_finance"
EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM = 384  # all-MiniLM-L6-v2 native dim; fallback also produces this dim
FALLBACK_DIM = 384


# ---------------------------------------------------------------------------
# Embedding model (lazy init)
# ---------------------------------------------------------------------------

_embedder = None
_embedder_kind: Optional[str] = None  # "st" or "hash"


def _get_embedder():
    """Return (embed_fn, dim, kind). Lazy-init sentence-transformers, else hash fallback."""
    global _embedder, _embedder_kind
    if _embedder is not None:
        return _embedder, EMBED_DIM, _embedder_kind

    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        # Suppress noisy progress bars
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
        _embedder = SentenceTransformer(EMBED_MODEL_NAME)
        _embedder_kind = "st"
        logger.info("RAG using sentence-transformers (%s)", EMBED_MODEL_NAME)
    except Exception as e:  # noqa: BLE001
        logger.warning("sentence-transformers unavailable (%s); using hash fallback", e)
        _embedder = _hash_embed_text
        _embedder_kind = "hash"

    return _embedder, EMBED_DIM, _embedder_kind


def _hash_embed_text(text: str) -> List[float]:
    """Deterministic, dependency-free pseudo-embedding.

    Design (intentionally simple, intentionally strong on exact-token
    match):
      * Tokenise on word boundaries, lowercase.
      * For each unique token, hash to a single vector bucket and
        add a positive weight = sub-linear TF.
      * L2-normalise.

    Why this works as a retrieval fallback: the bucket for
    'pay_s30006' is unique (with 384 dims and ~700 unique tokens in
    the corpus, collision is rare). A query that is just
    'pay_s30006' lights up that one bucket, and the document
    containing the same token has a relatively large component in
    that bucket vs. documents that don't. With L2-normalisation,
    the cosine then reflects "what fraction of the document's
    energy is in the matching bucket" — which strongly favours
    short documents whose content IS the matching token, and ranks
    documents that contain the exact token above ones that don't.
    """
    if not text:
        return [0.0] * FALLBACK_DIM
    tokens = re.findall(r"[A-Za-z0-9_]+", text.lower())
    if not tokens:
        return [0.0] * FALLBACK_DIM

    counts: Dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1

    vec = [0.0] * FALLBACK_DIM
    for tok, count in counts.items():
        # SHA-256 → first 4 bytes → bucket index (well-distributed)
        h = hashlib.sha256(tok.encode("utf-8", "ignore")).digest()[:4]
        idx = int.from_bytes(h, "big") % FALLBACK_DIM
        # Sub-linear TF + small extra so a token's first occurrence
        # counts but repeats don't dominate.
        vec[idx] += 1.0 + math.log(count)

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _embed_texts(texts: List[str]) -> List[List[float]]:
    embedder, _, _ = _get_embedder()
    if _embedder_kind == "st":
        # sentence-transformers returns numpy; convert to plain lists
        vecs = embedder.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return [v.tolist() for v in vecs]
    return [embedder(t) for t in texts]


def _embed_query(text: str):
    return _embed_texts([text])[0]


# ---------------------------------------------------------------------------
# CSV -> documents
# ---------------------------------------------------------------------------

def _row_to_document(source: str, row: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Turn one CSV row into (document_text, metadata).

    The document text is a human-readable concatenation of all fields
    (so semantic search sees amounts, dates, IDs together). Metadata
    is the raw row (stringified) so the LLM can quote exact values.
    """
    parts: List[str] = [f"source: {source}"]
    meta: Dict[str, Any] = {"source": source}

    for k, v in row.items():
        if v is None or (isinstance(v, float) and math.isnan(v)):
            sv = ""
        else:
            sv = str(v)
        parts.append(f"{k}: {sv}")
        meta[k] = sv

    return " | ".join(parts), meta


def _iter_csv(path: Path, source: str):
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield _row_to_document(source, row)


# ---------------------------------------------------------------------------
# ChromaDB helpers
# ---------------------------------------------------------------------------

# Cache the PersistentClient at module level so we never accidentally end
# up with two clients pointing at the same on-disk path (chromadb 1.x
# has cross-client cache issues that surface as
# "Collection <uuid> does not exist" on upsert).
_client = None


def _get_client():
    global _client
    if _client is None:
        import chromadb  # local import; only needed if RAG is used

        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


def _get_client_and_collection(reset: bool = False):
    """Return (client, collection). Creates/refreshes the collection.

    On reset we delete the existing collection and re-create it, and
    we also drop the cached client (chromadb 1.x keeps a stale
    collection-id cache on the PersistentClient after delete).
    """
    global _client

    if reset:
        # If we already have a client, try to delete the collection
        # through it; then drop the cached client so the next call
        # re-opens a fresh one (which knows the new collection id).
        if _client is not None:
            try:
                _client.delete_collection(COLLECTION_NAME)
            except Exception:  # noqa: BLE001
                pass
            try:
                _client.reset()
            except Exception:  # noqa: BLE001
                pass
            _client = None

    client = _get_client()

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "Reconciled finance rows from 4 source CSVs"},
    )
    return client, collection


def get_collection():
    """Public accessor (does not re-index; reads the on-disk store)."""
    return _get_client_and_collection(reset=False)[1]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def index_reconciled_data(reset: bool = True) -> Dict[str, Any]:
    """Index all 4 source CSVs into ChromaDB.

    Returns a stats dict: sources, count, embedder, collection_name.
    """
    sources = {
        "razorpay_settlement": DATA_DIR / "razorpay_settlement.csv",
        "bank_statement": DATA_DIR / "bank_statement.csv",
        "oms_orders": DATA_DIR / "oms_orders.csv",
        "gst_invoices": DATA_DIR / "gst_invoices.csv",
    }

    _, collection = _get_client_and_collection(reset=reset)

    ids: List[str] = []
    docs: List[str] = []
    metas: List[Dict[str, Any]] = []
    counter = 0
    per_source: Dict[str, int] = {}

    for name, path in sources.items():
        if not path.exists():
            logger.warning("Skipping missing source: %s", path)
            continue
        n = 0
        for doc_text, meta in _iter_csv(path, name):
            # Stable id: source + row-index, so re-indexing is idempotent
            ids.append(f"{name}::{counter}")
            docs.append(doc_text)
            metas.append(meta)
            counter += 1
            n += 1
        per_source[name] = n

    if not docs:
        raise RuntimeError(f"No rows found under {DATA_DIR}")

    # ChromaDB has a per-call batch limit; chunk conservatively.
    embeddings = _embed_texts(docs)
    BATCH = 256
    for start in range(0, len(docs), BATCH):
        end = start + BATCH
        collection.upsert(
            ids=ids[start:end],
            documents=docs[start:end],
            metadatas=metas[start:end],
            embeddings=embeddings[start:end],
        )

    _, _, kind = _get_embedder()
    stats = {
        "sources": per_source,
        "total": len(docs),
        "embedder": kind,
        "collection": collection.name,
        "path": str(CHROMA_DIR),
    }
    logger.info("Indexed %d rows into %s using %s", len(docs), collection.name, kind)
    return stats


def retrieve_context(query: str, k: int = 5) -> List[Dict[str, Any]]:
    """Return the top-k most similar documents for a query.

    Each result dict has: id, document, metadata, score (cosine
    similarity; higher = more similar, in [-1, 1]).
    """
    if not query or not query.strip():
        return []

    collection = get_collection()
    count = collection.count()
    if count == 0:
        logger.warning("retrieve_context: collection is empty; call index_reconciled_data() first")
        return []

    q_vec = _embed_query(query)
    # Clamp k to what's available
    k = max(1, min(int(k), count))

    res = collection.query(
        query_embeddings=[q_vec],
        n_results=k,
    )

    out: List[Dict[str, Any]] = []
    if not res or not res.get("ids"):
        return out
    ids = res["ids"][0]
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    # Chroma returns distances; for cosine space, similarity = 1 - distance.
    dists = (res.get("distances") or [[]])[0]

    for i, _id in enumerate(ids):
        dist = dists[i] if i < len(dists) else 0.0
        try:
            score = float(1.0 - float(dist))
        except (TypeError, ValueError):
            score = 0.0
        out.append(
            {
                "id": _id,
                "document": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
                "score": score,
            }
        )
    return out


def format_context_for_prompt(results: List[Dict[str, Any]]) -> str:
    """Render retrieved rows as a compact block for the LLM prompt."""
    if not results:
        return "(no relevant rows retrieved)"
    lines: List[str] = []
    for i, r in enumerate(results, 1):
        meta = r.get("metadata") or {}
        src = meta.get("source", "?")
        score = r.get("score", 0.0)
        lines.append(f"[{i}] (source={src}, score={score:.3f})")
        # Show the structured fields, not the raw pipe-joined blob
        for k, v in meta.items():
            if k == "source":
                continue
            lines.append(f"    {k}: {v}")
        lines.append("")
    return "\n".join(lines).rstrip()


def collection_stats() -> Dict[str, Any]:
    """Return lightweight stats for the current on-disk collection."""
    _, _, kind = _get_embedder()
    try:
        c = get_collection()
        return {"count": c.count(), "embedder": kind, "name": c.name}
    except Exception as e:  # noqa: BLE001
        return {"count": 0, "embedder": kind, "error": str(e)}


if __name__ == "__main__":
    # CLI: `python -m core.rag` reindexes and prints one retrieval
    import sys as _sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    stats = index_reconciled_data(reset=True)
    print(json.dumps(stats, indent=2))
    q = " ".join(_sys.argv[1:]) or "pay_S30006"
    print("\nQuery:", q)
    for r in retrieve_context(q, k=5):
        print(f"  {r['id']} (score={r['score']:.3f})")
