import os
from typing import Any, Dict, List

from google.cloud import bigquery

# Config básica compartida (puede usarse desde varios agentes)
PROJECT_ID = os.getenv("PROJECT_ID", "tfg-agro-llm")
BQ_DATASET = os.getenv("BQ_DATASET", "agro_data")

# Cliente BigQuery global
bq_client = bigquery.Client(project=PROJECT_ID)


def query_daily_features_last_days(days: int = 7) -> List[Dict[str, Any]]:
    """
    Devuelve features diarias de los últimos N días para la vista cesens_s4_daily_features.
    (Orientado ahora a S4, pero reutilizable por otros agentes que usen la misma vista).
    """
    query = f"""
    SELECT *
    FROM `{PROJECT_ID}.{BQ_DATASET}.cesens_s4_daily_features`
    WHERE fecha >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
    ORDER BY fecha
    """
    rows = bq_client.query(query).result()
    results: List[Dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        if "fecha" in d and hasattr(d["fecha"], "isoformat"):
            d["fecha"] = d["fecha"].isoformat()
        results.append(d)
    return results


def query_recent_timeseries(hours_back: int = 72) -> Dict[str, List[Dict[str, Any]]]:
    """
    Devuelve serie temporal ancha (wide) de las últimas horas para cesens_s4_wide.
    """
    query = f"""
    SELECT
      ts_utc,
      RF,
      T_in,
      H_in,
      VWC10cm,
      VWC20cm,
      VWC40cm,
      VWC60cm,
      VWC2,
      TS10cm,
      TS20cm,
      TS40cm,
      TS60cm,
      TS2,
      Sal2
    FROM `{PROJECT_ID}.{BQ_DATASET}.cesens_s4_wide`
    WHERE ts_utc >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours_back} HOUR)
    ORDER BY ts_utc
    """
    rows = list(bq_client.query(query).result())

    metrics: Dict[str, List[Dict[str, float]]] = {
        "RF": [],
        "T_in": [],
        "H_in": [],
        "VWC10cm": [],
        "VWC20cm": [],
        "VWC40cm": [],
        "VWC60cm": [],
        "VWC2": [],
        "TS10cm": [],
        "TS20cm": [],
        "TS40cm": [],
        "TS60cm": [],
        "TS2": [],
        "Sal2": [],
    }

    for row in rows:
        ts_iso = row["ts_utc"].isoformat()
        for m in metrics.keys():
            value = row.get(m)
            if value is not None:
                metrics[m].append({"ts_utc": ts_iso, "value": float(value)})

    return {"hours_back": hours_back, "metrics": metrics}
