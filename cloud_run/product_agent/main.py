import json
from typing import Any, Dict
from cloud_run.product_agent.logic import build_product_agent_payload, build_rag_context_for_products
# Reutilizamos el cliente LLM genérico, solo cambiamos prompts internamente
from cloud_run.irrigation_agent.llm_client import call_irrigation_agent_hf as call_llm_generic 
# NOTA: Podrías refactorizar llm_client para que no se llame "irrigation", 
# pero funcionalmente sirve igual si le pasas el prompt correcto.
# Para hacerlo limpio, asumiremos que call_irrigation_agent_hf usa 
# las variables globales de prompts.py de SU módulo. 
# Como Python importa por módulos, necesitamos un llm_client propio o 
# pasar el prompt explícitamente.
# MEJOR OPCIÓN: Copiar llm_client.py a product_agent/llm_client.py 
# y cambiar los imports de prompts.

from cloud_run.product_agent.llm_client import call_product_agent_hf

def run_product_agent(request):
    try:
        if request.method == "OPTIONS":
            headers = {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            }
            return ("", 204, headers)

        body = request.get_json(silent=True) or {}
        
        # Construir payload
        payload = build_product_agent_payload(body)
        
        # RAG Productos
        rag_context = build_rag_context_for_products(payload)
        
        # Llamada LLM
        result = call_product_agent_hf(payload, rag_context_text=rag_context)
        
        return (json.dumps(result, ensure_ascii=False), 200, {"Content-Type": "application/json"})

    except Exception as e:
        return (json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"})
