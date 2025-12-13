# cloud_run/stress_agent/config.py
import os

PROJECT_ID = os.getenv("PROJECT_ID", "tfg-agro-llm")
BQ_DATASET = os.getenv("BQ_DATASET", "agro_data")
LOCATION_ID = int(os.getenv("LOCATION_ID", "8507"))
LOCATION_NAME = os.getenv("LOCATION_NAME", "S4 - Invernadero")

# Configuración del modelo (Hugging Face / Gemini)
# Puedes usar el mismo que para los otros agentes
HF_TOKEN = os.getenv("HF_TOKEN")
HF_MODEL_ID = os.getenv("HF_MODEL_ID", "Qwen/Qwen2.5-7B-Instruct")

# Umbrales de alerta (pueden ser usados en lógica o pasados al prompt)
# VPD > 1.5-2.0 kPa empieza a ser estresante para tomate
VPD_HIGH_THRESHOLD = 1.8 
UV_HIGH_THRESHOLD = 7.0
