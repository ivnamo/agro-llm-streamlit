import streamlit as st
import requests
import pandas as pd
import json
import os

# ==========================
# CONFIGURACIÓN
# ==========================
st.set_page_config(page_title="Agro-IA: Riego y Manejo", page_icon="🌿", layout="wide")

# Intenta leer de variables de entorno (Cloud Run), si no, busca en st.secrets (Local)
IRRIGATION_URL = os.getenv("IRRIGATION_URL") or st.secrets.get("irrigation_url")
PRODUCT_URL = os.getenv("PRODUCT_URL") or st.secrets.get("product_url")

if not IRRIGATION_URL or "URL_DE_TU" in IRRIGATION_URL:
    st.error("❌ Falta configurar la URL del Agente de Riego (IRRIGATION_URL)")
    st.stop()

# ==========================
# FUNCIONES AUXILIARES
# ==========================

def parse_timeseries_to_df(ts_data):
    if not ts_data or "metrics" not in ts_data:
        return pd.DataFrame()
    
    metrics = ts_data["metrics"]
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
        
    return pd.concat(dfs, axis=1).sort_index()

def render_quality_indicator(data_context):
    ts = data_context.get("recent_timeseries", {}).get("metrics", {})
    daily = data_context.get("daily_features", [])
    
    col1, col2, col3 = st.columns(3)
    
    has_data = any(len(v) > 0 for v in ts.values())
    with col1:
        if has_data:
            st.success("📡 Sensores Online")
        else:
            st.error("📡 Sin conexión Sensores")
            
    days_count = len(daily)
    with col2:
        if days_count >= 5:
            st.success(f"📅 Histórico: {days_count} días")
        elif days_count > 0:
            st.warning(f"📅 Histórico parcial ({days_count} días)")
        else:
            st.error("📅 Sin histórico diario")

    with col3:
        st.info("⏱️ Latencia: < 5min")

# ==========================
# INTERFAZ PRINCIPAL
# ==========================

st.title("🌿 Sistema Integral de Gestión Agrícola (S4)")
st.markdown("Orquestación de Agentes: **Ingeniería Hidráulica** + **Manejo de Productos**")

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

