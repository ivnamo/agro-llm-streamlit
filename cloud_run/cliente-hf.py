import os
import json
from typing import Any, Dict, List

import requests
from google.cloud import bigquery, storage

import faiss
import numpy as np

# =========================
# CONFIG
# =========================

PROJECT_ID = os.getenv("PROJECT_ID", "tfg-agro-llm")
BQ_DATASET = os.getenv("BQ_DATASET", "agro_data")
LOCATION_ID = int(os.getenv("LOCATION_ID", "8507"))
LOCATION_NAME = os.getenv("LOCATION_NAME", "S4 - Invernadero")

# Hugging Face (nueva API router)
HF_TOKEN = os.getenv("HF_TOKEN")
HF_MODEL_ID = os.getenv("HF_MODEL_ID", "deepseek-ai/DeepSeek-V3.2")

# Modelo de embeddings en Hugging Face (debe ser el mismo usado para crear index.faiss)
HF_EMBED_MODEL_ID = os.getenv("HF_EMBED_MODEL_ID", "sentence-transformers/all-MiniLM-L6-v2")

# Cliente BigQuery global
bq_client = bigquery.Client(project=PROJECT_ID)

# =========================
# CONFIG RAG
# =========================

RAG_BUCKET = os.getenv("RAG_BUCKET", "tfg-agro-data")
RAG_PREFIX = os.getenv("RAG_PREFIX", "rag/manuales")
RAG_INDEX_BLOB = os.getenv("RAG_INDEX_BLOB", "index.faiss")
RAG_META_BLOB = os.getenv("RAG_META_BLOB", "chunk_meta.json")
RAG_K = int(os.getenv("RAG_K", "5"))

# Globals RAG (lazy load)
_rag_index: faiss.Index | None = None
_rag_chunks: List[Dict[str, Any]] | None = None


# =========================
# PROMPT DE SISTEMA
# =========================

SYSTEM_PROMPT = """
Eres un asesor agronómico virtual especializado en cultivos en invernadero con riego localizado.

Recibes como entrada un objeto JSON con:
- Información de la parcela (location_id, location_name).
- Información del cultivo (especie, variedad, estado fenológico).
- Información del suelo (textura, capacidad de campo, punto de marchitez, rangos objetivo de humedad VWC y salinidad).
- Información del sistema de riego (tipo de riego, caudal por gotero, densidad de plantas).
- Comentarios opcionales del agricultor (farmer_notes) sobre problemas observados, riego aplicado, etc.
- Un histórico de features diarias de los últimos días (daily_features_last_days).
- Una serie temporal reciente de las últimas horas (recent_timeseries_last_hours).

Tu objetivo es:
1. Evaluar el estado hídrico actual del cultivo y del suelo.
2. Detectar riesgo de estrés hídrico, percolación excesiva o problemas de salinidad.
3. Proponer una recomendación de riego para las próximas 24 horas, en litros/m² y, si es posible, minutos de riego por ciclo.
4. Indicar claramente si recomiendas aumentar, mantener o reducir el riego respecto a lo que parece que se venía aplicando.

Instrucciones importantes:
- Si los datos son insuficientes o inconsistentes, indícalo claramente y sé conservador.
- No inventes números sin justificar; indica cuándo estás suponiendo algo.
- Ten en cuenta que VWC es aproximación al % de volumen de agua en suelo.
- Considera la salinidad: si Sal2 se acerca o supera el máximo, evita riegos muy cortos y frecuentes sin lavado, y considera proponer riegos de lavado si procede.

Cuando recibas CONTEXTO DOCUMENTAL adicional (manuales de riego, guías técnicas, etc.),
debes apoyarte en ese contexto siempre que sea posible. No lo copies literalmente, pero
utilízalo como referencia técnica.

Devuelve SIEMPRE un JSON con exactamente estos dos campos en la raíz:
- "recommendation": objeto con la propuesta estructurada.
- "explanation": texto corto explicando el razonamiento.

Muy importante: al final del texto de "explanation", añade SIEMPRE un párrafo breve titulado
"Recomendación Atlántica Agrícola" en el que sugieras uno o varios productos de Atlántica Agrícola
coherentes con el estado hídrico y nutricional descrito (por ejemplo, manejo de salinidad, estrés
hídrico, mejora de desarrollo radicular, etc.). No añadas nuevos campos al JSON; todo debe ir
incluido dentro de la cadena de texto "explanation".
"""

