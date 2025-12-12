import streamlit as st
import requests
import pandas as pd
import json
import datetime as dt

# ==========================
# CONFIGURACIÓN
# ==========================
st.set_page_config(page_title="Agro-IA: Riego y Manejo", page_icon="🌿", layout="wide")

# URLs de los servicios (Idealmente en st.secrets)
IRRIGATION_URL = st.secrets.get("irrigation_url", "URL_DE_TU_IRRIGATION_AGENT_AQUI") 
PRODUCT_URL = st.secrets.get("product_url", "URL_DE_TU_PRODUCT_AGENT_AQUI")

# Si no están en secrets, úsalas hardcodeadas temporalmente para probar
# IRRIGATION_URL = "https://irrigation-agent-..."
# PRODUCT_URL = "https://product-agent-..."

# ==========================
# FUNCIONES AUXILIARES (VISUALIZACIÓN)
# ==========================

def parse_timeseries_to_df(ts_data):
    """Convierte el JSON de series temporales en un DataFrame ancho para st.line_chart"""
    if not ts_data or "metrics" not in ts_data:
        return pd.DataFrame()
    
    metrics = ts_data["metrics"] # Diccionario { "RF": [{ts, val}...], "T_in": ... }
    
    # Estrategia: Crear un DF por métrica y luego hacer merge/join por timestamp
    dfs = []
    for metric_name, values in metrics.items():
        if not values:
            continue
        df_m = pd.DataFrame(values)
        df_m["ts_utc"] = pd.to_datetime(df_m["ts_utc"])
        df_m = df_m.rename(columns={"value": metric_name})
        df_m = df_m.set_index("ts_utc")
        dfs.append(df_m)
    
    if not dfs:
        return pd.DataFrame()
        
    # Unir todos en un solo DF ancho
    df_final = pd.concat(dfs, axis=1).sort_index()
    return df_final

def render_quality_indicator(data_context):
    """Muestra semáforos de calidad de datos (Historia 2.3)"""
    ts = data_context.get("recent_timeseries", {}).get("metrics", {})
    daily = data_context.get("daily_features", [])
    
    col1, col2, col3 = st.columns(3)
    
    # 1. Disponibilidad Sensores (Check rápido si hay datos recientes)
    has_data = any(len(v) > 0 for v in ts.values())
    with col1:
        if has_data:
            st.success("📡 Sensores Online")
        else:
            st.error("📡 Sin conexión Sensores")
            
    # 2. Consistencia Histórica
    days_count = len(daily)
    with col2:
        if days_count >= 5:
            st.success(f"📅 Histórico: {days_count} días")
        elif days_count > 0:
            st.warning(f"📅 Histórico parcial ({days_count} días)")
        else:
            st.error("📅 Sin histórico diario")

    # 3. Latencia (Fake check para demo, se podría calcular real)
    with col3:
        st.info("⏱️ Latencia: < 5min")

# ==========================
# INTERFAZ PRINCIPAL
# ==========================

st.title("🌿 Sistema Integral de Gestión Agrícola (S4)")
st.markdown("Orquestación de Agentes: **Ingeniería Hidráulica** + **Manejo de Productos**")

# --- SIDEBAR: PARÁMETROS ---
with st.sidebar:
    st.header("📋 Configuración de Parcela")
    with st.form("params_form"):
        st.subheader("Cultivo")
        crop_species = st.selectbox("Especie", ["tomate", "pimiento", "pepino"], index=0)
        crop_stage = st.selectbox("Fase", ["trasplante", "crecimiento", "floracion", "cuajado_y_engorde", "maduracion"], index=3)
        
        st.subheader("Objetivos Suelo")
        target_vwc = st.slider("Humedad Objetivo (%)", 20.0, 40.0, (25.0, 35.0))
        max_salinity = st.number_input("Salinidad Máx (µS/cm)", value=2500.0, step=100.0)
        
        st.subheader("Notas Agricultor")
        farmer_notes = st.text_area("Observaciones", placeholder="Ej: Veo hojas amarillas en la zona sur...")
        
        submitted = st.form_submit_button("🔄 GENERAR ESTRATEGIA", type="primary")

