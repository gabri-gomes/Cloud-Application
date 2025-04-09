FROM python:3.9-slim

WORKDIR /app

COPY . /app

RUN apt-get update && apt-get install -y netcat-openbsd \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

RUN chmod +x wait-for-it.sh

CMD ["./wait-for-it.sh", "data_base:5432", "--", "python", "main.py"]
