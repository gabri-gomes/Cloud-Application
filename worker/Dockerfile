FROM python:3.10-slim

WORKDIR /app

# Copia só as deps primeiro para agilizar cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código do worker
COPY tasks.py . 
COPY tasks.py executor_client.py ./


# O comando será sobrescrito pelo docker-compose (celery -A tasks worker)
ENTRYPOINT ["celery", "-A", "tasks", "worker", "--loglevel=info"]
