import traceback
from typing import Any, Tuple

from config import check_required_env
from etl_logic import run_backfill


def backfill_cesens(request: Any) -> Tuple[str, int]:
    """
    Entry point para Cloud Function HTTP.

    Descarga las MÉTRICAS DE INTERÉS de UNA única ubicación (TARGET_UBICACION_ID)
    para los últimos N días y las sube a GCS en una carpeta PLANA.
    """
    try:
        missing = check_required_env()
        if missing:
            msg = f"Faltan variables de entorno: {', '.join(missing)}"
            print(msg)
            return (msg, 500)

        msg = run_backfill()
        return (msg, 200)

    except Exception as e:
        print("[ERROR FATAL]")
        print(traceback.format_exc())
        return (f"Error interno: {e}", 500)
