FROM python:3.11-slim

WORKDIR /app

# Copiamos requirements desde la raíz del repo
COPY ../../requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos TODO el repo dentro de /app
# (incluye common/, cloud_run/irrigation_agent, etc.)
COPY ../../ ./

# Arrancamos el functions-framework apuntando al entrypoint
CMD ["functions-framework", "--target=run_irrigation_agent", "--port=8080"]
