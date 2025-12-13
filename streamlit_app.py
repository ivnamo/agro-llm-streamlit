import streamlit as st
import requests
import pandas as pd
import json
import time
import os
import datetime
from google.cloud import bigquery

# ==========================
# 0. DATOS MOCK (LOREM IPSUM)
# ==========================
MOCK_IRRIGATION_DATA = {
    "agent_response": {
        "recommendation": {
            "apply_irrigation": True,
            "reason": "increase (MOCK)",
            "suggested_water_l_m2": 5.5,
            "suggested_cycles": [{"start_time_local": "2025-12-14T09:00:00", "duration_minutes": 20, "comment": "Ciclo Simulado 1"}],
            "warnings": ["[MOCK] Alerta simulada."],
        },
        "explanation": "Respuesta simulada (LOREM IPSUM). Interfaz renderizada sin llamar a Gemini."
    },
    "data_context": {"recent_timeseries": {"metrics": {}}, "daily_features": []}
}

MOCK_STRESS_DATA = {
    "agent_response": {
        "stress_alert": {
            "risk_level": "ALTO (MOCK)",
            "primary_risk": "Abiótico (Simulación)",
            "detailed_reason": "Riesgo simulado de Lorem Ipsum por condiciones de Dolor Sit Amet."
        },
        "recommendations": {"climate_control": "Ventilación simulada 100%.", "sanitary_alert": "Vigilar vectores test."}
    }
}

MOCK_PRODUCT_DATA = {
    "product_plan": [{"product_name": "Producto Mock A", "dose": "2 L/ha", "application_timing": "Inmediato", "reason": "Tratar déficit Mock."}],
    "agronomic_advice": "Estrategia simulada. Sin inferencia real.",
    "audit_log": {"mock": True, "info": "Log de auditoría simulado"}
}

# ==========================
# CONFIGURACIÓN
# ==========================
st.set_page_config(page_title="Agro-IA: S4 Invernadero", page_icon="🌿", layout="wide")

IRRIGATION_URL = os.getenv("IRRIGATION_URL") or st.secrets.get("irrigation_url")
PRODUCT_URL = os.getenv("PRODUCT_URL") or st.secrets.get("product_url")
STRESS_URL = os.getenv("STRESS_URL") or st.secrets.get("stress_url")
PROJECT_ID = "tfg-agro-llm"
DATASET_ID = "agro_data"

if not IRRIGATION_URL:
    st.error("❌ Falta configuración de URLs.")
    st.stop()

# ==========================
# FUNCIONES BACKEND (BQ)
# ==========================
def save_feedback_to_bq(audit_log, rating, feedback_text, accepted):
    client = bigquery.Client(project=PROJECT_ID)
    table_id = f"{PROJECT_ID}.{DATASET_ID}.recommendation_history"
    row = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "location_id": 8507,
        "rating": rating,
        "user_feedback": feedback_text,
        "accepted": accepted,
        "full_audit_log": json.dumps(audit_log)
    }
    errors = client.insert_rows_json(table_id, [row])
    if errors: st.error(f"Error BQ: {errors}")
    else: st.success("✅ Guardado en historial.")

def load_history_from_bq(limit=10):
    client = bigquery.Client(project=PROJECT_ID)
    q = f"SELECT timestamp, rating, user_feedback, full_audit_log FROM `{PROJECT_ID}.{DATASET_ID}.recommendation_history` ORDER BY timestamp DESC LIMIT {limit}"
    return client.query(q).to_dataframe()

# ==========================
# HELPERS
# ==========================
def parse_timeseries_to_df(ts_data):
    if not ts_data or "metrics" not in ts_data: return pd.DataFrame()
    dfs = []
    for m, vals in ts_data["metrics"].items():
        if not vals: continue
        df = pd.DataFrame(vals)
        if "ts_utc" in df.columns:
            df["ts_utc"] = pd.to_datetime(df["ts_utc"])
            df = df.rename(columns={"value": m}).set_index("ts_utc")
            dfs.append(df)
    return pd.concat(dfs, axis=1).sort_index() if dfs else pd.DataFrame()

