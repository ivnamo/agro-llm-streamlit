import json
import datetime
from flask import Request
from cloud_run.product_agent.logic import build_product_agent_payload, build_rag_context_for_products
from cloud_run.product_agent.llm_client import call_product_agent_hf

def run_product_agent(request: Request):
    """
    Cloud Function del Agente de Productos (Agrónomo).
    Devuelve plan de productos + Log de Auditoría.
    """
    try:
        if request.method == "OPTIONS":
            headers = {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            }
            return ("", 204, headers)

        body = request.get_json(silent=True) or {}
        
        # 1. Construir Payload (Aquí se juntan Riego + Estrés + Contexto)
        payload = build_product_agent_payload(body)
        
        # 2. RAG (Contexto documental)
        rag_context = build_rag_context_for_products(payload)
        
        # 3. Llamada al LLM
        agent_result = call_product_agent_hf(payload, rag_context_text=rag_context)
        
        # 4. GENERACIÓN DEL LOG DE AUDITORÍA (TRAZABILIDAD)
        # Guardamos la "foto" exacta de lo que sabía el agente para tomar la decisión
        audit_log = {
            "timestamp_utc": datetime.datetime.utcnow().isoformat(),
            "case_inputs": {
                "farmer_notes": payload.get("farmer_notes"),
                "crop_context": payload.get("crop"),
                "irrigation_input": payload.get("irrigation_recommendation"),
                "stress_input": payload.get("stress_alert")
            },
            "ai_reasoning_output": agent_result,
            "model_used": "Qwen/Qwen2.5-7B-Instruct", # O la variable de entorno HF_MODEL_ID
            "rag_context_snippet": rag_context[:200] + "..." if rag_context else "N/A"
        }

        # 5. Respuesta Final: Unimos resultado y log
        response_data = {
            **agent_result,       # product_plan, agronomic_advice
            "audit_log": audit_log # <--- Para descargar/guardar
        }
        
        headers = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
        return (json.dumps(response_data, ensure_ascii=False), 200, headers)

    except Exception as e:
        headers = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
        return (json.dumps({"error": str(e)}), 500, headers)
