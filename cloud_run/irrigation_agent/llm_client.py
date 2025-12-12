import json
from typing import Any, Dict, Optional
from huggingface_hub import InferenceClient  # <--- Usamos la librería oficial
from cloud_run.irrigation_agent.config import HF_TOKEN, HF_MODEL_ID
from cloud_run.irrigation_agent.prompts import SYSTEM_PROMPT, RESPONSE_SCHEMA_HINT

def _try_parse_json(raw: str) -> Optional[Dict[str, Any]]:
    cleaned = raw.strip()
    # Eliminar bloques markdown ```json ... ``` si existen
    if "```" in cleaned:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            cleaned = cleaned[start : end + 1]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None

def call_irrigation_agent_hf(
    payload: Dict[str, Any],
    rag_context_text: Optional[str] = None,
) -> Dict[str, Any]:
    
    if not HF_TOKEN:
        return {"recommendation": None, "explanation": "Falta HF_TOKEN."}

    # Inicializamos el cliente oficial (Gestiona la API gratuita automáticamente)
    client = InferenceClient(model=HF_MODEL_ID, token=HF_TOKEN)

    # Construcción del Prompt
    rag_block = ""
    if rag_context_text:
        rag_block = (
            "CONTEXTO TÉCNICO ADICIONAL (RAG):\n"
            f"{rag_context_text}\n"
            "FIN CONTEXTO.\n\n"
        )

    json_instructions = (
        "Responde SOLO con un JSON válido. Estructura esperada:\n"
        f"{json.dumps(RESPONSE_SCHEMA_HINT, ensure_ascii=False)}\n"
    )

    user_content = (
        f"{rag_block}"
        f"{json_instructions}\n"
        "DATOS DE LA PARCELA:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        # Llamada oficial a Chat Completion
        response = client.chat_completion(
            messages=messages,
            max_tokens=1500,
            temperature=0.2, # Baja temperatura para que el JSON sea preciso
            stream=False
        )
        
        # Extraer texto
        text = response.choices[0].message.content

        # Parsear JSON
        parsed = _try_parse_json(text)
        if not parsed:
            return {
                "recommendation": None,
                "explanation": f"Error parseando JSON del modelo. Respuesta cruda: {text[:200]}..."
            }
            
        return parsed

    except Exception as e:
        print(f"[HF API ERROR] {e}")
        # Si da error, devolvemos un mensaje que no rompa el frontend
        return {
            "recommendation": None,
            "explanation": f"Error conectando con el modelo IA ({HF_MODEL_ID}): {str(e)}"
        }
