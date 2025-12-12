import json
from typing import Any, Dict, Optional
from huggingface_hub import InferenceClient
from cloud_run.product_agent.config import HF_TOKEN, HF_MODEL_ID
from cloud_run.product_agent.prompts import SYSTEM_PROMPT, RESPONSE_SCHEMA_HINT

def _try_parse_json(raw: str) -> Optional[Dict[str, Any]]:
    """Limpia y parsea JSON, resistente a bloques markdown."""
    cleaned = raw.strip()
    if "```" in cleaned:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            cleaned = cleaned[start : end + 1]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None

def call_product_agent_hf(
    payload: Dict[str, Any],
    rag_context_text: Optional[str] = None,
) -> Dict[str, Any]:
    
    if not HF_TOKEN:
        return {"product_plan": [], "agronomic_advice": "Falta HF_TOKEN."}

    client = InferenceClient(model=HF_MODEL_ID, token=HF_TOKEN)

    # 1. Preparar Contextos
    catalog_block = payload.get("catalog_context", "")
    rag_block = ""
    if rag_context_text:
        rag_block = f"VADEMÉCUM TÉCNICO (Referencia):\n{rag_context_text}\n\n"

    # 2. Extraer datos clave para inyectarlos explícitamente en el prompt
    # Esto ayuda a que el modelo no los pase por alto
    soil_data = payload.get("soil", {})
    crop_data = payload.get("crop", {})
    daily_feats = payload.get("daily_features_last_days", [])
    
    # Resumen rápido de sensores (último dato disponible)
    last_salinity = "Desconocida"
    last_temp_max = "Desconocida"
    if daily_feats:
        last_day = daily_feats[-1]
        last_salinity = last_day.get("Sal2_max", "N/D")
        last_temp_max = last_day.get("T_in_max", "N/D")

    # 3. CONSTRUCCIÓN DEL PROMPT (Razonamiento Multidimensional)
    user_content = (
        "ACTÚA COMO UN INGENIERO AGRÓNOMO SENIOR ESPECIALISTA EN NUTRICIÓN Y FISIOLOGÍA VEGETAL.\n"
        "Tu objetivo NO es calcular el riego (eso ya está hecho), sino diseñar la ESTRATEGIA DE PRODUCTOS (Nutrición/Bioestimulación/Sanidad).\n\n"
        
        f"{catalog_block}\n\n"
        f"{rag_block}"
        
        "--- SITUACIÓN DE LA PARCELA ---\n"
        f"1. CULTIVO: {crop_data.get('species')} ({crop_data.get('variety')}) en fase '{crop_data.get('phenological_stage')}'.\n"
        f"2. NOTAS DEL AGRICULTOR: '{payload.get('farmer_notes', '')}'\n"
        f"3. SENSORES CLAVE: Salinidad Máx ayer: {last_salinity} | Temp Máx ayer: {last_temp_max}.\n"
        f"4. RECOMENDACIÓN DE RIEGO RECIBIDA: {json.dumps(payload.get('irrigation_recommendation', {}).get('recommendation'), ensure_ascii=False)}\n"
        "-------------------------------\n\n"

        "🧠 PROCESO DE RAZONAMIENTO OBLIGATORIO (Chain of Thought):\n"
        "Paso 1: ANÁLISIS BIÓTICO (PRIORIDAD 1). Revisa las 'Notas del Agricultor'.\n"
        "   - ¿Menciona plagas, hongos (Oídio, Botrytis) o nematodos? -> Selecciona Fitosanitarios/Biocontrol del catálogo.\n"
        
        "Paso 2: ANÁLISIS ABIÓTICO (SENSORES). Revisa los datos de sensores.\n"
        "   - ¿Salinidad alta (>2.5)? -> Recomendar mejoradores de suelo o desalinizadores.\n"
        "   - ¿Calor extremo o frío? -> Recomendar antiestresantes (algas, aminoácidos).\n"
        
        "Paso 3: DEMANDA FISIOLÓGICA (FASE). Revisa la fase fenológica.\n"
        "   - Trasplante -> Enraizantes.\n"
        "   - Floración/Cuajado -> Bioestimulantes de floración.\n"
        "   - Engorde -> Potasio y Calcio.\n"
        
        "Paso 4: INTEGRACIÓN.\n"
        "   - Cruza los productos seleccionados. Si el riego es corto, prioriza vía foliar si es posible.\n"
        "   - NO repitas el razonamiento de 'el suelo está seco'. Céntrate en METABOLISMO y SANIDAD.\n\n"

        "SALIDA JSON REQUERIDA:\n"
        "{ \"product_plan\": [ { \"product_name\": \"...\", \"dose\": \"...\", \"application_timing\": \"...\", \"reason\": \"Explicación FISIOLÓGICA (ej: 'Para inducir citoquininas...')\" } ], \"agronomic_advice\": \"Resumen técnico...\" }"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        response = client.chat_completion(
            messages=messages,
            max_tokens=1500,
            temperature=0.3, # Un pelín más creativo para que explique bien la fisiología
            stream=False
        )
        
        text = response.choices[0].message.content
        parsed = _try_parse_json(text)
        
        if not parsed:
            return {
                "product_plan": [], 
                "agronomic_advice": f"Error JSON. Salida cruda: {text[:100]}..."
            }

        parsed.setdefault("product_plan", [])
        parsed.setdefault("agronomic_advice", "Sin consejo generado.")
        return parsed

    except Exception as e:
        print(f"[HF API ERROR] {e}")
        return {"product_plan": [], "agronomic_advice": f"Error API: {e}"}
