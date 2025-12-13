import json
import re
from typing import Any, Dict, Optional
from huggingface_hub import InferenceClient
from cloud_run.stress_agent.config import HF_TOKEN, HF_MODEL_ID
from cloud_run.stress_agent.prompts import SYSTEM_PROMPT, RESPONSE_SCHEMA_HINT

def _try_parse_json(raw: str) -> Optional[Dict[str, Any]]:
    """
    Intenta extraer y parsear un JSON de un string sucio (con Markdown, texto, etc.).
    Usa expresiones regulares para encontrar el bloque JSON { ... } más externo.
    """
    if not raw:
        return None
        
    # 1. Limpieza básica de caracteres invisibles molestos (non-breaking spaces)
    cleaned = raw.replace("\u00a0", " ").strip()
    
    # 2. Estrategia Regex: Buscar el primer '{' y el último '}' balanceados no es trivial con regex,
    # pero buscar el contenido entre el primer { y el último } suele bastar.
    # El flag DOTALL permite que el punto coincida con saltos de línea.
    match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
    
    if match:
        candidate = match.group(1)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # Si falla, a veces es por comillas simples o trailing commas.
            # Intentamos un "arreglo" desesperado (opcional) o simplemente pasamos.
            pass
            
    # 3. Estrategia Fallback manual (si el regex falla por alguna razón)
    try:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            candidate = cleaned[start : end + 1]
            return json.loads(candidate)
    except:
        pass

    return None

def call_stress_agent_hf(payload: Dict[str, Any]) -> Dict[str, Any]:
    
    if not HF_TOKEN:
        return {"error": "Falta HF_TOKEN en las variables de entorno."}

    client = InferenceClient(model=HF_MODEL_ID, token=HF_TOKEN)

    # Preparamos el resumen para el prompt
    summary = payload.get("summary_metrics", {})
    
    # Construimos el mensaje de usuario con los datos reales
    user_content = (
        f"ANÁLISIS DE ESTRÉS (FISIOLOGÍA) A 48H.\n"
        f"CULTIVO: {json.dumps(payload.get('crop', {}), ensure_ascii=False)}\n"
        f"RESUMEN METEOROLÓGICO: VPD Máx: {summary.get('max_forecast_vpd')} kPa | UV Máx: {summary.get('max_forecast_uv')}\n"
        f"NOTAS AGRICULTOR: {payload.get('farmer_notes', '')}\n\n"
        f"PRONÓSTICO DETALLADO (JSON):\n{json.dumps(payload.get('forecast_48h', []), ensure_ascii=False)}\n\n"
        "Genera la respuesta JSON siguiendo estrictamente este esquema:\n"
        f"{json.dumps(RESPONSE_SCHEMA_HINT, ensure_ascii=False)}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        # Temperature baja (0.2) para que sea riguroso con el JSON
        response = client.chat_completion(
            messages=messages, 
            max_tokens=1500, 
            temperature=0.2, 
            stream=False
        )
        
        text = response.choices[0].message.content
        
        # Parseamos
        parsed = _try_parse_json(text)
        
        if not parsed:
            # Si falla el parseo, devolvemos una estructura de error pero con el texto crudo
            # para poder depurar (como acabas de hacer, ¡bien hecho!)
            return {
                "stress_alert": {
                    "risk_level": "ERROR_FORMATO",
                    "detailed_reason": "El modelo generó una respuesta pero no es un JSON válido."
                },
                "recommendations": {},
                "raw": text
            }
            
        return parsed

    except Exception as e:
        print(f"[STRESS AGENT ERROR] {e}")
        return {"error": str(e)}
