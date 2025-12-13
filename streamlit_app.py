import streamlit as st
import requests
import pandas as pd
import json
import time
import os

# ==========================
# 0. DATOS MOCK (LOREM IPSUM)
# ==========================
# Estos diccionarios imitan la estructura real para probar la UI sin gastar tokens.

MOCK_IRRIGATION_DATA = {
    "agent_response": {
        "recommendation": {
            "apply_irrigation": True,
            "reason": "increase (MOCK)",
            "suggested_water_l_m2": 5.5,
            "suggested_cycles": [
                {"start_time_local": "2025-12-14T09:00:00", "duration_minutes": 20, "comment": "Ciclo Simulado 1"},
                {"start_time_local": "2025-12-14T15:00:00", "duration_minutes": 15, "comment": "Ciclo Simulado 2"}
            ],
            "warnings": ["[MOCK] Esto es una alerta simulada de prueba."],
        },
        "explanation": "Respuesta simulada (LOREM IPSUM). El agente de riego ha determinado que faltan datos reales, así que se inventa este texto para que compruebes que la interfaz se renderiza bien sin llamar a Gemini."
    },
    "data_context": {
        "recent_timeseries": {"metrics": {}}, # Vacío para no romper gráficas
        "daily_features": []
    }
}

MOCK_STRESS_DATA = {
    "agent_response": {
        "stress_alert": {
            "risk_level": "ALTO (MOCK)",
            "primary_risk": "Abiótico (Simulación)",
            "detailed_reason": "Se simula un riesgo alto de Lorem Ipsum debido a condiciones de Dolor Sit Amet en la atmósfera."
        },
        "recommendations": {
            "climate_control": "Activar ventilación simulada al 100%.",
            "sanitary_alert": "Vigilar vectores de prueba en el sector 7G."
        }
    }
}

MOCK_PRODUCT_DATA = {
    "product_plan": [
        {
            "product_name": "Producto Mock A",
            "dose": "2 L/ha",
            "application_timing": "Inmediato",
            "reason": "Para tratar el déficit de Lorem Ipsum detectado."
        },
        {
            "product_name": "Producto Mock B",
            "dose": "300 cc/100L",
            "application_timing": "Foliar",
            "reason": "Refuerzo preventivo de UI Testing."
        }
    ],
    "agronomic_advice": "Estrategia agronómica simulada. No se ha realizado ninguna inferencia real. Todo parece correcto en la simulación."
}

# ==========================
# CONFIGURACIÓN
# ==========================
st.set_page_config(page_title="Agro-IA: S4 Invernadero", page_icon="🌿", layout="wide")

# URLs
IRRIGATION_URL = os.getenv("IRRIGATION_URL") or st.secrets.get("irrigation_url")
PRODUCT_URL = os.getenv("PRODUCT_URL") or st.secrets.get("product_url")
STRESS_URL = os.getenv("STRESS_URL") or st.secrets.get("stress_url")

if not IRRIGATION_URL:
    st.error("❌ Falta configurar las URLs de los servicios.")
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
        if not values: continue
        df_m = pd.DataFrame(values)
        if "ts_utc" in df_m.columns:
            df_m["ts_utc"] = pd.to_datetime(df_m["ts_utc"])
            df_m = df_m.rename(columns={"value": metric_name})
            df_m = df_m.set_index("ts_utc")
            dfs.append(df_m)
    if not dfs: return pd.DataFrame()
    return pd.concat(dfs, axis=1).sort_index()

def render_quality_indicator(data_context):
    ts = data_context.get("recent_timeseries", {}).get("metrics", {})
    daily = data_context.get("daily_features", [])
    
    col1, col2, col3 = st.columns(3)
    has_data = any(len(v) > 0 for v in ts.values())
    
    with col1:
        if has_data: st.success("📡 Sensores Online")
        else: st.warning("📡 Sin datos (Mock/Offline)")
            
    with col2:
        if len(daily) >= 5: st.success(f"📅 Histórico: {len(daily)} días")
        else: st.warning(f"📅 Histórico parcial ({len(daily)} días)")

    with col3:
        st.info("⏱️ Latencia: < 5min")

# ==========================
# INTERFAZ PRINCIPAL
# ==========================
st.title("🌿 Sistema Integral de Gestión Agrícola (S4)")
st.markdown("Orquestación Multi-Agente: **Hidráulica** + **Fisiología** + **Agronomía**")

