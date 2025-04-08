FROM python:3.9-slim

WORKDIR /app

COPY . /app

RUN apt-get update && apt-get install -y netcat-openbsd

RUN chmod +x wait-for-it.sh
RUN pip install --no-cache-dir -r requirements.txt

CMD ["./wait-for-it.sh", "data_base:5432", "--", "python", "main.py"]
