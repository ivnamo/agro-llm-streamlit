import streamlit as st
import requests
import pandas as pd
import json
import time
import os
import datetime
import traceback
from google.cloud import bigquery
from google.oauth2 import service_account

# ==========================
# CONFIGURACIÓN
# ==========================
st.set_page_config(page_title="Agro-IA: S4 Invernadero", page_icon="🌿", layout="wide")

# MOCKS
MOCK_IRRIGATION_DATA = {
    "agent_response": {
        "recommendation": {
            "apply_irrigation": True, "reason": "MOCK: Aumento hídrico", "suggested_water_l_m2": 5.5,
            "suggested_cycles": [{"start_time_local": "09:00", "duration_minutes": 20}],
        }, "explanation": "Respuesta simulada."
    }, "data_context": {"recent_timeseries": {"metrics": {}}, "daily_features": []}
}
MOCK_STRESS_DATA = {
    "agent_response": {
        "stress_alert": {
            "risk_level": "ALTO", "primary_risk": "Abiótico", "detailed_reason": "Simulación Mock."
        }, "recommendations": {"climate_control": "Ventilación", "sanitary_alert": "Vigilar"}
    }
}
MOCK_PRODUCT_DATA = {
    "product_plan": [{"product_name": "Producto Mock", "dose": "2 L/ha", "application_timing": "Ahora", "reason": "Test"}],
    "agronomic_advice": "Consejo simulado.",
    "audit_log": {"mock": True, "info": "Log simulado"}
}

IRRIGATION_URL = os.getenv("IRRIGATION_URL") or st.secrets.get("irrigation_url")
PRODUCT_URL = os.getenv("PRODUCT_URL") or st.secrets.get("product_url")
STRESS_URL = os.getenv("STRESS_URL") or st.secrets.get("stress_url")
PROJECT_ID = "tfg-agro-llm"
DATASET_ID = "agro_data"

# ⚠️ LA CLAVE DEL ÉXITO: FORZAR LA REGIÓN DE MADRID
BQ_LOCATION = "europe-southwest1" 

# Validacion simple de URL (puedes comentarla si solo usas mocks ahora mismo)
# if not IRRIGATION_URL: st.error("❌ Falta URL."); st.stop()

# ==========================
# LOGS
# ==========================
if "debug_logs" not in st.session_state: st.session_state.debug_logs = []

def add_log(msg, type="info"):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    st.session_state.debug_logs.append({"ts": ts, "msg": msg, "type": type})

# ==========================
# FUNCIONES BQ (CON REGIÓN MADRID)
# ==========================
def get_bq_client():
    # Intentar Secrets
    if "gcp_service_account" in st.secrets:
        try:
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"]
            )
            return bigquery.Client(credentials=creds, project=PROJECT_ID, location=BQ_LOCATION)
        except Exception as e:
            add_log(f"Error credenciales: {e}", "error")
            return None

    # Intentar Local
    try:
        return bigquery.Client(project=PROJECT_ID, location=BQ_LOCATION)
    except Exception as e:
        add_log(f"Error local: {e}", "error")
        return None

def save_feedback_to_bq(audit_log, rating, feedback_text, accepted):
    client = get_bq_client()
    if not client: return

    table_id = f"{PROJECT_ID}.{DATASET_ID}.recommendation_history"
    
    try:
        # Sanitizar y convertir a String para evitar error "Not a record"
        audit_clean = json.loads(json.dumps(audit_log, default=str))
        audit_str = json.dumps(audit_clean)

        row = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "location_id": 8507,
            "rating": rating,
            "user_feedback": feedback_text,
            "accepted": accepted,
            "full_audit_log": audit_str # String JSON
        }
        
        errors = client.insert_rows_json(table_id, [row])
        
        if errors == []:
            add_log("✅ Guardado OK en BigQuery.", "success")
            st.toast("Guardado OK", icon="🎉")
        else:
            add_log(f"❌ Error BigQuery: {errors}", "error")
            st.error(f"Error guardando: {errors}")

    except Exception as e:
        add_log(f"💥 Error Python: {e}", "error")
        st.error(f"Excepción Python al guardar: {e}")

