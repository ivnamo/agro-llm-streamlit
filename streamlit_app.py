import streamlit as st
import requests
import json

# ==========================
# CONFIG
# ==========================

CLOUD_FUNCTION_URL = st.secrets["cloud_function_url"]  # la metes en secrets.toml

st.set_page_config(
    page_title="Recomendador de Riego S4",
    page_icon="💧",
    layout="wide"
)

st.title("💧 Asistente Inteligente de Riego — S4 Invernadero")
st.write("Esta aplicación consulta la función en Google Cloud y genera recomendaciones de riego usando Gemini.")


# ==========================
# UI — Botón para ejecutar recomendación
# ==========================

st.subheader("Generar recomendación de riego")

if st.button("Obtener recomendación ahora", type="primary"):
    with st.spinner("Consultando sistema inteligente de riego..."):
        try:
            response = requests.post(CLOUD_FUNCTION_URL, timeout=60)
            st.write("STATUS", response.status_code)
            st.write("RAW TEXT", response.text)
            try:
                data = response.json()
            except Exception as e:
                st.error(f"JSON decode error: {e}")
                st.stop()

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
            st.metric("¿Aplicar riego?", "Sí" if reco["apply_irrigation"] else "No")
            st.metric("Intensidad recomendada", reco["reason"])
        with col2:
            st.metric("Litros/m² sugeridos", reco["suggested_water_l_m2"])

        # ---- Tabla de ciclos ----
        st.markdown("### ⏱️ Ciclos propuestos")
        if "suggested_cycles" in reco:
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
st.caption("TFG Agro LLM — Recomendaciones automáticas para optimización de riego.")
