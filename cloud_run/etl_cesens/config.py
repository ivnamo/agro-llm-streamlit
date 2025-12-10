import os
from typing import Dict, List, Optional

def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name, default)
    return v.strip() if isinstance(v, str) else v

CESENS_USER = get_env("CESENS_USER")
CESENS_PASS = get_env("CESENS_PASS")
CESENS_BASE_URL = get_env("CESENS_BASE_URL", "https://app.cesens.com/api")
GCS_BUCKET = get_env("GCS_BUCKET")

# Endpoint de métricas directas (igual que en Colab: /metricas/directas)
CESENS_METRICAS_PATH = get_env("CESENS_METRICAS_PATH", "/metricas/directas")

# Siempre 7 días hacia atrás para esta función
DAYS_BACK = 7

# Ubicación objetivo (ej: 8507 para S4, 8506 para Sector 2, etc.)
TARGET_UBICACION_ID = int(get_env("TARGET_UBICACION_ID", "8507"))  # por defecto S4

# Prefijo PLANO para los ficheros (clave para BigQuery)
FLAT_PREFIX = get_env("CESENS_FLAT_PREFIX", "raw/cesens/all")

# Métricas de interés por ubicación (acrónimos de Cesens)
METRIC_ACRONIMOS_INTERES: Dict[int, List[str]] = {
    7095: [
        "H",
        "T",
        "R",
        "Plu",
        "Vel",
        "VelMax",
        "Dir",
    ],
    8507: [
        "RF",
        "T_in",
        "H_in",
        "VWC10cm",
        "VWC20cm",
        "VWC40cm",
        "VWC60cm",
        "VWC2",
        "TS10cm",
        "TS20cm",
        "TS40cm",
        "TS60cm",
        "TS2",
        "Sal2",
    ],
    7094: [
        "T_in",
        "H_in",
