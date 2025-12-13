import json
import re
from typing import Any, Dict, Optional
from huggingface_hub import InferenceClient
from cloud_run.product_agent.config import HF_TOKEN, HF_MODEL_ID
from cloud_run.product_agent.prompts import SYSTEM_PROMPT, RESPONSE_SCHEMA_HINT

def _try_parse_json(raw: str) -> Optional[Dict[str, Any]]:
    """
    Intenta extraer y parsear un JSON de un string sucio usando Regex.
    Misma lógica robusta que en el Agente de Estrés.
    """
    if not raw:
        return None
        
    # 1. Limpieza básica de caracteres invisibles
    cleaned = raw.replace("\u00a0", " ").strip()
    
    # 2. Estrategia Regex: Buscar el contenido entre el primer { y el último }
    match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
    
    if match:
        candidate = match.group(1)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
            
    # 3. Estrategia Fallback manual
    try:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            candidate = cleaned[start : end + 1]
            return json.loads(candidate)
    except:
        pass

    return None

def call_product_agent_hf(
    payload: Dict[str, Any],
    rag_context_text: Optional[str] = None,
) -> Dict[str, Any]:
    
    if not HF_TOKEN:
        return {"product_plan": [], "agronomic_advice": "Error: Falta HF_TOKEN."}

    client = InferenceClient(model=HF_MODEL_ID, token=HF_TOKEN)

    # 1. Preparar Contextos
    catalog_block = payload.get("catalog_context", "")
    rag_block = f"VADEMÉCUM TÉCNICO (Referencia):\n{rag_context_text}\n\n" if rag_context_text else ""

    # 2. Extraer Inputs de otros Agentes
    irrig_reco = payload.get('irrigation_recommendation', {}).get('recommendation', {})
    stress_alert = payload.get('stress_alert', {}).get('stress_alert', {})

    # 3. Construir Prompt
    user_content = (
        "ACTÚA COMO UN INGENIERO AGRÓNOMO SENIOR ESPECIALISTA EN NUTRICIÓN Y FISIOLOGÍA VEGETAL.\n"
        "Tu objetivo es diseñar la ESTRATEGIA DE PRODUCTOS (Nutrición/Bioestimulación/Sanidad).\n\n"
        
        f"{catalog_block}\n\n"
        f"{rag_block}"
        
        "--- SITUACIÓN INTEGRAL DE LA PARCELA ---\n"
        f"1. CULTIVO: {payload.get('crop', {}).get('species')} ({payload.get('crop', {}).get('phenological_stage')}).\n"
        f"2. NOTAS DEL AGRICULTOR: '{payload.get('farmer_notes', '')}'\n"
        f"3. INFORME HIDRÁULICO (Riego): {json.dumps(irrig_reco, ensure_ascii=False)}\n"
        f"4. ALERTA FISIOLÓGICA (Estrés/Clima): {json.dumps(stress_alert, ensure_ascii=False)}\n"
        "----------------------------------------\n\n"

        "🧠 PROCESO DE RAZONAMIENTO OBLIGATORIO (Chain of Thought):\n"
        "Paso 1: ANÁLISIS BIÓTICO (PRIORIDAD 1). Revisa 'Notas del Agricultor' y 'Alerta Fisiológica'.\n"
        "   - ¿Hay riesgo de hongos (Botrytis/Oídio) por clima húmedo? -> Busca Fitosanitarios/Biocontrol en el catálogo.\n"
        "   - ¿Hay plagas? -> Busca insecticidas biológicos.\n"
        
        "Paso 2: ANÁLISIS ABIÓTICO (ESTRÉS). Revisa la 'Alerta Fisiológica'.\n"
        "   - ¿VPD Alto o Calor extremo? -> Recomendar antiestresantes (algas, aminoácidos).\n"
        "   - ¿Salinidad o Suelo pobre? -> Recomendar mejoradores de suelo.\n"
        
        "Paso 3: DEMANDA FISIOLÓGICA (FASE). Revisa la fase del cultivo.\n"
        "   - Trasplante -> Enraizantes. Floración -> Cuajado. Engorde -> Potasio.\n"
        
        "Paso 4: INTEGRACIÓN.\n"
        "   - Si el riego es reducido por lluvia, prioriza aplicaciones FOLIARES.\n\n"

        "SALIDA JSON REQUERIDA (NO incluyas markdown, SOLO el JSON):\n"
        f"{json.dumps(RESPONSE_SCHEMA_HINT, ensure_ascii=False)}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        response = client.chat_completion(
            messages=messages,
            max_tokens=1500,
            temperature=0.2, # Baja temperatura para formato estricto
            stream=False
        )
        
        text = response.choices[0].message.content
        parsed = _try_parse_json(text)
        
        if not parsed:
            # Devuelve el texto crudo para que puedas depurar si vuelve a fallar
            return {
                "product_plan": [], 
                "agronomic_advice": "Error JSON en Agente Productos. Ver 'raw'.",
                "raw": text
            }

        parsed.setdefault("product_plan", [])
        parsed.setdefault("agronomic_advice", "Sin consejo generado.")
        return parsed

    except Exception as e:
        print(f"[HF API ERROR] {e}")
        return {"product_plan": [], "agronomic_advice": f"Error API: {e}"}
