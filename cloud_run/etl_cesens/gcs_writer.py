import json
import datetime as dt
from typing import Any, Dict

from google.cloud import storage

from config import GCS_BUCKET, FLAT_PREFIX


def upload_datos_to_gcs(
    data: Any,
    ubicacion_id: int,
    metrica: Dict[str, Any],
    fecha_ini: dt.datetime,
    fecha_fin_exclusiva: dt.datetime,
) -> str:
    """
    Sube los datos a una ruta PLANA en GCS, para que BigQuery pueda usar un único wildcard:
    gs://<bucket>/raw/cesens/all/*.json (o el prefijo que definas en CESENS_FLAT_PREFIX).
    """
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)

    metrica_id = metrica.get("id") or metrica.get("idmetrica")
    metrica_acronimo = metrica.get("acronimo") or metrica.get("nombre") or f"metrica_{metrica_id}"

    # Nombre de archivo plano con info útil
    fname = (
        f"datos_ubic_{ubicacion_id}_met_{metrica_id}_"
        f"{metrica_acronimo}_{fecha_ini:%Y%m%d}_{(fecha_fin_exclusiva - dt.timedelta(days=1)):%Y%m%d}.json"
    )

    # Prefijo plano configurable (por defecto raw/cesens/all)
    blob_name = f"{FLAT_PREFIX}/{fname}"

    payload = {
        "ubicacion_id": ubicacion_id,
        "metrica_id": metrica_id,
        "metrica_acronimo": metrica_acronimo,
        "fecha_inicio": fecha_ini.isoformat(),
        "fecha_fin_exclusiva": fecha_fin_exclusiva.isoformat(),
        "datos": data,
    }

    blob = bucket.blob(blob_name)
    blob.upload_from_string(
        json.dumps(payload, ensure_ascii=False),
        content_type="application/json",
    )

    gcs_path = f"gs://{GCS_BUCKET}/{blob_name}"
    print(f"[UPLOAD] {gcs_path}")
    return gcs_path
