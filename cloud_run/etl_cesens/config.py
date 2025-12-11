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
    # 7095 - Finca Experimental Mazarrón 1 (exterior)
    7095: [
        "H",        # Humedad relativa
        "T",        # Temperatura
        "R",        # Radiación solar
        "Plu",      # Precipitaciones
        "Vel",      # Velocidad viento
        "VelMax",   # Racha máxima
        "Dir",      # Dirección viento
    ],
    # 8507 - S4 (invernadero con suelo)
    8507: [
        "RF",       # PPFD / flujo fotones
        "T_in",     # Temperatura interna
        "H_in",     # Humedad relativa interna
        "VWC10cm",
        "VWC20cm",
        "VWC40cm",
        "VWC60cm",
        "VWC2",     # contenido volumétrico conector 2
        "TS10cm",
        "TS20cm",
        "TS40cm",
        "TS60cm",
        "TS2",      # temperatura de suelo conector 2
        "Sal2",     # conductividad eléctrica suelo
    ],
    # 7094 - Sector 1 (invernadero sin suelo)
    7094: [
        "T_in",
        "H_in",
        "T",
        "H",
        "R",
        "P",        # presión atmosférica
    ],
    # 8506 - Sector 2 (invernadero con suelo)
    8506: [
        "T_in",
        "H_in",
        "VWC10cm",
        "VWC20cm",
        "VWC30cm",
        "VWC40cm",
        "VWC2",
        "TS10cm",
        "TS20cm",
        "TS30cm",
        "TS40cm",
        "TS2",
        "Sal2",
    ],
}
