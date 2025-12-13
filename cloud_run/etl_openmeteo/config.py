import os

# ==========================
# CONFIGURACIÓN OPEN-METEO
# ==========================

# Coordenadas por defecto (Mazarrón, Murcia aprox)
# ¡Ajustar a la ubicación exacta del invernadero S4!
LATITUDE = float(os.getenv("LATITUDE", "37.60"))
LONGITUDE = float(os.getenv("LONGITUDE", "-1.31"))

# Bucket de Google Cloud Storage
GCS_BUCKET = os.getenv("GCS_BUCKET", "tfg-agro-llm")

# Ruta donde se guardarán los jsons crudos
# Estructura: raw/openmeteo/forecast/YYYY-MM-DD/forecast_HHMM.json
GCS_PREFIX = os.getenv("OPENMETEO_PREFIX", "raw/openmeteo/forecast")

# cloud_run/etl_openmeteo/config.py

HOURLY_PARAMS = [
    # --- Básicos ---
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation_probability",
    "precipitation",
    "wind_speed_10m",
    
    # --- Agente de Riego (Hidráulica) ---
    "et0_fao_evapotranspiration",
    "soil_moisture_0_to_1cm",
    
    # --- Agente de Estrés (Fisiología) ---
    "vapour_pressure_deficit",  # <--- CRÍTICO para cierre estomático
    "shortwave_radiation",      # <--- Carga térmica total
    "direct_radiation",         # <--- Intensidad directa (quemaduras)
    "uv_index",                 # <--- Daño celular (para recomendar Archer Eclipse)
    "soil_temperature_6cm"      # <--- Estrés radicular (bloqueo absorción)
]

DAILY_PARAMS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "et0_fao_evapotranspiration",
    "uv_index_max"              # <--- Pico diario de radiación dañina
]