if submitted:
    tab_dashboard, tab_riego, tab_productos = st.tabs(["📊 Monitorización (Datos)", "💧 Recomendación Riego", "🧪 Plan Productos"])
    
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

    # --- LLAMADA RIEGO ---
    irrigation_reco = {}
    raw_data = {}
    
    with st.spinner("🤖 Agente de Riego analizando sensores..."):
        try:
            r_irrigation = requests.post(IRRIGATION_URL, json=payload_riego, timeout=120)
            r_irrigation.raise_for_status()
            data_irrigation = r_irrigation.json()
            
            irrigation_reco = data_irrigation.get("agent_response", {}) or {} # <--- Aseguramos dict
            raw_data = data_irrigation.get("data_context", {}) or {}
            
        except Exception as e:
            st.error(f"Error conectando con Agente de Riego: {e}")
            # No detenemos la ejecución para intentar mostrar al menos los datos parciales
            irrigation_reco = {"explanation": f"Fallo de conexión: {e}"}

    # --- LLAMADA PRODUCTOS ---
    payload_productos = {
        "context_overrides": user_context,
        "farmer_notes": farmer_notes,
        "irrigation_recommendation": irrigation_reco 
    }
    
    data_products = {}
    with st.spinner("💊 Agente de Productos consultando Vademécum..."):
        try:
            r_product = requests.post(PRODUCT_URL, json=payload_productos, timeout=120)
            r_product.raise_for_status()
            data_products = r_product.json()
        except Exception as e:
            st.warning(f"Agente de Productos no disponible: {e}")

    # --- PESTAÑA 1: DASHBOARD ---
    with tab_dashboard:
        st.markdown("### 📡 Estado de los Sensores")
        render_quality_indicator(raw_data)
        
        df_ts = parse_timeseries_to_df(raw_data.get("recent_timeseries", {}))
        
        if not df_ts.empty:
            cols_vwc = [c for c in df_ts.columns if "VWC" in c]
            if cols_vwc:
                st.markdown("#### 💧 Humedad de Suelo (%)")
                st.line_chart(df_ts[cols_vwc], height=300)
            
            col_graph1, col_graph2 = st.columns(2)
            with col_graph1:
                st.markdown("#### 🌡️ Temperatura Interna")
                if "T_in" in df_ts.columns:
                    st.line_chart(df_ts[["T_in"]], height=200, color="#FF4B4B")
            with col_graph2:
                st.markdown("#### ☀️ Radiación")
                if "RF" in df_ts.columns:
                    st.line_chart(df_ts[["RF"]], height=200, color="#FFA500")
        else:
            st.info("Sin datos recientes de sensores.")

        st.divider()
        st.markdown("### 📈 Tendencias Diarias")
        daily_list = raw_data.get("daily_features", [])
        if daily_list:
            df_daily = pd.DataFrame(daily_list)
            if "fecha" in df_daily.columns:
                df_daily = df_daily.set_index("fecha")
            
            # <--- CAMBIO: Solución error use_container_width
            # Usamos una configuración compatible o simplemente .dataframe(df) sin argumentos extraños
            try:
                st.dataframe(df_daily, use_container_width=True)
            except:
                # Fallback por si la versión de streamlit se queja
                st.dataframe(df_daily) 
        else:
            st.info("No hay features diarias disponibles.")

    # --- PESTAÑA 2: RIEGO ---
    with tab_riego:
        # <--- CAMBIO CRÍTICO: Protección contra None
        # Si recommendation es None, asignamos un dict vacío {}
        reco = irrigation_reco.get("recommendation") or {} 
        expl = irrigation_reco.get("explanation", "Sin explicación disponible.")
        
        if not reco:
            st.error("⚠️ El Agente de Riego no pudo generar una recomendación válida (posible error del modelo).")
            st.write("**Detalle del error:**", expl)
        else:
            col_r1, col_r2 = st.columns([1, 2])
            with col_r1:
                st.markdown("#### 🚿 Decisión")
                # Ahora es seguro llamar a .get()
                do_irrigate = reco.get("apply_irrigation", False)
                
                if do_irrigate:
                    st.success("APLICAR RIEGO")
                else:
                    st.info("NO REGAR")
                
                st.metric("Volumen", f"{reco.get('suggested_water_l_m2', 0)} L/m²")
                st.markdown(f"**Estrategia:** {reco.get('reason', '-')}")
                
            with col_r2:
                st.markdown("#### 📝 Justificación")
                st.info(expl)
            
            st.markdown("#### 🕒 Ciclos")
            cycles = reco.get("suggested_cycles", [])
            if cycles:
                st.table(pd.DataFrame(cycles))
            else:
                st.caption("Sin ciclos específicos.")
                
            if reco.get("warnings"):
                for w in reco["warnings"]:
                    st.warning(f"⚠️ {w}")

    # --- PESTAÑA 3: PRODUCTOS ---
    with tab_productos:
        prod_plan = data_products.get("product_plan", [])
        advice = data_products.get("agronomic_advice", "")
        
        st.markdown("### 🧪 Estrategia de Nutrición")
        st.write(advice)
        
        if prod_plan:
            for prod in prod_plan:
                with st.expander(f"🧴 **{prod.get('product_name')}**", expanded=True):
                    st.write(f"**Dosis:** {prod.get('dose')}")
                    st.write(f"**Momento:** {prod.get('application_timing')}")
                    st.caption(f"**Objetivo:** {prod.get('reason')}")
        else:
            st.info("No hay productos recomendados.")

else:
    st.info("👈 Pulsa 'Generar Estrategia' para comenzar.")
