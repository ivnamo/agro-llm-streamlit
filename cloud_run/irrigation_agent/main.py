import json
from typing import Any, Dict

from .logic import build_irrigation_payload, build_rag_context_for_payload
from .llm_client import call_irrigation_agent_hf


def run_irrigation_agent(request):
    """
    Endpoint HTTP para el agente de riego basado en Hugging Face:
    - Método: POST.
    - Opcionalmente puede recibir un JSON con 'context_overrides' y 'farmer_notes'.
    """
    try:
        # CORS básico
        if request.method == "OPTIONS":
            headers = {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            }
            return ("", 204, headers)

        try:
            body: Dict[str, Any] = request.get_json(silent=True) or {}
        except Exception:
            body = {}

        # Construir payload completo (datos + contexto)
        payload = build_irrigation_payload(body)

        # RAG: contexto documental (si está disponible)
        rag_context_text = build_rag_context_for_payload(payload)

        # Llamar al LLM de Hugging Face
        result = call_irrigation_agent_hf(payload, rag_context_text=rag_context_text)

        headers = {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        }
        return (json.dumps(result, ensure_ascii=False), 200, headers)

    except Exception as e:
        headers = {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        }
        error_body = {"error": str(e)}
        return (json.dumps(error_body, ensure_ascii=False), 500, headers)
