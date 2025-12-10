FROM python:3.11-slim

# 1) Trabajamos inicialmente en /app
WORKDIR /app

# 2) Copiamos requirements.txt desde la RAÍZ del repo
#    (porque el build context será ".")
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 3) Copiamos TODO el repo dentro de /app
COPY . .

# 4) Ahora sí, nos movemos a la carpeta del servicio
WORKDIR /app/cloud_run/etl_cesens

# 5) Lanzamos functions-framework apuntando a la función backfill_cesens
CMD ["functions-framework", "--target=backfill_cesens", "--port=8080"]