RESPONSE_SCHEMA_HINT = {
    "recommendation": {
        "apply_irrigation": True,
        "reason": "increase|maintain|decrease",
        "suggested_water_l_m2": 6.5,
        "suggested_cycles": [
            {
                "start_time_local": "2025-12-04T07:00:00",
                "duration_minutes": 20,
                "comment": "Riego principal de la mañana"
            }
        ],
        "constraints": {
            "target_vwc10_range": [25.0, 35.0],
            "target_vwc_profile_range": [22.0, 35.0],
            "max_salinity_uScm": 2500
        },
        "warnings": [],
        "data_quality_flags": []
    },
    "explanation": "..."
}


# =========================
# HELPERS LLM
# =========================

def _try_parse_json(raw: str) -> Dict[str, Any] | None:
    """
    Intenta extraer un JSON de un texto potencialmente rodeado de fences ```json ... ```
    o con texto antes/después.
    """
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```", 2)
        if len(parts) >= 2:
            cleaned = parts[1]
        else:
            cleaned = raw

    cleaned = str(cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    candidate = cleaned[start: end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def call_hf_irrigation_advisor(
    payload: Dict[str, Any],
    rag_context_text: str | None = None,
) -> Dict[str, Any]:
    """
    Llama al modelo de Hugging Face vía API unificada /v1/chat/completions
    y devuelve recommendation + explanation (parseado).
    Puede recibir opcionalmente un bloque de contexto RAG en texto plano.
    """
    if not HF_TOKEN:
        return {
            "recommendation": None,
            "explanation": "HF_TOKEN no está configurado en el entorno de ejecución.",
        }

    API_URL = "https://router.huggingface.co/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json",
    }

    rag_block = ""
    if rag_context_text:
        rag_block = (
            "Además dispones del siguiente CONTEXTO DOCUMENTAL procedente de manuales de riego "
            "y guías técnicas (no lo reproduzcas literalmente, pero úsalo como referencia técnica):\n\n"
            f"{rag_context_text}\n\n"
            "Fin del contexto documental.\n\n"
        )

    # Instrucciones adicionales para forzar JSON limpio y corto
    json_instructions = (
        "Muy importante:\n"
        "- Responde EXCLUSIVAMENTE con un ÚNICO objeto JSON válido.\n"
        "- No incluyas nada de texto antes ni después del JSON.\n"
        "- No uses bloques ```json ni ningún tipo de marcado de código.\n"
        "- No añadas comentarios dentro del JSON.\n"
        "- El campo \"explanation\" debe ser un texto corto (máximo ~700 caracteres), "
        "no una explicación muy larga.\n"
    )

    # ---- Construcción del mensaje de usuario ----
    user_prompt = (
        "Usa el siguiente JSON con datos de la parcela para generar una "
        "recomendación de riego para las próximas 24 horas. "
        "Devuelve SOLO un JSON con 'recommendation' y 'explanation'.\n\n"
        "Ejemplo de estructura de respuesta (no copies los valores, solo la forma):\n"
        f"{json.dumps(RESPONSE_SCHEMA_HINT, ensure_ascii=False, indent=2)}\n\n"
        f"{json_instructions}\n"
        + rag_block +
        "JSON de entrada:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.strip()},
        {"role": "user", "content": user_prompt},
    ]

    body = {
        "model": HF_MODEL_ID,   # por ejemplo: deepseek-ai/DeepSeek-V3.2
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 1200,  # un poco más de margen para que no corte el JSON
        # "response_format": {"type": "json_object"},  # si el router lo soporta en el futuro
    }

    # ---- Llamada HTTP ----
    resp = requests.post(API_URL, headers=headers, json=body, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    # ---- Recuperar el texto generado ----
    text = data["choices"][0]["message"]["content"]

    # ---- Parsing robusto del JSON devuelto ----
    parsed = _try_parse_json(text)
    if parsed is None:
        # Ampliamos el trozo para debugging
        return {
            "recommendation": None,
            "explanation": (
                "El modelo de Hugging Face no devolvió un JSON parseable. "
                f"Respuesta cruda (primeros 1000 caracteres): {text[:1000]}"
            ),
        }

    # Normalizar campos mínimos
    parsed.setdefault("recommendation", None)
    parsed.setdefault("explanation", "")

    return parsed


# =========================
# HELPERS RAG
# =========================

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
    Obtiene el embedding de un texto usando la API unificada de Hugging Face.
    Usa el mismo HF_TOKEN que el modelo de chat, pero con el endpoint /v1/embeddings.
    """
    if not HF_TOKEN:
        raise RuntimeError("HF_TOKEN no está configurado; no se pueden obtener embeddings.")

    API_URL = "https://router.huggingface.co/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json",
    }

    body = {
        "model": HF_EMBED_MODEL_ID,
        "input": text,
    }

    resp = requests.post(API_URL, headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    emb = data["data"][0]["embedding"]
    return np.array(emb, dtype="float32")


def _rag_retrieve(query: str, k: int = RAG_K) -> List[Dict[str, Any]]:
    """
    Devuelve los top-k chunks para una query.
    Cada resultado incluye doc_id, chunk_id, text y score.
    """
    _load_rag_resources()

    assert _rag_index is not None
    assert _rag_chunks is not None

    # Embedding de la query vía API de Hugging Face
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


def _build_rag_context_text(chunks: List[Dict[str, Any]]) -> str:
    """
    Convierte los chunks recuperados en un bloque de texto para meter directamente en el prompt.
    (Opción A: todo como texto).
    """
    parts: List[str] = []
    for c in chunks:
        header = f"[DOC: {c['doc_id']} | CHUNK: {c['chunk_id']} | score={c['score']:.3f}]"
        parts.append(header + "\n" + c["text"])
    return "\n\n---\n\n".join(parts)


def build_rag_query_from_payload(payload: Dict[str, Any]) -> str:
    """
    Construye una pregunta RAG dinámica a partir del contexto de cultivo/suelo.
    """
    crop = payload.get("crop", {}) or {}
    soil = payload.get("soil", {}) or {}

    species = crop.get("species", "cultivo en invernadero")
    phen_stage = crop.get("phenological_stage", "")
    texture = soil.get("texture", "suelo agrícola")

    surf_range = soil.get("target_vwc_surface_range", [])
    prof_range = soil.get("target_vwc_profile_range", [])
    sal_max = soil.get("max_acceptable_salinity_uScm", None)

    def fmt_range(r):
        if isinstance(r, (list, tuple)) and len(r) == 2:
            return f"{r[0]}–{r[1]} % VWC"
        return "rango objetivo de humedad"

    surf_txt = fmt_range(surf_range)
    prof_txt = fmt_range(prof_range)
    sal_txt = f"{sal_max} µS/cm" if sal_max is not None else "el nivel máximo de salinidad aceptable"

    query = (
        f"Recomendaciones agronómicas de riego y manejo de humedad del suelo y salinidad para {species} "
        f"en invernadero con riego localizado sobre suelo de textura {texture}, "
        f"en fase fenológica '{phen_stage}'. "
        f"Incluye criterios para ajustar el riego diario según la humedad del suelo "
        f"(superficie: {surf_txt}, perfil: {prof_txt}) y para prevenir o corregir problemas de salinidad "
        f"(considerando {sal_txt}). "
        f"Da prioridad a recomendaciones aplicables en agricultura intensiva bajo plástico."
    )

    return query


# =========================
# QUERIES BIGQUERY
# =========================

def query_daily_features_last_days(days: int = 7) -> List[Dict[str, Any]]:
    query = f"""
    SELECT *
    FROM `{PROJECT_ID}.{BQ_DATASET}.cesens_s4_daily_features`
    WHERE fecha >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
    ORDER BY fecha
    """
    rows = bq_client.query(query).result()
    results: List[Dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        if "fecha" in d and hasattr(d["fecha"], "isoformat"):
            d["fecha"] = d["fecha"].isoformat()
        results.append(d)
    return results


def query_recent_timeseries(hours_back: int = 24) -> Dict[str, List[Dict[str, Any]]]:
    query = f"""
    SELECT
      ts_utc,
      RF,
      T_in,
      H_in,
      VWC10cm,
      VWC20cm,
      VWC40cm,
      VWC60cm,
      VWC2,
      TS10cm,
      TS20cm,
      TS40cm,
      TS60cm,
      TS2,
      Sal2
    FROM `{PROJECT_ID}.{BQ_DATASET}.cesens_s4_wide`
    WHERE ts_utc >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours_back} HOUR)
    ORDER BY ts_utc
    """
    rows = list(bq_client.query(query).result())

    metrics: Dict[str, List[Dict[str, float]]] = {
        "RF": [],
        "T_in": [],
        "H_in": [],
        "VWC10cm": [],
        "VWC20cm": [],
        "VWC40cm": [],
        "VWC60cm": [],
        "VWC2": [],
        "TS10cm": [],
        "TS20cm": [],
        "TS40cm": [],
        "TS60cm": [],
        "TS2": [],
        "Sal2": [],
    }

    for row in rows:
        ts_iso = row["ts_utc"].isoformat()
        for m in metrics.keys():
            value = row.get(m)
            if value is not None:
                metrics[m].append({"ts_utc": ts_iso, "value": float(value)})

    return {"hours_back": hours_back, "metrics": metrics}


# =========================
# CONTEXTO ESTÁTICO + OVERRIDES
# =========================

def build_static_context(overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Datos estáticos de cultivo/suelo/sistema de riego para el MVP,
    con posibilidad de sobreescribir campos desde la web (overrides).
    """
    base = {
        "crop": {
            "species": "tomate",
            "variety": "indeterminado",
            "phenological_stage": "cuajado_y_engorde",
            "planting_date": "2025-09-15",
        },
        "soil": {
            "texture": "franco-arenoso",
            "field_capacity_vwc": 35.0,
            "permanent_wilting_point_vwc": 15.0,
            "target_vwc_surface_range": [25.0, 35.0],
            "target_vwc_profile_range": [22.0, 35.0],
            "max_acceptable_salinity_uScm": 2500.0,
        },
        "irrigation_system": {
            "type": "riego_por_goteo",
            "emitters_per_plant": 2,
            "flow_lph_per_emitter": 1.6,
            "plants_per_m2": 2.5,
        },
    }

    overrides = overrides or {}

    def merge_dict(key: str):
        if key in overrides and isinstance(overrides[key], dict):
            for k, v in overrides[key].items():
                if v not in (None, "", []):
                    base[key][k] = v

    for section in ["crop", "soil", "irrigation_system"]:
        merge_dict(section)

    return base


