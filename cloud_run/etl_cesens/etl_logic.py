import datetime as dt
from typing import Any, Dict, List

from config import (
    DAYS_BACK,
    TARGET_UBICACION_ID,
    METRIC_ACRONIMOS_INTERES,
    FLAT_PREFIX,
)
from cesens_client import (
    cesens_login,
    get_ubicaciones,
    get_metricas,
    organizar_metricas_por_ubicacion,
    get_datos,
)
from gcs_writer import upload_datos_to_gcs


def run_backfill() -> str:
    """
    Lógica principal de backfill sin acoplarla a HTTP/Cloud Functions.
    Lanza excepciones si algo grave ocurre.
    """
    acronimos_interes = METRIC_ACRONIMOS_INTERES.get(TARGET_UBICACION_ID)
    if not acronimos_interes:
        raise RuntimeError(
            f"No hay métricas de interés configuradas para la ubicación {TARGET_UBICACION_ID}"
        )

    # Rango de fechas: últimos 7 días
    now_utc = dt.datetime.utcnow()
    hoy = dt.datetime(year=now_utc.year, month=now_utc.month, day=now_utc.day)
    end = hoy + dt.timedelta(days=1)  # exclusivo, incluye hoy
    start = end - dt.timedelta(days=DAYS_BACK)

    print(
        f"[BACKFILL] Últimos {DAYS_BACK} días: "
        f"{start.date()} → {end.date()} (rango único) "
        f"para ubicacion_id={TARGET_UBICACION_ID}"
    )
    print(f"[BACKFILL] Métricas de interés: {acronimos_interes}")
    print(f"[BACKFILL] Prefijo plano en GCS: {FLAT_PREFIX}")

    token = cesens_login()

    ubicaciones = get_ubicaciones(token)
    metricas = get_metricas(token)
    metricas_por_ub = organizar_metricas_por_ubicacion(metricas)

    # Buscar la ubicación objetivo
    ubicacion_objetivo = None
    for ub in ubicaciones:
        if not isinstance(ub, dict):
            continue
        ub_id = ub.get("id") or ub.get("idubicacion") or ub.get("id_ubicacion")
        if ub_id == TARGET_UBICACION_ID:
            ubicacion_objetivo = ub
            break

    if not ubicacion_objetivo:
        raise RuntimeError(
            f"No se encontró la ubicación con id {TARGET_UBICACION_ID} en Cesens"
        )

    ub_name = (
        ubicacion_objetivo.get("nombre")
        or ubicacion_objetivo.get("descripcion")
        or "sin_nombre"
    )
    print(f"[UBICACION] {TARGET_UBICACION_ID} - {ub_name}")

    # Métricas asociadas a esta ubicación + posibles globales
    metricas_ub = metricas_por_ub.get(TARGET_UBICACION_ID, []) + metricas_por_ub.get(
        "__global__", []
    )
    if not metricas_ub:
        raise RuntimeError(
            f"Sin métricas directas asociadas a la ubicación {TARGET_UBICACION_ID}"
        )

    # Filtrar sólo métricas de interés por acrónimo
    metricas_filtradas: List[Dict[str, Any]] = []
    for met in metricas_ub:
        if not isinstance(met, dict):
            continue
        met_acronimo = met.get("acronimo") or met.get("nombre") or ""
        if met_acronimo in acronimos_interes:
            metricas_filtradas.append(met)

    print(
        f"[INFO] Nº métricas a procesar en esta ubicación: {len(metricas_filtradas)}"
    )

    for met in metricas_filtradas:
        met_id = met.get("id") or met.get("idmetrica")
        met_acronimo = met.get("acronimo") or met.get("nombre") or "sin_nombre"
        if met_id is None:
            print(f"[WARN] metrica sin id: {met}")
            continue

        print(f"  [METRICA] {met_id} - {met_acronimo}")

        try:
            datos = get_datos(token, TARGET_UBICACION_ID, met_id, start, end)
            if datos:
                upload_datos_to_gcs(datos, TARGET_UBICACION_ID, met, start, end)
            else:
                print("    [INFO] Sin datos en este intervalo.")
        except Exception as e:
            print(f"    [ERROR] metrica {met_id} ubicacion {TARGET_UBICACION_ID}: {e}")

    return f"OK CESENS BACKFILL {DAYS_BACK} DÍAS ubicación {TARGET_UBICACION_ID}"
