import requests
import json
import datetime as dt
from google.cloud import storage
from config import (
    LATITUDE, LONGITUDE, 
    HOURLY_PARAMS, DAILY_PARAMS,
    GCS_BUCKET, GCS_PREFIX
)

def fetch_forecast():
    """Descarga el pronóstico de 7 días."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(HOURLY_PARAMS),
        "daily": ",".join(DAILY_PARAMS),
        "timezone": "auto",  # Detecta zona horaria por lat/long
        "forecast_days": 7
    }

    print(f"[OPEN-METEO] GET {url} (Lat: {LATITUDE}, Lon: {LONGITUDE})")
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[ERROR] Fallo conectando a Open-Meteo: {e}")
        raise e

def upload_to_gcs(data: dict):
    """Sube el JSON crudo a GCS con timestamp."""
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)

    now = dt.datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")
    
    # Nombre de archivo particionado por día para facilitar BQ
    blob_name = f"{GCS_PREFIX}/{date_str}/forecast_{time_str}.json"
    
    blob = bucket.blob(blob_name)
    blob.upload_from_string(
        json.dumps(data, ensure_ascii=False),
        content_type="application/json"
    )
    
    print(f"[UPLOAD] Guardado en: gs://{GCS_BUCKET}/{blob_name}")
    return blob_name

def run_etl_process():
    print(">>> Iniciando ETL Open-Meteo")
    data = fetch_forecast()
    
    # Añadimos metadatos propios al JSON antes de subir
    data["_metadata"] = {
        "fetched_at_utc": dt.datetime.utcnow().isoformat(),
        "source": "open-meteo",
        "location_target": "S4"
    }
    
    path = upload_to_gcs(data)
    print("<<< Fin ETL Open-Meteo")
    return f"Success: {path}"