with st.sidebar:
    st.header("📋 Configuración")
    with st.form("params_form"):
        st.subheader("Cultivo")
        crop_species = st.selectbox("Especie", ["tomate", "pimiento", "pepino"], index=0)
        crop_stage = st.selectbox("Fase", ["trasplante", "crecimiento", "floracion", "cuajado_y_engorde", "maduracion"], index=3)
        
        st.subheader("Notas Agricultor")
        farmer_notes = st.text_area("Observaciones", placeholder="Ej: Veo hojas amarillas, posible oídio...")
        
        submitted = st.form_submit_button("🔄 EJECUTAR ANÁLISIS", type="primary")
    
    st.divider()
    st.markdown("### 🛠️ Modo Desarrollo (Tokens)")
    st.caption("Desactiva para usar datos 'fake' y no gastar dinero.")
    use_real_irrigation = st.toggle("Activar Agente Riego", value=True)
    use_real_stress = st.toggle("Activar Agente Estrés", value=True)
    use_real_products = st.toggle("Activar Agente Productos", value=True)

if submitted:
    tab_dashboard, tab_riego, tab_estres, tab_productos = st.tabs([
        "📊 Monitorización", 
        "💧 Riego (Hidráulica)", 
        "🌡️ Estrés (Fisiología)", 
        "🧪 Plan (Agronomía)"
    ])
    
    user_context = {
        "crop": {"species": crop_species, "phenological_stage": crop_stage}
    }
    
    payload_base = {
        "context_overrides": user_context,
        "farmer_notes": farmer_notes
    }

    irrigation_resp = {}
    stress_resp = {}
    product_resp = {}
    raw_data_riego = {}
    
    with st.status("🤖 Coordinando Agentes Inteligentes...", expanded=True) as status:
        
        # --- 1. AGENTE DE RIEGO ---
        status.write("💧 Contactando Agente Hidráulico...")
        if use_real_irrigation:
            try:
                r_irr = requests.post(IRRIGATION_URL, json=payload_base, timeout=60)
                r_irr.raise_for_status()
                data_irr = r_irr.json()
                irrigation_resp = data_irr.get("agent_response", {})
                raw_data_riego = data_irr.get("data_context", {})
                status.write("✅ Riego (REAL) completado.")
            except Exception as e:
                st.error(f"Fallo en Agente Riego: {e}")
        else:
            time.sleep(1) # Simular latencia
            irrigation_resp = MOCK_IRRIGATION_DATA["agent_response"]
            raw_data_riego = MOCK_IRRIGATION_DATA["data_context"]
            status.write("⚠️ Riego (MOCK) cargado.")

        # --- 2. AGENTE DE ESTRÉS ---
        status.write("🌡️ Contactando Agente Fisiólogo...")
        if use_real_stress:
            try:
                r_str = requests.post(STRESS_URL, json=payload_base, timeout=60)
                r_str.raise_for_status()
                data_str = r_str.json()
                stress_resp = data_str.get("agent_response", {})
                status.write("✅ Estrés (REAL) completado.")
            except Exception as e:
                st.warning(f"Agente Estrés no disponible: {e}")
        else:
            time.sleep(1)
            stress_resp = MOCK_STRESS_DATA["agent_response"]
            status.write("⚠️ Estrés (MOCK) cargado.")

        # --- 3. AGENTE DE PRODUCTOS ---
        status.write("🧪 Contactando Agente Agrónomo...")
        if use_real_products:
            payload_prod = {
                **payload_base,
                "irrigation_recommendation": irrigation_resp,
                "stress_alert": stress_resp
            }
            try:
                r_prod = requests.post(PRODUCT_URL, json=payload_prod, timeout=90)
                r_prod.raise_for_status()
                product_resp = r_prod.json()
                status.write("✅ Plan (REAL) generado.")
            except Exception as e:
                st.warning(f"Agente Productos no disponible: {e}")
        else:
            time.sleep(1.5)
            product_resp = MOCK_PRODUCT_DATA
            status.write("⚠️ Plan (MOCK) cargado.")
            
        status.update(label="¡Estrategia Generada!", state="complete", expanded=False)

    # --- PESTAÑA 1: DASHBOARD ---
    with tab_dashboard:
        st.markdown("### 📡 Estado de los Sensores")
        render_quality_indicator(raw_data_riego) # Funciona aunque venga vacío del Mock
        
        if raw_data_riego and raw_data_riego.get("recent_timeseries", {}).get("metrics"):
            df_ts = parse_timeseries_to_df(raw_data_riego.get("recent_timeseries", {}))
            if not df_ts.empty:
                cols_vwc = [c for c in df_ts.columns if "VWC" in c]
                if cols_vwc: st.line_chart(df_ts[cols_vwc], height=250)
                
                c1, c2 = st.columns(2)
                if "T_in" in df_ts.columns: c1.line_chart(df_ts[["T_in"]], height=200, color="#FF4B4B")
                if "RF" in df_ts.columns: c2.line_chart(df_ts[["RF"]], height=200, color="#FFA500")
        else:
            if not use_real_irrigation:
                st.info("ℹ️ En modo MOCK no se cargan datos reales de sensores para ahorrar lecturas a BigQuery.")
            else:
                st.warning("Sin datos de sensores.")

    # --- PESTAÑA 2: RIEGO ---
    with tab_riego:
        reco = irrigation_resp.get("recommendation")
        expl = irrigation_resp.get("explanation", "Sin respuesta.")
        
        if reco:
            col_r1, col_r2 = st.columns([1, 2])
            with col_r1:
                do_irrigate = reco.get("apply_irrigation", False)
                if do_irrigate: st.success(f"🚿 APLICAR RIEGO: {reco.get('reason','-')}")
                else: st.info("⏸️ NO REGAR")
                st.metric("Volumen", f"{reco.get('suggested_water_l_m2', 0)} L/m²")
            
            with col_r2:
                st.info(f"**Razonamiento:** {expl}")
                
            cycles = reco.get("suggested_cycles", [])
            if cycles: st.table(pd.DataFrame(cycles))
            
            for w in reco.get("warnings", []): st.warning(f"⚠️ {w}")
        else:
            st.error("Sin recomendación válida.")

    # --- PESTAÑA 3: ESTRÉS ---
    with tab_estres:
        alert = stress_resp.get("stress_alert", {})
        recs = stress_resp.get("recommendations", {})
        
        if alert:
            risk_level = alert.get("risk_level", "DESCONOCIDO")
            # Lógica simple de colores
            color = "red" if "ALTO" in risk_level else "orange" if "MEDIO" in risk_level else "green"
            
            st.markdown(f"### Riesgo Detectado: :{color}[{risk_level}]")
            st.markdown(f"**Factor Principal:** {alert.get('primary_risk', '-')}")
            st.info(alert.get("detailed_reason", ""))
            
            st.divider()
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### 🌬️ Manejo de Clima")
                st.write(recs.get("climate_control", "-"))
            with c2:
                st.markdown("#### 🦠 Alerta Sanitaria")
                st.write(recs.get("sanitary_alert", "-"))
        else:
            st.info("Sin alertas de estrés generadas.")

