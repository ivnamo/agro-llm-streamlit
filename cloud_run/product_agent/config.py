import os

PROJECT_ID = os.getenv("PROJECT_ID", "tfg-agro-llm")
BQ_DATASET = os.getenv("BQ_DATASET", "agro_data")
LOCATION_ID = int(os.getenv("LOCATION_ID", "8507"))
LOCATION_NAME = os.getenv("LOCATION_NAME", "S4 - Invernadero")

# Configuración RAG para Productos
# Si tienes los PDF de productos en otra ruta, cámbialo aquí:
RAG_PREFIX = os.getenv("RAG_PREFIX", "rag/productos") 
RAG_K = int(os.getenv("RAG_K", "5"))

HF_TOKEN = os.getenv("HF_TOKEN")
HF_MODEL_ID = os.getenv("HF_MODEL_ID", "deepseek-ai/DeepSeek-V3.2")
