"""Local multilingual language model (sentence embeddings), used for two things:

* nature of complaint: the complaint is compared with the plain descriptions of each category in
  settings.yaml (zero-shot; nothing is trained on the demo data);
* same matter: two complaints are compared with each other, across Hindi and English.

Model: paraphrase-multilingual-MiniLM-L12-v2 (50+ languages, 384-d), quantised ONNX run by fastembed
on the CPU. If the model files are missing the module falls back to character n-gram vectors so the
system still works (with weaker cross-language matching); `backend()` reports which one is active.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from functools import lru_cache

import numpy as np

from . import db, settings
from .config import EMBED_MODEL, MODELS

log = logging.getLogger("samanvay.ai")
_model = None
_backend = "loading"
_lock = threading.Lock()


def _load():
    global _model, _backend
    with _lock:
        if _model is not None or _backend == "fallback":
            return
        try:
            from fastembed import TextEmbedding
            _model = TextEmbedding(EMBED_MODEL, cache_dir=str(MODELS))
            _backend = "model"
        except Exception as e:  # offline and no local copy
            log.warning("language model unavailable (%s); using character n-grams", e)
            _backend = "fallback"


def backend() -> dict:
    _load()
    return {"backend": _backend, "model": EMBED_MODEL if _backend == "model" else "character n-grams"}


def _ngram_vec(text: str, dim: int = 2048) -> np.ndarray:
    v = np.zeros(dim, dtype=np.float32)
    t = f"  {text.lower()}  "
    for i in range(len(t) - 2):
        v[int(hashlib.md5(t[i:i + 3].encode()).hexdigest()[:8], 16) % dim] += 1
    return v


def embed(texts: list[str]) -> np.ndarray:
    _load()
    if _backend == "model":
        E = np.array(list(_model.embed(texts)), dtype=np.float32)
    else:
        E = np.array([_ngram_vec(t) for t in texts], dtype=np.float32)
    n = np.linalg.norm(E, axis=1, keepdims=True)
    n[n == 0] = 1
    return E / n


def case_text(c: dict) -> str:
    return f"{c.get('subject') or ''}. {c.get('description') or ''}".strip()


def case_vectors(cases: list[dict]) -> dict[str, np.ndarray]:
    """Vectors for cases, read from the cache or computed once and stored."""
    out, todo = {}, []
    have = {r["case_id"]: r for r in db.q(
        f"SELECT * FROM vectors WHERE case_id IN ({','.join('?' * len(cases))})", [c["id"] for c in cases])} if cases else {}
    for c in cases:
        t = case_text(c)
        sha = hashlib.sha1((_backend + t).encode()).hexdigest()
        r = have.get(c["id"])
        if r and r["sha"] == sha:
            out[c["id"]] = np.frombuffer(r["vec"], dtype=np.float32)
        else:
            todo.append((c["id"], sha, t))
    if todo:
        E = embed([t for _, _, t in todo])
        with db.tx() as cx:
            for (cid, sha, _), v in zip(todo, E):
                cx.execute("INSERT OR REPLACE INTO vectors (case_id, sha, vec) VALUES (?,?,?)", (cid, sha, v.tobytes()))
                out[cid] = v
    return out


@lru_cache(maxsize=4)
def _prototypes(key: str) -> tuple[list[str], np.ndarray]:
    cats = settings.get()["categories"]
    ids, vecs = [], []
    for cid, c in cats.items():
        lines = c.get("describe") or [c["label"]]
        E = embed(lines)
        ids.append(cid)
        vecs.append(E)
    return ids, vecs


def classify(text: str, top: int = 3, inst_text: str | None = None) -> list[dict]:
    """Nature of complaint, best first: [{'category', 'label', 'score'}]. Score is cosine similarity
    to the closest description line of the category. The institution's name is replaced by a neutral
    word first, so that names like 'Fee Waiver Polytechnic' do not sway the result."""
    cats = settings.get()["categories"]
    if inst_text and len(inst_text) > 3:
        text = text.replace(inst_text, "the college")
    key = hashlib.sha1(db.j({k: v.get("describe") for k, v in cats.items()}).encode()).hexdigest()
    ids, vecs = _prototypes(key + _backend)
    v = embed([text])[0]
    scores = [float(np.max(E @ v)) for E in vecs]
    order = np.argsort(scores)[::-1][:top]
    return [{"category": ids[i], "label": cats[ids[i]]["label"], "score": round(scores[i], 3)} for i in order]


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))
