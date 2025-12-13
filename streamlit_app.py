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
# 0. CONFIGURACIÓN Y MOCKS
# ==========================
st.set_page_config(page_title="Agro-IA: S4 Invernadero", page_icon="🌿", layout="wide")

# DATOS MOCK
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

# Variables de entorno
IRRIGATION_URL = os.getenv("IRRIGATION_URL") or st.secrets.get("irrigation_url")
PRODUCT_URL = os.getenv("PRODUCT_URL") or st.secrets.get("product_url")
STRESS_URL = os.getenv("STRESS_URL") or st.secrets.get("stress_url")
PROJECT_ID = "tfg-agro-llm"
DATASET_ID = "agro_data"

if not IRRIGATION_URL: st.error("❌ Falta URL."); st.stop()

# ==========================
# GESTIÓN DE ERRORES PERSISTENTE
# ==========================
if "debug_logs" not in st.session_state:
    st.session_state.debug_logs = []

def add_log(msg, type="info"):
    """Guarda logs en memoria para que no se borren al refrescar"""
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    st.session_state.debug_logs.append({"ts": ts, "msg": msg, "type": type})

# ==========================
# FUNCIONES BQ (A PRUEBA DE BOMBAS)
# ==========================
def get_bq_client():
    add_log("Intentando crear cliente BigQuery...", "info")
    
    # 1. Intentar Secrets
    if "gcp_service_account" in st.secrets:
        try:
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"]
            )
            add_log("Credenciales leídas de st.secrets correctamente.", "success")
            return bigquery.Client(credentials=creds, project=PROJECT_ID)
        except Exception as e:
            add_log(f"Error creando credenciales desde secrets: {str(e)}", "error")
            return None

    # 2. Intentar Local
    try:
        add_log("Buscando credenciales por defecto (entorno)...", "warning")
        return bigquery.Client(project=PROJECT_ID)
    except Exception as e:
        add_log(f"Fallo total autenticación: {str(e)}", "error")
        return None

def save_feedback_to_bq(audit_log, rating, feedback_text, accepted):
    add_log("--- INICIO PROCESO DE GUARDADO ---", "info")
    
    client = get_bq_client()
    if not client:
        add_log("No hay cliente BQ. Abortando.", "error")
        return

    table_id = f"{PROJECT_ID}.{DATASET_ID}.recommendation_history"
    add_log(f"Tabla destino: {table_id}", "info")

    try:
        # 1. Limpieza: Aseguramos que sea un diccionario serializable (quitando fechas raras)
        audit_clean_dict = json.loads(json.dumps(audit_log, default=str))
        
        # 2. TRUCO FINAL: Convertir a STRING para que BigQuery no lo confunda con un RECORD
        # Si tu columna en BQ es JSON, a veces prefiere recibir el string serializado.
        audit_as_string = json.dumps(audit_clean_dict)

        row = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "location_id": 8507,
            "rating": rating,
            "user_feedback": feedback_text,
            "accepted": accepted,
            "full_audit_log": audit_as_string # <--- AQUÍ ESTÁ EL CAMBIO (Enviamos String)
        }
        
        add_log("Enviando fila a BigQuery...", "info")
        
        # Debug: ver qué enviamos
        # st.write(row) 
        
        errors = client.insert_rows_json(table_id, [row])
        
        if errors == []:
            add_log("✅ ¡INSERT EXITOSO! BigQuery devolvió OK.", "success")
            st.toast("Guardado OK", icon="🎉")
        else:
            add_log(f"❌ BigQuery rechazó los datos: {errors}", "error")
            # Si falla de nuevo, prueba a cambiar 'full_audit_log' por audit_clean_dict (el dict)
            # pero el error anterior sugería que quería string o había conflicto de tipos.

    except Exception as e:
        add_log(f"💥 EXCEPCIÓN PYTHON: {str(e)}", "error")
        add_log(traceback.format_exc(), "error")
def load_history_from_bq(selected_date=None):
    client = get_bq_client()
    if not client: return pd.DataFrame()
    
    where = f"WHERE DATE(timestamp) = '{selected_date.strftime('%Y-%m-%d')}'" if selected_date else ""
    q = f"SELECT timestamp, rating, user_feedback, full_audit_log, accepted FROM `{PROJECT_ID}.{DATASET_ID}.recommendation_history` {where} ORDER BY timestamp DESC LIMIT 20"
    
    try:
        return client.query(q).to_dataframe()
    except Exception as e:
        add_log(f"Error leyendo historial: {e}", "error")
        return pd.DataFrame()

# ==========================
# UI PRINCIPAL
# ==========================
st.title("🌿 Sistema Integral (Modo Debug)")

# ZONA DE DEBUG VISIBLE SIEMPRE
with st.expander("🛠️ CONSOLA DE DEPURACIÓN (Ver aquí si falla)", expanded=True):
    if st.button("Limpiar Logs"): st.session_state.debug_logs = []
    for log in st.session_state.debug_logs:
        if log["type"] == "error": st.error(f"[{log['ts']}] {log['msg']}")
        elif log["type"] == "success": st.success(f"[{log['ts']}] {log['msg']}")
        elif log["type"] == "warning": st.warning(f"[{log['ts']}] {log['msg']}")
        else: st.info(f"[{log['ts']}] {log['msg']}")

# Estado
if "results" not in st.session_state: st.session_state.results = None

with st.sidebar:
    st.header("📋 Configuración")
    with st.form("params"):
        submitted = st.form_submit_button("🔄 EJECUTAR ANÁLISIS")
    
    use_mock = st.toggle("Usar Mocks (Ahorrar Tokens)", True)

if submitted:
    # Lógica simplificada para probar el guardado
    add_log("Análisis ejecutado.", "info")
    if use_mock:
        st.session_state.results = {
            "irrigation": MOCK_IRRIGATION_DATA,
            "product": MOCK_PRODUCT_DATA,
            "audit": MOCK_PRODUCT_DATA["audit_log"]
        }
        add_log("Datos Mock cargados.", "success")
    else:
        # Aquí irían tus llamadas reales
        pass

tab_plan, tab_hist = st.tabs(["🧪 Plan & Feedback", "📜 Historial"])

# PESTAÑA FEEDBACK
with tab_plan:
    if st.session_state.results:
        res = st.session_state.results
        st.json(res["audit"])
        
        st.divider()
        st.subheader("Guardar Feedback")
        
        # FORMULARIO
        with st.form("fb_form"):
            rating = st.slider("Nota", 1, 5, 5)
            txt = st.text_area("Comentario", "Test debug")
            accepted = st.checkbox("Aceptado", True)
            
            # AL PULSAR GUARDAR
            if st.form_submit_button("💾 GUARDAR EN BIGQUERY"):
                save_feedback_to_bq(res["audit"], rating, txt, accepted)
    else:
        st.info("Ejecuta el análisis primero.")

# PESTAÑA HISTORIAL
with tab_hist:
    if st.button("🔄 Refrescar Tabla"):
        df = load_history_from_bq()
        if not df.empty:
            st.dataframe(df)
        else:
            st.warning("Tabla vacía o error de lectura (mira los logs arriba).")
