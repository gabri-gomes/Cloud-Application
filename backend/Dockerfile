FROM python:3.9-slim

WORKDIR /app

COPY . /app

# Instala dependências adicionais para suporte a múltiplas linguagens
RUN apt-get update && apt-get install -y \
    netcat-openbsd \
    g++ \
    nodejs \
    curl \
    && curl https://sh.rustup.rs -sSf | sh -s -- -y \
    && rm -rf /var/lib/apt/lists/*

# Adiciona o Rust ao PATH
ENV PATH="/root/.cargo/bin:${PATH}"

RUN chmod +x wait-for-it.sh
RUN pip install --no-cache-dir -r requirements.txt

CMD ["./wait-for-it.sh", "data_base:5432", "--", "python", "main.py"]
