FROM python:3.9-slim

WORKDIR /app

COPY main.py .

# Instala dependências necessárias
RUN apt-get update && apt-get install -y \
    nodejs \
    curl \
    rustc \
    && apt-get clean

RUN pip install flask

CMD ["python", "main.py"]