def render_quality_indicator(data_context):
    ts = data_context.get("recent_timeseries", {}).get("metrics", {})
    daily = data_context.get("daily_features", [])
    c1, c2, c3 = st.columns(3)
    with c1: st.success("📡 Sensores Online") if any(len(v)>0 for v in ts.values()) else st.warning("📡 Sin datos")
    with c2: st.success(f"📅 Histórico: {len(daily)} días") if len(daily)>=5 else st.warning(f"📅 Histórico: {len(daily)} días")
    with c3: st.info("⏱️ Latencia: < 5min")

# ==========================
# UI PRINCIPAL
# ==========================
st.title("🌿 Sistema Integral de Gestión Agrícola (S4)")

with st.sidebar:
    st.header("📋 Configuración")
    with st.form("params"):
        crop = st.selectbox("Especie", ["tomate", "pimiento", "pepino"])
        stage = st.selectbox("Fase", ["cuajado_y_engorde", "maduracion", "crecimiento"])
        notes = st.text_area("Observaciones", placeholder="Ej: Veo hojas amarillas...")
        submitted = st.form_submit_button("🔄 EJECUTAR ANÁLISIS", type="primary")
    
    st.divider()
    st.caption("🛠️ Modo Desarrollo")
    use_irr = st.toggle("Agente Riego", True)
    use_str = st.toggle("Agente Estrés", True)
    use_prod = st.toggle("Agente Productos", True)

# Estado persistente para feedback
if "audit_cache" not in st.session_state: st.session_state.audit_cache = None

tab_dash, tab_riego, tab_estres, tab_prod, tab_hist = st.tabs(["📊 Monitor", "💧 Riego", "🌡️ Estrés", "🧪 Plan & Feedback", "📜 Historial"])

