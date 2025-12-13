# cloud_run/stress_agent/llm_client.py
import json
from typing import Any, Dict, Optional
from huggingface_hub import InferenceClient
from cloud_run.stress_agent.config import HF_TOKEN, HF_MODEL_ID
from cloud_run.stress_agent.prompts import SYSTEM_PROMPT, RESPONSE_SCHEMA_HINT

def _try_parse_json(raw: str) -> Optional[Dict[str, Any]]:
    # (Misma función de limpieza que en los otros agentes)
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

def call_stress_agent_hf(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not HF_TOKEN:
        return {"error": "Falta HF_TOKEN"}

    client = InferenceClient(model=HF_MODEL_ID, token=HF_TOKEN)

    # Inyectamos el resumen en el prompt de usuario para ayudar al modelo
    summary = payload.get("summary_metrics", {})
    user_content = (
        f"ANÁLISIS DE ESTRÉS PARA LAS PRÓXIMAS 48H.\n"
        f"CULTIVO: {json.dumps(payload.get('crop'), ensure_ascii=False)}\n"
        f"RESUMEN METEOROLÓGICO: VPD Máx: {summary.get('max_forecast_vpd')} kPa | UV Máx: {summary.get('max_forecast_uv')}\n"
        f"NOTAS AGRICULTOR: {payload.get('farmer_notes', '')}\n\n"
        f"PRONÓSTICO DETALLADO (JSON):\n{json.dumps(payload.get('forecast_48h'), ensure_ascii=False)}\n\n"
        f"Genera el JSON de respuesta siguiendo el esquema sugerido:\n{json.dumps(RESPONSE_SCHEMA_HINT)}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        response = client.chat_completion(messages=messages, max_tokens=1200, temperature=0.2, stream=False)
        text = response.choices[0].message.content
        parsed = _try_parse_json(text)
        return parsed or {"stress_alert": {}, "climate_management_advice": "Error parseando respuesta IA", "raw": text}
    except Exception as e:
        return {"error": str(e)}
