import datetime as dt
from typing import Any, Dict, List

from google.cloud import bigquery

from common.bq_timeseries import (
    query_daily_features_last_days,
    query_recent_timeseries,
)
from common.context_base import build_static_context
from common.rag_client import rag_retrieve, build_rag_context_text

from cloud_run.irrigation_agent.config import (
    PROJECT_ID, 
    BQ_DATASET, 
    LOCATION_ID, 
    LOCATION_NAME, 
    RAG_K
)

def query_irrigation_forecast_24h() -> List[Dict[str, Any]]:
    """
    Recupera métricas críticas para DECISIONES HIDRÁULICAS (Et0, Lluvia, Temp)
    de las próximas 24 horas desde la vista de Open-Meteo.
    """
    client = bigquery.Client(project=PROJECT_ID)
    
    # Usamos la vista horaria que creamos con LAX_FLOAT64
    query = f"""
    SELECT
        ts_forecast,
        temp_2m,
        et0,          -- Clave para demanda hídrica futura
        precip_mm,    -- Clave para suspender riego (lluvia directa)
        prob_precip   -- Clave para riesgo de lluvia
    FROM `{PROJECT_ID}.{BQ_DATASET}.openmeteo_hourly_forecast`
    WHERE ts_forecast >= CURRENT_TIMESTAMP()
      AND ts_forecast <= TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
    ORDER BY ts_forecast ASC
    """
    
    rows = client.query(query).result()
    
    # Serializamos las fechas a string ISO para el JSON
    results = []
    for row in rows:
        d = dict(row)
        if "ts_forecast" in d and d["ts_forecast"]:
            d["ts_forecast"] = d["ts_forecast"].isoformat()
        results.append(d)
        
    return results

def build_rag_query_from_payload(payload: Dict[str, Any]) -> str:
    """
    Construye una pregunta RAG dinámica basada en el cultivo y suelo.
    """
    crop = payload.get("crop", {}) or {}
    soil = payload.get("soil", {}) or {}

    species = crop.get("species", "cultivo en invernadero")
    phen_stage = crop.get("phenological_stage", "")
    texture = soil.get("texture", "suelo agrícola")

    surf_range = soil.get("target_vwc_surface_range", [])
    prof_range = soil.get("target_vwc_profile_range", [])
    sal_max = soil.get("max_acceptable_salinity_uScm", None)

    def fmt_range(r):
        if isinstance(r, (list, tuple)) and len(r) == 2:
            return f"{r[0]}–{r[1]} % VWC"
        return "rango objetivo de humedad"

    surf_txt = fmt_range(surf_range)
    prof_txt = fmt_range(prof_range)
    sal_txt = f"{sal_max} µS/cm" if sal_max is not None else "el nivel máximo de salinidad aceptable"

    query = (
        f"Recomendaciones agronómicas de riego y manejo de humedad del suelo y salinidad para {species} "
        f"en invernadero con riego localizado sobre suelo de textura {texture}, "
        f"en fase fenológica '{phen_stage}'. "
        f"Incluye criterios para ajustar el riego diario según la humedad del suelo "
        f"(superficie: {surf_txt}, perfil: {prof_txt}) y para prevenir o corregir problemas de salinidad "
        f"(considerando {sal_txt}). "
        f"Da prioridad a recomendaciones aplicables en agricultura intensiva bajo plástico."
    )

    return query

def build_irrigation_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Orquesta BigQuery (Pasado + Futuro) + contexto estático + overrides + notas agricultor.
    """
    context_overrides = body.get("context_overrides") or {}
    farmer_notes = body.get("farmer_notes") or ""

    # 1. Datos del Pasado (Sensores Cesens)
    daily_features = query_daily_features_last_days(days=7)
    recent_ts = query_recent_timeseries(hours_back=24)
    
    # 2. Datos del Futuro (Open-Meteo) - ¡NUEVO!
    forecast_data = query_irrigation_forecast_24h()
    
    static_ctx = build_static_context(context_overrides)

    payload: Dict[str, Any] = {
        "location_id": LOCATION_ID,
        "location_name": LOCATION_NAME,
        **static_ctx,
        "farmer_notes": farmer_notes,
        "daily_features_last_days": daily_features,
        "recent_timeseries_last_hours": recent_ts,
        "meteo_forecast_24h": forecast_data, # Inyectamos la previsión
    }

    return payload

def build_rag_context_for_payload(payload: Dict[str, Any]) -> str:
    """
    Construye el texto de contexto RAG a partir del payload.
    """
    rag_context_text = ""
    try:
        rag_query = build_rag_query_from_payload(payload)
        rag_results = rag_retrieve(rag_query, k=RAG_K)
        if rag_results:
            rag_context_text = build_rag_context_text(rag_results)
    except Exception as e:
        # No rompemos el flujo si falla el RAG, solo avisamos en el payload
        payload["rag_warning"] = f"RAG no disponible: {str(e)}"

    return rag_context_text