# =========================
# ENTRYPOINT HTTP (Cloud Run / Function)
# =========================

def recomendar_riego_s4_hf(request):
    """
    Endpoint HTTP para Hugging Face:
    - Método: POST.
    - Opcionalmente puede recibir un JSON con 'context_overrides' y 'farmer_notes'.
    """
    try:
        # CORS básico
        if request.method == "OPTIONS":
            headers = {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            }
            return ("", 204, headers)

        try:
            body = request.get_json(silent=True) or {}
        except Exception:
            body = {}

        context_overrides = body.get("context_overrides") or {}
        farmer_notes = body.get("farmer_notes") or ""

        daily_features = query_daily_features_last_days(days=7)
        recent_ts = query_recent_timeseries(hours_back=24)
        static_ctx = build_static_context(context_overrides)

        payload: Dict[str, Any] = {
            "location_id": LOCATION_ID,
            "location_name": LOCATION_NAME,
            **static_ctx,
            "farmer_notes": farmer_notes,
            "daily_features_last_days": daily_features,
            "recent_timeseries_last_hours": recent_ts,
        }

        # ---- RAG: construir query dinámica y recuperar k=RAG_K chunks ----
        rag_context_text = ""
        try:
            rag_query = build_rag_query_from_payload(payload)
            rag_results = _rag_retrieve(rag_query, k=RAG_K)
            if rag_results:
                rag_context_text = _build_rag_context_text(rag_results)
        except Exception as e:
            # si falla el RAG, seguimos sin contexto documental
            payload["rag_warning"] = f"RAG no disponible: {str(e)}"

        # ---- Llamar al asesor LLM con contexto RAG (si lo hay) ----
        result = call_hf_irrigation_advisor(payload, rag_context_text=rag_context_text)

        headers = {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        }
        return (json.dumps(result, ensure_ascii=False), 200, headers)

    except Exception as e:
        headers = {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        }
        error_body = {"error": str(e)}
        return (json.dumps(error_body, ensure_ascii=False), 500, headers)