# --- LOGICA PRINCIPAL AL PULSAR BOTÓN ---
if submitted:
    # Contenedores para resultados
    tab_dashboard, tab_riego, tab_productos = st.tabs(["📊 Monitorización (Datos)", "💧 Recomendación Riego", "🧪 Plan Productos"])
    
    # Payload base
    user_context = {
        "crop": {"species": crop_species, "phenological_stage": crop_stage},
        "soil": {
            "target_vwc_profile_range": target_vwc,
            "max_acceptable_salinity_uScm": max_salinity
        }
    }
    
    payload_riego = {
        "context_overrides": user_context,
        "farmer_notes": farmer_notes
    }

    # ---------------------------------------------------------
    # 1. LLAMADA AGENTE RIEGO (Hydraulic Engineer)
    # ---------------------------------------------------------
    with st.spinner("🤖 Agente de Riego analizando sensores y calculando balance hídrico..."):
        try:
            r_irrigation = requests.post(IRRIGATION_URL, json=payload_riego, timeout=120)
            r_irrigation.raise_for_status()
            data_irrigation = r_irrigation.json()
            
            # Separar respuesta IA de datos crudos
            irrigation_reco = data_irrigation.get("agent_response", {})
            raw_data = data_irrigation.get("data_context", {})
            
        except Exception as e:
            st.error(f"Error fatal en Agente de Riego: {e}")
            st.stop()

    # ---------------------------------------------------------
    # 2. LLAMADA AGENTE PRODUCTOS (Agronomist)
    # ---------------------------------------------------------
    # Le pasamos lo que dijo el de riego + las notas
    payload_productos = {
        "context_overrides": user_context,
        "farmer_notes": farmer_notes,
        # INYECCIÓN CLAVE: El output del primero es input del segundo
        "irrigation_recommendation": irrigation_reco 
    }
    
    with st.spinner("💊 Agente de Productos consultando Vademécum y Fichas Técnicas..."):
        try:
            r_product = requests.post(PRODUCT_URL, json=payload_productos, timeout=120)
            r_product.raise_for_status()
            data_products = r_product.json()
        except Exception as e:
            st.warning(f"No se pudo conectar con el Agente de Productos: {e}")
            data_products = {}

    # ---------------------------------------------------------
    # PESTAÑA 1: DASHBOARD & DATOS (ÉPICA 2)
    # ---------------------------------------------------------
    with tab_dashboard:
        st.markdown("### 📡 Estado de los Sensores (Últimas 24h)")
        render_quality_indicator(raw_data)
        
        # Procesar Series Temporales
        df_ts = parse_timeseries_to_df(raw_data.get("recent_timeseries", {}))
        
        if not df_ts.empty:
            # Gráfica 1: Humedad de Suelo (VWC)
            cols_vwc = [c for c in df_ts.columns if "VWC" in c]
            if cols_vwc:
                st.markdown("#### 💧 Dinámica de Humedad de Suelo (%)")
                st.line_chart(df_ts[cols_vwc], height=300)
            
            # Gráfica 2: Clima (Temp/Humedad)
            col_graph1, col_graph2 = st.columns(2)
            with col_graph1:
                st.markdown("#### 🌡️ Temperatura Interna")
                if "T_in" in df_ts.columns:
                    st.line_chart(df_ts[["T_in"]], height=200, color="#FF4B4B")
            with col_graph2:
                st.markdown("#### ☀️ Radiación / Luz")
                if "RF" in df_ts.columns:
                    st.line_chart(df_ts[["RF"]], height=200, color="#FFA500")
        else:
            st.info("No hay datos de series temporales disponibles para visualizar.")

        st.divider()
        st.markdown("### 📈 Tendencias Diarias (Últimos 7 días)")
        daily_list = raw_data.get("daily_features", [])
        if daily_list:
            df_daily = pd.DataFrame(daily_list)
            if "fecha" in df_daily.columns:
                df_daily = df_daily.set_index("fecha")
            st.dataframe(df_daily, use_container_width=True)
        else:
            st.info("No hay features diarias disponibles.")

    # ---------------------------------------------------------
    # PESTAÑA 2: RECOMENDACIÓN RIEGO
    # ---------------------------------------------------------
    with tab_riego:
        reco = irrigation_reco.get("recommendation", {})
        expl = irrigation_reco.get("explanation", "Sin explicación")
        
        col_r1, col_r2 = st.columns([1, 2])
        with col_r1:
            st.markdown("#### 🚿 Decisión")
            do_irrigate = reco.get("apply_irrigation", False)
            if do_irrigate:
                st.success("APLICAR RIEGO")
            else:
                st.info("NO REGAR")
            
            st.metric("Volumen Sugerido", f"{reco.get('suggested_water_l_m2', 0)} L/m²")
            st.markdown(f"**Estrategia:** {reco.get('reason', '-')}")
            
        with col_r2:
            st.markdown("#### 📝 Justificación Técnica")
            st.info(expl)
        
        st.markdown("#### 🕒 Programación de Ciclos")
        cycles = reco.get("suggested_cycles", [])
        if cycles:
            st.table(pd.DataFrame(cycles))
        else:
            st.write("Sin ciclos definidos.")
            
        if reco.get("warnings"):
            st.warning("⚠️ **Alertas Hidráulicas:** " + "; ".join(reco["warnings"]))

    # ---------------------------------------------------------
    # PESTAÑA 3: PLAN DE PRODUCTOS
    # ---------------------------------------------------------
    with tab_productos:
        prod_plan = data_products.get("product_plan", [])
        advice = data_products.get("agronomic_advice", "")
        
        st.markdown("### 🧪 Estrategia de Nutrición y Bioestimulación")
        st.caption("Basado en Catálogo Atlántica Agrícola + Estado Hídrico")
        
        st.write(advice)
        
        if prod_plan:
            st.markdown("#### 📦 Canasta de Productos Recomendada")
            # Mostrar como tarjetas o tabla bonita
            for prod in prod_plan:
                with st.expander(f"🧴 **{prod.get('product_name')}** ({prod.get('dose')})", expanded=True):
                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        st.markdown(f"**Momento:** {prod.get('application_timing')}")
                    with col_p2:
                        st.markdown(f"**Objetivo:** {prod.get('reason')}")
        else:
            st.info("No se requieren productos específicos para esta jornada o el modelo no encontró coincidencias.")

else:
    st.info("👈 Configura los parámetros en la barra lateral y pulsa 'Generar Estrategia' para iniciar el análisis.")
