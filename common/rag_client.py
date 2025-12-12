import json
import os
from typing import Any, Dict, List, Optional

import faiss
import numpy as np
import requests
from google.cloud import storage

# Config RAG compartida (puede ser común a varios agentes)
RAG_BUCKET = os.getenv("RAG_BUCKET", "tfg-agro-data")
RAG_PREFIX = os.getenv("RAG_PREFIX", "rag/manuales")
RAG_INDEX_BLOB = os.getenv("RAG_INDEX_BLOB", "index.faiss")
RAG_META_BLOB = os.getenv("RAG_META_BLOB", "chunk_meta.json")
RAG_K = int(os.getenv("RAG_K", "5"))

# Hugging Face embeddings
HF_TOKEN = os.getenv("HF_TOKEN")
HF_EMBED_MODEL_ID = os.getenv(
    "HF_EMBED_MODEL_ID",
    "sentence-transformers/all-MiniLM-L6-v2",
)

# Globals RAG (lazy load)
_rag_index: Optional[faiss.Index] = None
_rag_chunks: Optional[List[Dict[str, Any]]] = None


def _load_rag_resources() -> None:
    """
    Carga index.faiss y chunk_meta.json desde GCS en globals.
    Se llama lazy la primera vez que se hace una búsqueda.
    """
    global _rag_index, _rag_chunks

    if _rag_index is not None and _rag_chunks is not None:
        return

    client = storage.Client()
    bucket = client.bucket(RAG_BUCKET)

    index_path = "/tmp/index.faiss"
    meta_path = "/tmp/chunk_meta.json"

    bucket.blob(f"{RAG_PREFIX}/{RAG_INDEX_BLOB}").download_to_filename(index_path)
    bucket.blob(f"{RAG_PREFIX}/{RAG_META_BLOB}").download_to_filename(meta_path)

    _rag_index = faiss.read_index(index_path)

    with open(meta_path, "r", encoding="utf-8") as f:
        _rag_chunks = json.load(f)


def _hf_embed(text: str) -> np.ndarray:
    """
    Obtiene el embedding de un texto usando la API NATIVA de Hugging Face.
    Es más estable que el endpoint /v1/embeddings para cuentas gratuitas.
    """
    if not HF_TOKEN:
        raise RuntimeError("HF_TOKEN no está configurado; no se pueden obtener embeddings.")

    # Usamos el endpoint directo del modelo
    api_url = f"https://api-inference.huggingface.co/models/{HF_EMBED_MODEL_ID}"
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json",
    }

    # La API nativa prefiere recibir una lista para evitar ambigüedades
    body = {"inputs": [text]}

    resp = requests.post(api_url, headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    # Verificación de errores que a veces vienen como JSON 200 OK
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"Error HF API: {data['error']}")

    # La respuesta para inputs=[text] es una lista de listas: [[0.1, 0.2, ...]]
    # Tomamos el primer elemento
    if isinstance(data, list) and len(data) > 0:
        emb = data[0]
        # Aseguramos que sea una lista de floats (a veces la API anida diferente)
        if isinstance(emb, list):
            return np.array(emb, dtype="float32")
            
    # Fallback por si la estructura cambia
    print(f"[DEBUG] Estructura inesperada de embeddings: {type(data)}")
    # Intentamos convertir lo que llegue
    return np.array(data, dtype="float32")


def rag_retrieve(query: str, k: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Devuelve los top-k chunks para una query.
    Cada resultado incluye doc_id, chunk_id, text y score.
    """
    _load_rag_resources()

    assert _rag_index is not None
    assert _rag_chunks is not None

    k = k or RAG_K

    q_emb = _hf_embed(query)  # shape (dim,)
    q_emb = q_emb.reshape(1, -1)  # FAISS espera [1, dim]

    D, I = _rag_index.search(q_emb, k)

    results: List[Dict[str, Any]] = []
    for rank, idx in enumerate(I[0]):
        meta = _rag_chunks[idx]
        results.append(
            {
                "rank": rank,
                "score": float(D[0][rank]),
                "doc_id": meta["doc_id"],
                "chunk_id": meta["chunk_id"],
                "text": meta["text"],
            }
        )
    return results


def build_rag_context_text(chunks: List[Dict[str, Any]]) -> str:
    """
    Convierte los chunks recuperados en un bloque de texto para meter directamente en el prompt.
    """
    parts: List[str] = []
    for c in chunks:
        header = f"[DOC: {c['doc_id']} | CHUNK: {c['chunk_id']} | score={c['score']:.3f}]"
        parts.append(header + "\n" + c["text"])
    return "\n\n---\n\n".join(parts)
