import traceback
from flask import Request
from client import run_etl_process

def fetch_openmeteo(request: Request):
    """
    Cloud Function Trigger.
    Puede ser llamada por Cloud Scheduler cada X horas (ej. cada 6h).
    """
    try:
        # Soporte básico CORS por si se llama desde navegador (opcional)
        if request.method == "OPTIONS":
            headers = {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST",
                "Access-Control-Allow-Headers": "Content-Type",
            }
            return ("", 204, headers)

        result_msg = run_etl_process()
        return (result_msg, 200)

    except Exception as e:
        print(f"[FATAL ERROR] {traceback.format_exc()}")
        return (f"Error interno: {str(e)}", 500)
