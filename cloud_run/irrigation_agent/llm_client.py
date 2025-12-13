import json
import re
from typing import Any, Dict, Optional, List
from huggingface_hub import InferenceClient
from cloud_run.irrigation_agent.config import HF_TOKEN, HF_MODEL_ID
from cloud_run.irrigation_agent.prompts import SYSTEM_PROMPT, RESPONSE_SCHEMA_HINT

def _try_parse_json(raw: str) -> Optional[Dict[str, Any]]:
    """Intenta extraer JSON usando Regex para evitar basura Markdown."""
    if not raw: return None
    cleaned = raw.replace("\u00a0", " ").strip()
    match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except: pass
    try:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        return json.loads(cleaned[start : end + 1]) if start != -1 else None
    except:
        return None

def _compress_timeseries(ts_data: Dict[str, Any], step: int = 6) -> str:
    """
    Toma las series temporales crudas (cada 10 min) y las reduce.
    step=6 significa que coge 1 dato cada 6 (1 por hora aprox).
    Devuelve un string compacto CSV-like para ahorrar tokens JSON.
    """
    metrics = ts_data.get("metrics", {})
    if not metrics:
        return "Sin datos recientes."

    # Cabecera
    keys = list(metrics.keys())
    lines = [f"TIMESTAMP | {' | '.join(keys)}"]
    
    # Asumimos que todas las métricas tienen la misma longitud y timestamps alineados
    # Si no, esto es una aproximación válida para el LLM
    try:
        first_metric = metrics[keys[0]]
        count = len(first_metric)
        
        # Iteramos con 'step' para saltarnos datos (Downsampling)
        for i in range(0, count, step):
            row_vals = []
            ts_str = first_metric[i].get("ts_utc", "")[-8:] # Solo hora HH:MM:SS
            
            for k in keys:
                val_list = metrics.get(k, [])
                if i < len(val_list):
                    val = val_list[i].get("value")
                    # Redondeamos a 1 decimal para ahorrar caracteres
                    row_vals.append(f"{val:.1f}" if isinstance(val, float) else str(val))
                else:
                    row_vals.append("-")
            
            lines.append(f"{ts_str} | {' | '.join(row_vals)}")
            
        return "\n".join(lines)
    except Exception as e:
        return f"Error comprimiendo series: {str(e)}"

def _format_forecast_compact(forecast_list: List[Dict[str, Any]]) -> str:
    """Formatea el pronóstico de forma compacta (CSV-like)"""
    if not forecast_list: return "Sin pronóstico."
    
    # Seleccionamos solo columnas clave para riego para no saturar
    cols = ["ts_forecast", "temp_2m", "et0", "prob_precip", "precip_mm"]
    lines = ["TIME | Temp | Et0 | ProbLLuvia% | mm"]
    
    for row in forecast_list:
        ts = row.get("ts_forecast", "")[11:16] # Solo HH:MM
        t = row.get("temp_2m", 0)
        et = row.get("et0", 0)
        prob = row.get("prob_precip", 0)
        mm = row.get("precip_mm", 0)
        lines.append(f"{ts} | {t} | {et} | {prob} | {mm}")
        
    return "\n".join(lines)

def call_irrigation_agent_hf(
    payload: Dict[str, Any],
    rag_context_text: Optional[str] = None,
) -> Dict[str, Any]:
    
    if not HF_TOKEN:
        return {"recommendation": {}, "explanation": "Error: Falta HF_TOKEN"}

    client = InferenceClient(model=HF_MODEL_ID, token=HF_TOKEN)

    # --- DIETA DE TOKENS ---
    # En lugar de json.dumps(payload) a lo bruto, construimos el prompt a mano y comprimido
    
    # 1. Comprimimos Series Temporales (El mayor consumidor de tokens)
    recent_ts_txt = _compress_timeseries(payload.get("recent_timeseries_last_hours", {}), step=6)
    
    # 2. Comprimimos Pronóstico
    forecast_txt = _format_forecast_compact(payload.get("meteo_forecast_24h", []))
    
    # 3. RAG y Notas
    rag_block = f"VADEMÉCUM RIEGO:\n{rag_context_text[:2000]}..." if rag_context_text else "" # Limitamos RAG
    notes = payload.get("farmer_notes", "")
    
    # 4. Contexto Estático (Suelo/Cultivo)
    soil = payload.get("soil", {})
    crop = payload.get("crop", {})

    user_content = (
        "CONTEXTO AGRONÓMICO:\n"
        f"- Cultivo: {crop.get('species')} ({crop.get('phenological_stage')})\n"
        f"- Suelo: {soil.get('texture')}. VWC Objetivo: {soil.get('target_vwc_profile_range')}\n"
        f"- Notas Operario: {notes}\n\n"
        
        f"{rag_block}\n\n"
        
        "--- DATOS DE SENSORES (ÚLTIMAS 24H RESUMIDAS) ---\n"
        f"{recent_ts_txt}\n\n"
        
        "--- PRONÓSTICO METEOROLÓGICO (24H) ---\n"
        f"{forecast_txt}\n\n"
        
        "Genera la recomendación de riego en JSON basándote en el balance hídrico (Suelo vs Pronóstico Et0)."
        f"Esquema JSON esperado:\n{json.dumps(RESPONSE_SCHEMA_HINT)}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        response = client.chat_completion(messages=messages, max_tokens=1500, temperature=0.2)
        text = response.choices[0].message.content
        parsed = _try_parse_json(text)
        return parsed or {"recommendation": {}, "explanation": "Error parseando JSON", "raw": text}
    except Exception as e:
        return {"recommendation": {}, "explanation": f"Error API: {str(e)}"}
