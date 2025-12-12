
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


def call_irrigation_agent_hf(
    payload: Dict[str, Any],
    rag_context_text: Optional[str] = None,
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

    api_url = "https://router.huggingface.co/v1/chat/completions"
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

    json_instructions = (
        "Muy importante:\n"
        "- Responde EXCLUSIVAMENTE con un ÚNICO objeto JSON válido.\n"
        "- No incluyas nada de texto antes ni después del JSON.\n"
        "- No uses bloques ```json ni ningún tipo de marcado de código.\n"
        "- No añadas comentarios dentro del JSON.\n"
        "- El campo \"explanation\" debe ser un texto corto (máximo ~700 caracteres), "
        "no una explicación muy larga.\n"
    )

    user_prompt = (
        "Usa el siguiente JSON con datos de la parcela para generar una "
        "recomendación de riego para las próximas 24 horas. "
        "Devuelve SOLO un JSON con 'recommendation' y 'explanation'.\n\n"
        "Ejemplo de estructura de respuesta (no copies los valores, solo la forma):\n"
        f"{json.dumps(RESPONSE_SCHEMA_HINT, ensure_ascii=False, indent=2)}\n\n"
        f"{json_instructions}\n"
        + rag_block
        + "JSON de entrada:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.strip()},
        {"role": "user", "content": user_prompt},
    ]

    body = {
        "model": HF_MODEL_ID,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 1200,
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
            "recommendation": None,
            "explanation": (
                "El modelo de Hugging Face no devolvió un JSON parseable. "
                f"Respuesta cruda (primeros 1000 caracteres): {text[:1000]}"
            ),
        }

    parsed.setdefault("recommendation", None)
    parsed.setdefault("explanation", "")

    return parsed
