import json
import os
from typing import Any, Dict, List
from common.bq_timeseries import query_daily_features_last_days, query_recent_timeseries
from common.context_base import build_static_context
from common.rag_client import rag_retrieve, build_rag_context_text
from cloud_run.product_agent.config import LOCATION_ID, LOCATION_NAME, RAG_K

# Ruta al catálogo json dentro del contenedor
CATALOG_PATH = os.path.join(os.path.dirname(__file__), "catalog.json")

def load_catalog_as_text() -> str:
    """Carga el catálogo y lo formatea como texto estructurado."""
    if not os.path.exists(CATALOG_PATH):
        return ""
    try:
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        text_lines = ["CATÁLOGO MAESTRO (DISPONIBLES):"]
        for p in data:
            entry = (f"- {p.get('nombre', '?')} ({p.get('linea','?')})\n"
                     f"  Uso: {p.get('uso_principal','?')}\n"
                     f"  Dosis: {p.get('dosis_ref','?')}")
            text_lines.append(entry)
        return "\n".join(text_lines)
    except:
        return ""

def build_product_rag_query(payload: Dict[str, Any]) -> str:
    crop = payload.get("crop", {}).get("species", "cultivo")
    notes = payload.get("farmer_notes", "")
    
    # Incluimos info de riego y estrés en la búsqueda
    irrig_warn = " ".join(payload.get("irrigation_recommendation", {}).get("warnings", []))
    stress_risk = payload.get("stress_alert", {}).get("primary_risk", "")
    
    query = (
        f"Productos Atlántica Agrícola para {crop}. "
        f"Soluciones para: {notes} {irrig_warn} {stress_risk}. "
        f"Bioestimulantes y fitosanitarios."
    )
    return query

def build_product_agent_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Combina datos BQ + Contexto Estático + Inputs de otros agentes.
    """
    irrigation_output = body.get("irrigation_recommendation", {})
    stress_output = body.get("stress_alert", {})  # <--- NUEVO INPUT
    farmer_notes = body.get("farmer_notes", "")
    context_overrides = body.get("context_overrides", {})

    daily_features = query_daily_features_last_days(days=7)
    # No pedimos series horarias aquí para ahorrar, el agente de riego ya hizo el trabajo sucio
    static_ctx = build_static_context(context_overrides)

    payload = {
        "location_id": LOCATION_ID,
        "location_name": LOCATION_NAME,
        **static_ctx,
        "farmer_notes": farmer_notes,
        "daily_features_last_days": daily_features,
        "irrigation_recommendation": irrigation_output,
        "stress_alert": stress_output,  # <--- SE PASA AL LLM
        "catalog_context": load_catalog_as_text()
    }
    return payload

def build_rag_context_for_products(payload: Dict[str, Any]) -> str:
    query = build_product_rag_query(payload)
    results = rag_retrieve(query, k=RAG_K)
    return build_rag_context_text(results)
