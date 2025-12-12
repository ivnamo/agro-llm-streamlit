import json
import requests
from typing import Any, Dict, Optional

from cloud_run.product_agent.config import HF_TOKEN, HF_MODEL_ID
from cloud_run.product_agent.prompts import SYSTEM_PROMPT, RESPONSE_SCHEMA_HINT


def _try_parse_json(raw: str) -> Optional[Dict[str, Any]]:
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

    candidate = cleaned[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def call_product_agent_hf(
    payload: Dict[str, Any],
    rag_context_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Llama al modelo de Hugging Face para generar el Plan de Productos.
    Inyecta el Catálogo Maestro y el RAG de productos en el prompt.
    """
    if not HF_TOKEN:
        return {
            "product_plan": [],
            "agronomic_advice": "HF_TOKEN no está configurado en el entorno de ejecución.",
        }

    api_url = "https://router.huggingface.co/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json",
    }

    # 1. Recuperamos el Catálogo Maestro (El Guardarraíl)
    catalog_block = payload.get("catalog_context", "")

    # 2. Preparamos el bloque RAG (Fichas técnicas)
    rag_block = ""
    if rag_context_text:
        rag_block = (
            "Además dispones del siguiente CONTEXTO DOCUMENTAL procedente de Fichas Técnicas "
            "y Vademécum de Atlántica Agrícola (úsalo para verificar dosis y composición):\n\n"
            f"{rag_context_text}\n\n"
            "Fin del contexto documental.\n\n"
        )

    json_instructions = (
        "Muy importante:\n"
        "- Responde EXCLUSIVAMENTE con un ÚNICO objeto JSON válido.\n"
        "- El JSON debe contener las claves 'product_plan' (lista) y 'agronomic_advice' (texto).\n"
        "- No incluyas nada de texto antes ni después del JSON.\n"
        "- No uses bloques ```json ni marcado de código.\n"
    )

    # 3. Construimos el prompt final
    # IMPORTANTE: El catálogo va primero para fijar las restricciones.
    user_prompt = (
        f"{catalog_block}\n\n"
        "Usa el catálogo anterior (obligatorio), el contexto RAG y la siguiente situación agronómica "
        "(que incluye la recomendación de riego previa) para generar un Plan de Manejo de Productos.\n"
        "Devuelve SOLO un JSON con 'product_plan' y 'agronomic_advice'.\n\n"
        "Ejemplo de estructura de respuesta:\n"
        f"{json.dumps(RESPONSE_SCHEMA_HINT, ensure_ascii=False, indent=2)}\n\n"
        f"{json_instructions}\n"
        + rag_block
        + "JSON de entrada (Situación):\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.strip()},
        {"role": "user", "content": user_prompt},
    ]

    body = {
        "model": HF_MODEL_ID,
        "messages": messages,
        "temperature": 0.3, # Baja temperatura para respetar el catálogo
        "max_tokens": 1500,
    }

    resp = requests.post(api_url, headers=headers, json=body, timeout=120)
    
    if not resp.ok:
        print("[HF ERROR]", resp.status_code, resp.text[:500])
        resp.raise_for_status()
    
    data = resp.json()
    text = data["choices"][0]["message"]["content"]

    parsed = _try_parse_json(text)
    
    if parsed is None:
        return {
            "product_plan": [],
            "agronomic_advice": (
                "El modelo no devolvió un JSON válido. "
                f"Respuesta cruda: {text[:500]}..."
            ),
        }

    # Aseguramos que las claves existan para evitar errores en el frontend
    parsed.setdefault("product_plan", [])
    parsed.setdefault("agronomic_advice", "Sin consejo agronómico generado.")

    return parsed