def load_history_from_bq(selected_date=None):
    client = get_bq_client()
    if not client: 
        st.error("No se pudo iniciar el cliente BigQuery.")
        return None
    
    where = f"WHERE DATE(timestamp) = '{selected_date.strftime('%Y-%m-%d')}'" if selected_date else ""
    
    # Query explicita
    q = f"""
        SELECT timestamp, rating, user_feedback, full_audit_log, accepted 
        FROM `{PROJECT_ID}.{DATASET_ID}.recommendation_history` 
        {where} 
        ORDER BY timestamp DESC LIMIT 20
    """
    
    try:
        # Intentamos leer. Si falta db-dtypes, aquí explotará
        df = client.query(q).to_dataframe()
        return df
        
    except Exception as e:
        # ESTO ES LO NUEVO: Te muestra el error en la cara
        error_msg = str(e)
        st.error(f"🚨 ERROR CRÍTICO LEYENDO BQ: {error_msg}")
        
        if "db-dtypes" in error_msg:
            st.warning("💡 SOLUCIÓN: Añade 'db-dtypes' a tu requirements.txt en GitHub y espera al redeploy.")
            
        add_log(f"Error leyendo historial: {e}", "error")
        return None # Retornamos None para saber que falló

# ==========================
# UI
# ==========================
st.title("🌿 Sistema Integral (S4)")

with st.sidebar:
    st.header("📋 Configuración")
    with st.form("params"):
        submitted = st.form_submit_button("🔄 EJECUTAR ANÁLISIS")
    use_mock = st.toggle("Usar Mocks", True)
    
    st.divider()
    with st.expander("🛠️ Logs"):
        if st.button("Limpiar"): st.session_state.debug_logs = []
        for l in st.session_state.debug_logs:
            st.text(f"[{l['ts']}] {l['msg']}")

if "results" not in st.session_state: st.session_state.results = None

if submitted:
    if use_mock:
        st.session_state.results = {
            "irrigation": MOCK_IRRIGATION_DATA,
            "product": MOCK_PRODUCT_DATA,
            "audit": MOCK_PRODUCT_DATA["audit_log"]
        }
        add_log("Mock generado.", "info")

tab_plan, tab_hist = st.tabs(["🧪 Plan & Feedback", "📜 Historial"])

with tab_plan:
    if st.session_state.results:
        res = st.session_state.results
        st.info("Plan generado (Mock/Real).")
        
        st.divider()
        st.subheader("⭐ Tu Opinión")
        with st.form("fb"):
            c1, c2 = st.columns(2)
            rating = c1.slider("Nota", 1, 5, 5)
            accepted = c1.checkbox("Aceptar", True)
            txt = c2.text_area("Comentarios", "Funciona region madrid")
            
            if st.form_submit_button("💾 Guardar"):
                save_feedback_to_bq(res["audit"], rating, txt, accepted)

with tab_hist:
    st.write("Pulsa para ver las últimas 20 entradas:")
    if st.button("🔄 Refrescar Historial"):
        df = load_history_from_bq() # Leemos sin filtro de fecha para traer TODO
        
        if df is None:
            st.stop() # Se detiene aquí si hubo error técnico (ya mostrado arriba en rojo)
            
        if not df.empty:
            st.success(f"Se encontraron {len(df)} registros.")
            for i, r in df.iterrows():
                stars = "⭐" * int(r['rating']) if pd.notnull(r['rating']) else "-"
                status = "✅" if r['accepted'] else "❌"
                ts_str = str(r['timestamp'])
                
                with st.expander(f"{ts_str} | {stars} | {status}"):
                    st.write(f"**Feedback:** {r['user_feedback']}")
                    
                    # Parseo seguro del JSON
                    log_data = r['full_audit_log']
                    if isinstance(log_data, str):
                        try: log_data = json.loads(log_data)
                        except: pass
                    
                    st.json(log_data)
        else:
            st.warning("📭 La consulta funcionó correctamente, pero la tabla está vacía.")
