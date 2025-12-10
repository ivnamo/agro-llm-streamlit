import os
import json
import datetime as dt
from typing import Dict, List, Any

import requests
from google.cloud import storage
import traceback


# ==========================
# CONFIG
# ==========================

def get_env(name: str, default: str | None = None) -> str | None:
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

# Métricas de interés por ubicación (acróniomos de Cesens)
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


def check_required_env() -> List[str]:
    required = {
        "CESENS_USER": CESENS_USER,
        "CESENS_PASS": CESENS_PASS,
        "GCS_BUCKET": GCS_BUCKET,
    }
    return [k for k, v in required.items() if not v]


# ==========================
# AUTH
# ==========================

def cesens_login() -> str:
    url = f"{CESENS_BASE_URL}/usuarios/login"
    payload = {"nombre": CESENS_USER, "clave": CESENS_PASS}

    print(f"[LOGIN] POST {url}")
    r = requests.post(url, json=payload, timeout=30)
    print(f"[LOGIN] {r.status_code} {r.text[:200]}")

    r.raise_for_status()
    data = r.json()
    token = data.get("auth")
    if not token:
        raise Exception("Respuesta de login no contiene 'auth'")
    return token


def cesens_headers(token: str) -> Dict[str, str]:
    return {
        "Authentication": f"Token {token}",
        "Accept": "application/json",
    }


# ==========================
# HELPERS RESPUESTAS
# ==========================

def ensure_list(obj: Any, label: str) -> List[Any]:
    """
    Normaliza la respuesta a lista.
    """
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, list):
                print(f"[DEBUG] {label}: usando lista del campo '{k}'")
                return v
        print(f"[DEBUG] {label}: dict sin listas internas, lo meto en lista única")
        return [obj]
    print(f"[WARN] {label}: tipo inesperado {type(obj)}, valor={obj}")
    return []


# ==========================
# API CESENS
# ==========================

def get_ubicaciones(token: str) -> List[Dict[str, Any]]:
    url = f"{CESENS_BASE_URL}/ubicaciones"
    h = cesens_headers(token)
    print(f"[UBICACIONES] GET {url}")
    r = requests.get(url, headers=h, timeout=30)
    print(f"[UBICACIONES] {r.status_code}")
    r.raise_for_status()
    data = r.json()
    ubicaciones = ensure_list(data, "ubicaciones")
    print(f"[INFO] Nº ubicaciones: {len(ubicaciones)}")
    return ubicaciones


def get_metricas(token: str) -> List[Dict[str, Any]]:
    """
    Devuelve las métricas directas desde /metricas/directas
    (o el path que se configure en CESENS_METRICAS_PATH).
    """
    path = CESENS_METRICAS_PATH
    if not path.startswith("/"):
        path = "/" + path

    url = f"{CESENS_BASE_URL}{path}"
    h = cesens_headers(token)
    print(f"[METRICAS DIRECTAS] GET {url}")
    r = requests.get(url, headers=h, timeout=60)
    print(f"[METRICAS DIRECTAS] {r.status_code}")
    r.raise_for_status()
    data = r.json()
    metricas = ensure_list(data, "metricas_directas")
    print(f"[INFO] Nº métricas directas: {len(metricas)}")

    ejemplos = [
        (
            m.get("id") or m.get("idmetrica"),
            m.get("acronimo") or m.get("nombre"),
            m.get("idUbicacion") or m.get("idubicacion") or m.get("id_ubicacion"),
        )
        for m in metricas[:5]
    ]
    print(f"[INFO] Ejemplos métricas directas: {ejemplos}")
    return metricas


def organizar_metricas_por_ubicacion(metricas: List[Dict[str, Any]]) -> Dict[Any, List[Dict[str, Any]]]:
    """
    Devuelve {id_ubicacion: [métrica,...]} usando idUbicacion/idubicacion/id_ubicacion.
    Métricas sin ubicación explícita se agrupan bajo '__global__'.
    """
    por_ub: Dict[Any, List[Dict[str, Any]]] = {}
    for m in metricas:
        ub_id = (
            m.get("idUbicacion")
            or m.get("idubicacion")
            or m.get("id_ubicacion")
        )
        key = ub_id if ub_id is not None else "__global__"
        por_ub.setdefault(key, []).append(m)

    print(f"[INFO] Métricas globales: {len(por_ub.get('__global__', []))}")
    print(f"[INFO] Ubicaciones con métricas: {len([k for k in por_ub.keys() if k != '__global__'])}")
    return por_ub