if submitted:
    ctx = {"crop": {"species": crop, "phenological_stage": stage}}
    base = {"context_overrides": ctx, "farmer_notes": notes}
    
    irr_resp, str_resp, prod_resp, raw_riego = {}, {}, {}, {}

    with st.status("🤖 Coordinando Agentes...", expanded=True) as s:
        # 1. Riego
        s.write("💧 Riego...")
        if use_irr:
            try:
                r = requests.post(IRRIGATION_URL, json=base, timeout=60)
                d = r.json()
                irr_resp, raw_riego = d.get("agent_response", {}), d.get("data_context", {})
                s.write("✅ Riego OK")
            except Exception as e: st.error(f"Error Riego: {e}")
        else:
            time.sleep(0.5); irr_resp, raw_riego = MOCK_IRRIGATION_DATA["agent_response"], MOCK_IRRIGATION_DATA["data_context"]; s.write("⚠️ Riego Mock")

        # 2. Estrés
        s.write("🌡️ Estrés...")
        if use_str:
            try:
                r = requests.post(STRESS_URL, json=base, timeout=60)
                str_resp = r.json().get("agent_response", {})
                s.write("✅ Estrés OK")
            except Exception as e: st.warning(f"Error Estrés: {e}")
        else:
            time.sleep(0.5); str_resp = MOCK_STRESS_DATA["agent_response"]; s.write("⚠️ Estrés Mock")

        # 3. Productos (Síntesis)
        s.write("🧪 Productos...")
        if use_prod:
            pl = {**base, "irrigation_recommendation": irr_resp, "stress_alert": str_resp}
            try:
                r = requests.post(PRODUCT_URL, json=pl, timeout=90)
                prod_resp = r.json()
                s.write("✅ Plan OK")
            except Exception as e: st.warning(f"Error Prod: {e}")
        else:
            time.sleep(0.5); prod_resp = MOCK_PRODUCT_DATA; s.write("⚠️ Prod Mock")
        
        s.update(label="¡Completado!", state="complete", expanded=False)
        st.session_state.audit_cache = prod_resp.get("audit_log", {})

    # --- PESTAÑA 1: DASHBOARD ---
    with tab_dash:
        render_quality_indicator(raw_riego)
        df = parse_timeseries_to_df(raw_riego.get("recent_timeseries", {}))
        if not df.empty:
            if [c for c in df.columns if "VWC" in c]: st.line_chart(df[[c for c in df.columns if "VWC" in c]], height=250)
            c1, c2 = st.columns(2)
            if "T_in" in df.columns: c1.line_chart(df[["T_in"]], height=200, color="#FF4B4B")
            if "RF" in df.columns: c2.line_chart(df[["RF"]], height=200, color="#FFA500")
        else: st.info("Sin datos sensores.")

    # --- PESTAÑA 2: RIEGO ---
    with tab_riego:
        rec = irr_resp.get("recommendation", {})
        if rec:
            c1, c2 = st.columns([1, 2])
            with c1:
                st.success(f"🚿 RIEGO: {rec.get('reason')}") if rec.get("apply_irrigation") else st.info("⏸️ NO REGAR")
                st.metric("Volumen", f"{rec.get('suggested_water_l_m2', 0)} L/m²")
            with c2: st.info(irr_resp.get("explanation", "-"))
            if rec.get("suggested_cycles"): st.table(rec["suggested_cycles"])
            for w in rec.get("warnings", []): st.warning(w)
        else: st.error("Sin datos Riego.")

    # --- PESTAÑA 3: ESTRÉS ---
    with tab_estres:
        alert = str_resp.get("stress_alert", {})
        if alert:
            rl = alert.get("risk_level", "?")
            col = "red" if "ALTO" in rl else "orange" if "MEDIO" in rl else "green"
            st.markdown(f"### Riesgo: :{col}[{rl}] ({alert.get('primary_risk')})")
            st.info(alert.get("detailed_reason"))
            c1, c2 = st.columns(2)
            c1.markdown("**🌬️ Clima**"); c1.write(str_resp.get("recommendations", {}).get("climate_control"))
            c2.markdown("**🦠 Sanidad**"); c2.write(str_resp.get("recommendations", {}).get("sanitary_alert"))
        else: st.info("Sin alertas.")

    # --- PESTAÑA 4: PRODUCTOS & FEEDBACK ---
    with tab_prod:
        plan = prod_resp.get("product_plan", [])
        st.markdown("### 🧪 Estrategia")
        st.write(prod_resp.get("agronomic_advice", ""))
        for p in plan:
            with st.expander(f"🧴 {p.get('product_name')}", expanded=True):
                st.write(f"**Dosis:** {p.get('dose')} | **Momento:** {p.get('application_timing')}")
                st.caption(p.get('reason'))
        
        if st.session_state.audit_cache:
            st.divider()
            st.caption("📂 Auditoría")
            js = json.dumps(st.session_state.audit_cache, indent=2, ensure_ascii=False)
            st.download_button("📥 Descargar JSON", js, "informe.json", "application/json")
            with st.expander("👁️ Ver JSON Técnico"): st.code(js, language="json")
            
            st.divider()
            st.markdown("### ⭐ Valoración")
            with st.form("fb"):
                c1, c2 = st.columns(2)
                rat = c1.slider("Nota", 1, 5, 3)
                acc = c1.checkbox("Aceptado", True)
                txt = c2.text_area("Comentarios")
                if st.form_submit_button("💾 Guardar"):
                    save_feedback_to_bq(st.session_state.audit_cache, rat, txt, acc)

# --- PESTAÑA 5: HISTORIAL ---
with tab_hist:
    if st.button("🔄 Actualizar"):
        df = load_history_from_bq()
        if not df.empty:
            for i, r in df.iterrows():
                with st.expander(f"{r['timestamp']} - ⭐ {r['rating']}"):
                    st.write(f"**Feedback:** {r['user_feedback']}")
                    log = json.loads(r['full_audit_log']) if r['full_audit_log'] else {}
                    st.table(pd.DataFrame(log.get("ai_reasoning_output", {}).get("product_plan", [])))
                    if st.checkbox("JSON Completo", key=f"h_{i}"): st.json(log)
        else: st.warning("Historial vacío.")
