from typing import Any, Dict


def build_static_context(overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Datos estáticos de cultivo/suelo/sistema de riego para el MVP,
    con posibilidad de sobreescribir campos desde la web (overrides).
    Pensado para riego, pero reutilizable por otros agentes.
    """
    base = {
        "crop": {
            "species": "tomate",
            "variety": "indeterminado",
            "phenological_stage": "cuajado_y_engorde",
            "planting_date": "2025-09-15",
        },
        "soil": {
            "texture": "franco-arenoso",
            "field_capacity_vwc": 35.0,
            "permanent_wilting_point_vwc": 15.0,
            "target_vwc_surface_range": [25.0, 35.0],
            "target_vwc_profile_range": [22.0, 35.0],
            "max_acceptable_salinity_uScm": 2500.0,
        },
        "irrigation_system": {
            "type": "riego_por_goteo",
            "emitters_per_plant": 2,
            "flow_lph_per_emitter": 1.6,
            "plants_per_m2": 2.5,
        },
    }

    overrides = overrides or {}

    def merge_dict(key: str):
        if key in overrides and isinstance(overrides[key], dict):
            for k, v in overrides[key].items():
                if v not in (None, "", []):
                    base[key][k] = v

    for section in ["crop", "soil", "irrigation_system"]:
        merge_dict(section)

    return base