def get_datos(token: str, ubicacion_id: int, metrica_id: int,
              fecha_ini: dt.datetime, fecha_fin_exclusiva: dt.datetime) -> Any:
    """
    Llama a /datos/{ubicacionId}/{metricaId}/{YYYYMMDD-YYYYMMDD}
    usando [fecha_ini, fecha_fin_exclusiva) como intervalo Python.
    """
    fecha_ini_str = fecha_ini.strftime("%Y%m%d")
    fecha_fin_inclusiva = fecha_fin_exclusiva - dt.timedelta(days=1)
    fecha_fin_str = fecha_fin_inclusiva.strftime("%Y%m%d")

    intervalo = f"{fecha_ini_str}-{fecha_fin_str}"
    url = f"{CESENS_BASE_URL}/datos/{ubicacion_id}/{metrica_id}/{intervalo}"

    h = cesens_headers(token)
    print(f"[DATOS] GET {url}")
    r = requests.get(url, headers=h, timeout=60)
    print(f"[DATOS] {r.status_code}")
    r.raise_for_status()
    return r.json()  # normalmente {timestamp: valor}


# ==========================
# GCS (RUTA PLANA)
# ==========================

def upload_datos_to_gcs(data: Any, ubicacion_id: int, metrica: Dict[str, Any],
                        fecha_ini: dt.datetime, fecha_fin_exclusiva: dt.datetime) -> str:
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


# ==========================
# ENTRYPOINT CLOUD FUNCTION
# ==========================

def backfill_cesens(request):
    """
    Descarga las MÉTRICAS DE INTERÉS de UNA única ubicación (TARGET_UBICACION_ID)
    para los últimos 7 días y las sube a GCS en una carpeta PLANA.
    """
    try:
        missing = check_required_env()
        if missing:
            msg = f"Faltan variables de entorno: {', '.join(missing)}"
            print(msg)
            return (msg, 500)

        acronimos_interes = METRIC_ACRONIMOS_INTERES.get(TARGET_UBICACION_ID)
        if not acronimos_interes:
            msg = f"No hay métricas de interés configuradas para la ubicación {TARGET_UBICACION_ID}"
            print(msg)
            return (msg, 500)

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
            msg = f"No se encontró la ubicación con id {TARGET_UBICACION_ID} en Cesens"
            print(msg)
            return (msg, 500)

        ub_name = (
            ubicacion_objetivo.get("nombre")
            or ubicacion_objetivo.get("descripcion")
            or "sin_nombre"
        )
        print(f"[UBICACION] {TARGET_UBICACION_ID} - {ub_name}")

        # Métricas asociadas a esta ubicación + posibles globales
        metricas_ub = metricas_por_ub.get(TARGET_UBICACION_ID, []) + metricas_por_ub.get("__global__", [])
        if not metricas_ub:
            msg = f"Sin métricas directas asociadas a la ubicación {TARGET_UBICACION_ID}"
            print(msg)
            return (msg, 500)

        # Filtrar sólo métricas de interés por acrónimo
        metricas_filtradas: List[Dict[str, Any]] = []
        for met in metricas_ub:
            if not isinstance(met, dict):
                continue
            met_acronimo = met.get("acronimo") or met.get("nombre") or ""
            if met_acronimo in acronimos_interes:
                metricas_filtradas.append(met)

        print(f"[INFO] Nº métricas a procesar en esta ubicación: {len(metricas_filtradas)}")

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

        return (f"OK CESENS BACKFILL 7 DÍAS ubicación {TARGET_UBICACION_ID}", 200)

    except Exception as e:
        print("[ERROR FATAL]")
        print(traceback.format_exc())
        return (f"Error interno: {e}", 500)
