import json
from flask import Request
from cloud_run.stress_agent.logic import build_stress_payload
from cloud_run.stress_agent.llm_client import call_stress_agent_hf

def run_stress_agent(request: Request):
    """
    Cloud Function para el Agente de Estrés (Fisiología Vegetal).
    Entrada: JSON con context_overrides (cultivo) y farmer_notes.
    Salida: JSON con stress_alert y recomendaciones de manejo climático.
    """
    try:
        # 1. Gestión de CORS (para que Streamlit pueda llamar sin problemas)
        if request.method == "OPTIONS":
            headers = {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            }
            return ("", 204, headers)

        body = request.get_json(silent=True) or {}
        
        # 2. Construir el Payload (Datos de Cultivo + Pronóstico 48h BigQuery)
        # Aquí es donde se llama a la vista openmeteo_hourly_forecast
        payload = build_stress_payload(body)
        
        # 3. Llamada al Cerebro (Hugging Face / Gemini)
        # El prompt del "Fisiólogo" analizará el VPD y el UV
        agent_response = call_stress_agent_hf(payload)
        
        # 4. Respuesta Final
        # Devolvemos tanto la opinión del agente como los datos crudos del pronóstico
        # para que el Frontend pueda pintar gráficas si quiere.
        response_data = {
            "agent_response": agent_response,
            "data_context": {
                "forecast_48h": payload.get("forecast_48h", []),
                "summary": payload.get("summary_metrics", {})
            }
        }
        
        headers = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
        return (json.dumps(response_data, ensure_ascii=False), 200, headers)

    except Exception as e:
        # Manejo de errores robusto
        print(f"[ERROR STRESS AGENT] {e}")
        error_resp = {"error": str(e)}
        headers = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
        return (json.dumps(error_resp, ensure_ascii=False), 500, headers)
