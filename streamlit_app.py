import streamlit as st
import requests
import json

# ==========================
# CONFIG
# ==========================

CLOUD_FUNCTION_URL = st.secrets["cloud_function_url"]  # apunta a recomendar_riego_s4_hf

st.set_page_config(
    page_title="Recomendador de Riego S4 (HF)",
    page_icon="💧",
    layout="wide"
)

st.title("💧 Asistente Inteligente de Riego — S4 Invernadero (Hugging Face)")
st.write(
    "Esta aplicación consulta una función en Google Cloud que usa un modelo de Hugging Face "
    "para generar recomendaciones de riego."
)

# ==========================
# FORMULARIO DE PARÁMETROS AGRONÓMICOS
# ==========================

st.markdown("## 🧩 Parámetros que puede indicar el agricultor (opcionales)")

with st.form("parametros_agricultor"):

    st.markdown("### 🌱 Cultivo")
    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        crop_species = st.selectbox(
            "Especie",
            options=["tomate", "pimiento", "otro"],
            index=0
        )
    with col_c2:
        crop_variety = st.text_input("Variedad (opcional)", value="indeterminado")
    with col_c3:
        crop_stage = st.selectbox(
            "Estado fenológico",
            options=[
                "trasplante",
                "crecimiento_vegetativo",
                "floración",
                "cuajado_y_engorde",
                "maduración"
            ],
            index=3
        )

    planting_date = st.text_input(
        "Fecha de plantación (YYYY-MM-DD, opcional)",
        value="2025-09-15"
    )

    st.markdown("### 🌍 Suelo")
    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        soil_texture = st.selectbox(
            "Textura de suelo",
            options=[
                "franco-arenoso",
                "arenoso",
                "franco",
                "franco-arcilloso",
                "arcilloso",
            ],
            index=0
        )
    with col_s2:
        field_capacity = st.number_input(
            "Capacidad de campo VWC (%)",
            min_value=0.0,
            max_value=60.0,
            value=35.0,
            step=0.5
        )
    with col_s3:
        pwp = st.number_input(
            "Punto de marchitez VWC (%)",
            min_value=0.0,
            max_value=60.0,
            value=15.0,
            step=0.5
        )

    col_s4, col_s5, col_s6 = st.columns(3)
    with col_s4:
        target_vwc_surface_min = st.number_input(
            "VWC superficie mín. objetivo (%)",
            min_value=0.0, max_value=60.0, value=25.0, step=0.5
        )
    with col_s5:
        target_vwc_surface_max = st.number_input(
            "VWC superficie máx. objetivo (%)",
            min_value=0.0, max_value=60.0, value=35.0, step=0.5
        )
    with col_s6:
        max_salinity = st.number_input(
            "Salinidad máxima aceptable (µS/cm)",
            min_value=0.0, max_value=10000.0, value=2500.0, step=100.0
        )

    st.markdown("### 🚰 Sistema de riego")
    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1:
        irrigation_type = st.selectbox(
            "Tipo de riego",
            options=["riego_por_goteo", "aspersión", "otro"],
            index=0
        )
    with col_r2:
        emitters_per_plant = st.number_input(
            "Emisores por planta",
            min_value=0.0, max_value=10.0, value=2.0, step=0.5
        )
    with col_r3:
        flow_lph_per_emitter = st.number_input(
            "Caudal por emisor (L/h)",
            min_value=0.0, max_value=10.0, value=1.6, step=0.1
        )

    plants_per_m2 = st.number_input(
        "Plantas por m²",
        min_value=0.0, max_value=10.0, value=2.5, step=0.1
    )

    st.markdown("### 🗒️ Comentarios del agricultor (opcional)")
    farmer_notes = st.text_area(
        "Describe aquí problemas observados, riegos recientes, estrés, etc.",
        placeholder="Ejemplo: 'Ayer regué 6 L/m² en dos ciclos. Veo algo de marchitez por la tarde...'"
    )

    submitted = st.form_submit_button("Obtener recomendación ahora", type="primary")

# ==========================
# LLAMADA AL BACKEND CUANDO SE PULSA EL BOTÓN
# ==========================

if submitted:
    with st.spinner("Consultando sistema inteligente de riego (Hugging Face)..."):

        # Construimos el JSON que enviamos al backend.
        # Si el usuario no cambia nada, son básicamente los mismos valores por defecto.
        context_overrides = {
            "crop": {
                "species": crop_species,
                "variety": crop_variety,
                "phenological_stage": crop_stage,
                "planting_date": planting_date,
            },
            "soil": {
                "texture": soil_texture,
                "field_capacity_vwc": field_capacity,
                "permanent_wilting_point_vwc": pwp,
                "target_vwc_surface_range": [
                    target_vwc_surface_min,
                    target_vwc_surface_max,
                ],
                # El rango de perfil lo dejamos que lo derive el backend si quieres
                # o podrías pedirlo explícitamente en la UI.
                "max_acceptable_salinity_uScm": max_salinity,
            },
            "irrigation_system": {
                "type": irrigation_type,
                "emitters_per_plant": emitters_per_plant,
                "flow_lph_per_emitter": flow_lph_per_emitter,
                "plants_per_m2": plants_per_m2,
            },
        }

        body = {
            "context_overrides": context_overrides,
            "farmer_notes": farmer_notes,
        }

        try:
            response = requests.post(
                CLOUD_FUNCTION_URL,
                json=body,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            st.error(f"Error al conectar con la función: {e}")
            st.stop()

    # ==========================
    # Mostrar resultados
    # ==========================

    if data.get("recommendation") is None:
        st.error("La función no devolvió una recomendación válida.")
        st.json(data)
    else:
        reco = data["recommendation"]
        explanation = data.get("explanation", "")

        st.success("Recomendación generada correctamente")

        # ---- Tarjeta principal ----
        st.markdown("### 📝 Resumen de la recomendación")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("¿Aplicar riego?", "Sí" if reco.get("apply_irrigation") else "No")
            st.metric("Intensidad recomendada", reco.get("reason", "-"))
        with col2:
            st.metric(
                "Litros/m² sugeridos",
                reco.get("suggested_water_l_m2", "n/d")
            )

        # ---- Tabla de ciclos ----
        st.markdown("### ⏱️ Ciclos propuestos")
        if "suggested_cycles" in reco and reco["suggested_cycles"]:
            st.table(reco["suggested_cycles"])
        else:
            st.info("No se devolvieron ciclos específicos.")

        # ---- Advertencias ----
        st.markdown("### ⚠️ Advertencias y observaciones")
        if "warnings" in reco and reco["warnings"]:
            for w in reco["warnings"]:
                st.warning(w)
        else:
            st.write("Sin advertencias importantes.")

        # ---- Explicación ----
        st.markdown("### 🤖 Explicación del modelo")
        st.write(explanation)

        # ---- JSON completo ----
        with st.expander("Ver JSON completo de respuesta"):
            st.json(data)

st.markdown("---")
st.caption("TFG Agro LLM — Recomendaciones automáticas para optimización de riego (modelo Hugging Face).")

