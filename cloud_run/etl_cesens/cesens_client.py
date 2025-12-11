import datetime as dt
from typing import Any, Dict, List

import requests

from config import CESENS_BASE_URL, CESENS_USER, CESENS_PASS, CESENS_METRICAS_PATH


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


def get_datos(
    token: str,
    ubicacion_id: int,
    metrica_id: int,
    fecha_ini: dt.datetime,
    fecha_fin_exclusiva: dt.datetime,
) -> Any:
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
