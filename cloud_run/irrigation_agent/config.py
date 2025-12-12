import os

PROJECT_ID = os.getenv("PROJECT_ID", "tfg-agro-llm")
BQ_DATASET = os.getenv("BQ_DATASET", "agro_data")

LOCATION_ID = int(os.getenv("LOCATION_ID", "8507"))
LOCATION_NAME = os.getenv("LOCATION_NAME", "S4 - Invernadero")

# Hugging Face (router)
HF_TOKEN = os.getenv("HF_TOKEN")
HF_MODEL_ID = os.getenv("HF_MODEL_ID", "meta-llama/Meta-Llama-3-8B-Instruct")

# RAG: K por defecto para este agente (puede sobreescribir el de common si quieres)
RAG_K = int(os.getenv("RAG_K", "5"))