# --- PESTAÑA 4: PRODUCTOS ---
    with tab_productos:
        prod_plan = product_resp.get("product_plan", [])
        advice = product_resp.get("agronomic_advice", "")
        audit_data = product_resp.get("audit_log", None) # Recuperamos el log
        
        st.markdown("### 🧪 Estrategia Agronómica")
        st.write(advice)
        
        if prod_plan:
            for prod in prod_plan:
                with st.expander(f"🧴 **{prod.get('product_name')}**", expanded=True):
                    st.write(f"**Dosis:** {prod.get('dose')}")
                    st.write(f"**Momento:** {prod.get('application_timing')}")
                    st.caption(f"**Objetivo:** {prod.get('reason')}")
        else:
            st.info("No se recomiendan productos adicionales.")
            
        # --- ZONA DE AUDITORÍA (Descarga + Visualización + Copia) ---
        if audit_data:
            st.divider()
            st.caption("📂 Zona de Auditoría y Trazabilidad")
            
            # Convertimos el dict a JSON string bonito
            json_str = json.dumps(audit_data, indent=2, ensure_ascii=False)
            file_name = f"informe_tecnico_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.json"
            
            # 1. Botón de Descarga
            st.download_button(
                label="📥 Descargar Informe (JSON)",
                data=json_str,
                file_name=file_name,
                mime="application/json",
                help="Descarga el fichero completo para validación agronómica."
            )
            
            # 2. Desplegable con visualización y botón de COPIAR
            with st.expander("👁️ Ver y Copiar Informe Técnico Completo"):
                # st.code muestra el texto y añade automáticamente el icono de copiar 📋
                st.code(json_str, language="json")
else:
    st.info("👈 Pulsa 'Ejecutar Análisis' para comenzar.")
