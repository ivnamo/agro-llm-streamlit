# cloud_run/stress_agent/logic.py
import datetime as dt
from typing import Any, Dict, List
from google.cloud import bigquery
from cloud_run.stress_agent.config import PROJECT_ID, BQ_DATASET, LOCATION_ID, LOCATION_NAME

def query_forecast_next_48h() -> List[Dict[str, Any]]:
    """
    Consulta la vista 'openmeteo_hourly_forecast' para obtener la predicción
    de las próximas 48 horas.
    """
    client = bigquery.Client(project=PROJECT_ID)
    
    query = f"""
    SELECT
        ts_forecast,
        temp_2m,
        hum_rel,
        wind_speed,
        et0,
        
        -- Parámetros clave de Fisiología
        vpd_kpa,
        rad_short,
        rad_direct,
        uv_index,
        soil_temp_6cm,
        prob_precip
        
    FROM `{PROJECT_ID}.{BQ_DATASET}.openmeteo_hourly_forecast`
    WHERE ts_forecast >= CURRENT_TIMESTAMP()
      AND ts_forecast <= TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 48 HOUR)
    ORDER BY ts_forecast ASC
    """
    
    rows = client.query(query).result()
    
    # Convertimos a lista de dicts serializables
    forecast_data = []
    for row in rows:
        item = dict(row)
        if "ts_forecast" in item and item["ts_forecast"]:
            item["ts_forecast"] = item["ts_forecast"].isoformat()
        forecast_data.append(item)
        
    return forecast_data

def build_stress_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Construye el contexto para el Agente de Estrés.
    Incluye info del cultivo (para saber su sensibilidad) y el pronóstico.
    """
    # Contexto overrideable desde el frontend (cultivo, fase...)
    user_ctx = body.get("context_overrides", {})
    crop_info = user_ctx.get("crop", {
        "species": "tomate", 
        "phenological_stage": "generativa"
    })
    
    # Obtenemos el futuro
    forecast = query_forecast_next_48h()
    
    # Resumen de alertas simples (pre-procesado para ayudar al LLM)
    # Calculamos picos máximos para darle el "titular" al modelo
    max_vpd = 0.0
    max_uv = 0.0
    min_temp = 100.0
    
    if forecast:
        max_vpd = max(d.get("vpd_kpa") or 0 for d in forecast)
        max_uv = max(d.get("uv_index") or 0 for d in forecast)
        min_temp = min(d.get("temp_2m") or 100 for d in forecast)

    payload = {
        "location_id": LOCATION_ID,
        "location_name": LOCATION_NAME,
        "crop": crop_info,
        "timestamp_analysis": dt.datetime.utcnow().isoformat(),
        "summary_metrics": {
            "max_forecast_vpd": max_vpd,
            "max_forecast_uv": max_uv,
            "min_forecast_temp": min_temp
        },
        "forecast_48h": forecast, # Serie temporal completa
        "farmer_notes": body.get("farmer_notes", "") # Por si el agricultor ya ve síntomas
    }
    
    return payload
