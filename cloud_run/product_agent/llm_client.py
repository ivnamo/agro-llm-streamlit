import json
from typing import Any, Dict, Optional
from huggingface_hub import InferenceClient
from cloud_run.product_agent.config import HF_TOKEN, HF_MODEL_ID
from cloud_run.product_agent.prompts import SYSTEM_PROMPT, RESPONSE_SCHEMA_HINT

def _try_parse_json(raw: str) -> Optional[Dict[str, Any]]:
    cleaned = raw.strip()
    if "```" in cleaned:
        cleaned = cleaned.split("```")[-1] if cleaned.startswith("```json") else cleaned.replace("```json", "").replace("```", "")
    try:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            return json.loads(cleaned[start : end + 1])
        return json.loads(cleaned)
    except:
        return None

def call_product_agent_hf(
    payload: Dict[str, Any],
    rag_context_text: Optional[str] = None,
) -> Dict[str, Any]:
    
    if not HF_TOKEN:
        return {"product_plan": [], "agronomic_advice": "Falta HF_TOKEN."}

    client = InferenceClient(model=HF_MODEL_ID, token=HF_TOKEN)

    catalog_block = payload.get("catalog_context", "")
    rag_block = f"VADEMÉCUM TÉCNICO (RAG):\n{rag_context_text}\n\n" if rag_context_text else ""
    
    # Extraemos inputs de otros agentes
    irrig_reco = payload.get('irrigation_recommendation', {}).get('recommendation', {})
    stress_alert = payload.get('stress_alert', {}).get('stress_alert', {}) # Ojo con la estructura anidada

    user_content = (
        "ACTÚA COMO UN INGENIERO AGRÓNOMO SENIOR.\n"
        "Tu objetivo es diseñar la ESTRATEGIA DE PRODUCTOS (Nutrición/Sanidad) integrando todos los datos.\n\n"
        
        f"{catalog_block}\n\n"
        f"{rag_block}"
        
        "--- SITUACIÓN INTEGRAL ---\n"
        f"1. CULTIVO: {payload.get('crop', {}).get('species')} ({payload.get('crop', {}).get('phenological_stage')}).\n"
        f"2. NOTAS DEL AGRICULTOR: '{payload.get('farmer_notes', '')}'\n"
        f"3. INPUT HIDRÁULICO (Riego): {json.dumps(irrig_reco, ensure_ascii=False)}\n"
        f"4. INPUT FISIOLÓGICO (Estrés/Clima): {json.dumps(stress_alert, ensure_ascii=False)}\n"
        "--------------------------\n\n"

        "🧠 RAZONAMIENTO OBLIGATORIO:\n"
        "Paso 1: Prioridad Sanitaria (Biótica). Cruza 'Notas Agricultor' con 'Input Fisiológico'.\n"
        "   - Ej: Si el Fisiólogo alerta de riesgo de Botrytis por humedad alta -> Recomienda Mimoten/Zytron.\n"
        "Paso 2: Estrés Abiótico.\n"
        "   - Ej: Si el Fisiólogo alerta de VPD alto/Calor -> Recomienda antiestresantes (Fitomare/Raykat).\n"
        "Paso 3: Nutrición Base.\n"
        "   - Ajusta según fase fenológica, PERO ten en cuenta el riego. Si el riego es reducido por lluvia, prioriza vía foliar.\n\n"

        "SALIDA JSON REQUERIDA:\n"
        f"{json.dumps(RESPONSE_SCHEMA_HINT)}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        response = client.chat_completion(messages=messages, max_tokens=1500, temperature=0.3, stream=False)
        text = response.choices[0].message.content
        parsed = _try_parse_json(text)
        return parsed or {"product_plan": [], "agronomic_advice": "Error JSON", "raw": text}

    except Exception as e:
        return {"product_plan": [], "agronomic_advice": f"Error API: {e}"}
