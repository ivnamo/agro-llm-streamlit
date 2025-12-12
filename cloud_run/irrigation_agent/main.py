import json
from typing import Any, Dict
from cloud_run.irrigation_agent.logic import (
    build_irrigation_payload,
    build_rag_context_for_payload,
)
from cloud_run.irrigation_agent.llm_client import call_irrigation_agent_hf

def run_irrigation_agent(request):
    """
    Endpoint HTTP para el agente de riego.
    Devuelve: { "agent_response": {...}, "data_context": {...} }
    """
    try:
        # CORS
        if request.method == "OPTIONS":
            headers = {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            }
            return ("", 204, headers)

        body = request.get_json(silent=True) or {}
        
        # 1. Recuperar datos y construir payload
        payload = build_irrigation_payload(body)

        # 2. RAG (Contexto documental)
        rag_context_text = build_rag_context_for_payload(payload)

        # 3. Llamar al LLM (Cerebro)
        llm_result = call_irrigation_agent_hf(payload, rag_context_text=rag_context_text)

        # 4. PREPARAR RESPUESTA COMPLETA
        # Devolvemos tanto la opinión del LLM como los datos crudos para el Frontend
        response_data = {
            "agent_response": llm_result,  # Lo que dice la IA
            "data_context": {             # Los datos que miró la IA (para gráficas)
                "daily_features": payload.get("daily_features_last_days", []),
                "recent_timeseries": payload.get("recent_timeseries_last_hours", {})
            }
        }

        headers = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
        return (json.dumps(response_data, ensure_ascii=False), 200, headers)

    except Exception as e:
        headers = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
        return (json.dumps({"error": str(e)}), 500, headers)
