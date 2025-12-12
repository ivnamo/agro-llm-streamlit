import json
import os
from typing import Any, Dict, List, Optional

import faiss
import numpy as np
from google.cloud import storage
from huggingface_hub import InferenceClient  # <--- IMPORTANTE

# Config RAG
RAG_BUCKET = os.getenv("RAG_BUCKET", "tfg-agro-data")
RAG_PREFIX = os.getenv("RAG_PREFIX", "rag/manuales")
RAG_INDEX_BLOB = os.getenv("RAG_INDEX_BLOB", "index.faiss")
RAG_META_BLOB = os.getenv("RAG_META_BLOB", "chunk_meta.json")
RAG_K = int(os.getenv("RAG_K", "5"))

# Hugging Face config
HF_TOKEN = os.getenv("HF_TOKEN")
# Modelo por defecto (aunque se sobreescribirá en el Dockerfile)
HF_EMBED_MODEL_ID = os.getenv(
    "HF_EMBED_MODEL_ID",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)

# Globals
_rag_index: Optional[faiss.Index] = None
_rag_chunks: Optional[List[Dict[str, Any]]] = None


def _load_rag_resources() -> None:
    global _rag_index, _rag_chunks
    if _rag_index is not None and _rag_chunks is not None:
        return

    client = storage.Client()
    bucket = client.bucket(RAG_BUCKET)

    # Descargamos a /tmp para evitar problemas de permisos
    index_path = "/tmp/index.faiss"
    meta_path = "/tmp/chunk_meta.json"

    bucket.blob(f"{RAG_PREFIX}/{RAG_INDEX_BLOB}").download_to_filename(index_path)
    bucket.blob(f"{RAG_PREFIX}/{RAG_META_BLOB}").download_to_filename(meta_path)

    _rag_index = faiss.read_index(index_path)
    with open(meta_path, "r", encoding="utf-8") as f:
        _rag_chunks = json.load(f)


def _hf_embed(text: str) -> np.ndarray:
    """
    Obtiene el embedding usando la librería oficial InferenceClient.
    Gestiona automáticamente el enrutamiento y reintentos.
    """
    if not HF_TOKEN:
        raise RuntimeError("HF_TOKEN no está configurado.")

    # Inicializamos cliente oficial
    client = InferenceClient(model=HF_EMBED_MODEL_ID, token=HF_TOKEN)

    try:
        # feature_extraction devuelve el embedding directamente
        response = client.feature_extraction(text)
        
        # Convertimos a numpy array float32
        emb = np.array(response, dtype="float32")
        
        # Si la respuesta tiene dimensión de batch (1, 384), la aplanamos a (384,)
        if emb.ndim > 1:
            emb = emb.flatten()
            
        return emb

    except Exception as e:
        raise RuntimeError(f"Error HF InferenceClient: {e}")


def rag_retrieve(query: str, k: Optional[int] = None) -> List[Dict[str, Any]]:
    _load_rag_resources()
    
    # Check de seguridad
    if _rag_index is None or _rag_chunks is None:
        return []

    k = k or RAG_K

    q_emb = _hf_embed(query)  # shape (384,)
    q_emb = q_emb.reshape(1, -1)  # FAISS espera (1, 384)

    D, I = _rag_index.search(q_emb, k)

    results: List[Dict[str, Any]] = []
    for rank, idx in enumerate(I[0]):
        if idx == -1: continue # Por si FAISS devuelve padding
        meta = _rag_chunks[idx]
        results.append(
            {
                "rank": rank,
                "score": float(D[0][rank]),
                "doc_id": meta.get("doc_id", "unknown"),
                "chunk_id": meta.get("chunk_id", "unknown"),
                "text": meta.get("text", ""),
            }
        )
    return results


def build_rag_context_text(chunks: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for c in chunks:
        header = f"[DOC: {c['doc_id']} | CHUNK: {c['chunk_id']} | score={c['score']:.3f}]"
        parts.append(header + "\n" + c["text"])
    return "\n\n---\n\n".join(parts)
