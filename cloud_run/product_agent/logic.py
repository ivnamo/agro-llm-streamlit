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
    """
    Carga el catálogo y lo formatea como texto estructurado para el prompt.
    Adapta la salida al nuevo esquema con 'linea', 'composicion_clave', etc.
    """
    if not os.path.exists(CATALOG_PATH):
        print(f"[WARN] No se encontró el catálogo en {CATALOG_PATH}")
        return ""
    
    try:
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Cabecera clara para el modelo
        text_lines = [
            "CATÁLOGO MAESTRO DE PRODUCTOS ATLÁNTICA AGRÍCOLA (DISPONIBLES):",
            "Instrucción: Selecciona productos de esta lista basándote en su 'Uso' y 'Composición'."
        ]

        for p in data:
            # Extracción segura de campos con valores por defecto
            nombre = p.get("nombre", "Producto Desconocido")
            linea = p.get("linea", "General")
            tipo = p.get("tipo", "N/D")
            uso = p.get("uso_principal", "N/D")
            comp = p.get("composicion_clave", "N/D")
            dosis = p.get("dosis_ref", "Consultar ficha técnica")

            # Formato en bloque para máxima claridad del LLM
            # Usamos indentación para que el modelo entienda que todo pertenece al mismo item
            entry = (
                f"- NOMBRE: {nombre}\n"
                f"  * Línea/Tipo: {linea} | {tipo}\n"
                f"  * Composición clave: {comp}\n"
                f"  * Uso principal: {uso}\n"
                f"  * Dosis referencia: {dosis}"
            )
            text_lines.append(entry)
        
        return "\n".join(text_lines)

    except Exception as e:
        print(f"[ERROR] Fallo leyendo catálogo: {e}")
        return ""

def build_product_rag_query(payload: Dict[str, Any]) -> str:
    """Genera una búsqueda específica para productos Atlántica."""
    crop = payload.get("crop", {}).get("species", "cultivo")
    stage = payload.get("crop", {}).get("phenological_stage", "general")
    notes = payload.get("farmer_notes", "")
    
    # Incluimos info del riego si hay problemas
    irrig_reco = payload.get("irrigation_recommendation", {}).get("recommendation", {})
    warnings = " ".join(irrig_reco.get("warnings", []))
    
    query = (
        f"Catálogo productos Atlántica Agrícola para {crop} en etapa {stage}. "
        f"Soluciones para: {notes} {warnings}. "
        f"Bioestimulantes y fertilizantes para condiciones de invernadero."
    )
    return query

def build_product_agent_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Combina datos de BigQuery + Contexto Estático + Output del Agente de Riego.
    """
    # Extraemos la recomendación de riego que nos pasa el frontend/orquestador
    irrigation_output = body.get("irrigation_recommendation", {})
    farmer_notes = body.get("farmer_notes", "")
    context_overrides = body.get("context_overrides", {})

    # Volvemos a pedir datos frescos o confiamos en los pasados (aquí pedimos frescos por seguridad)
    daily_features = query_daily_features_last_days(days=7)
    recent_ts = query_recent_timeseries(hours_back=24)
    static_ctx = build_static_context(context_overrides)

    payload = {
        "location_id": LOCATION_ID,
        "location_name": LOCATION_NAME,
        **static_ctx,
        "farmer_notes": farmer_notes,
        "daily_features_last_days": daily_features,
        "recent_timeseries_last_hours": recent_ts,
        "irrigation_recommendation": irrigation_output  # Input clave
        "catalog_context": load_catalog_as_text()
    }
    return payload

def build_rag_context_for_products(payload: Dict[str, Any]) -> str:
    query = build_product_rag_query(payload)
    results = rag_retrieve(query, k=RAG_K)
    return build_rag_context_text(results)
