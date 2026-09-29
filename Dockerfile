FROM python:3.12-slim

WORKDIR /app

# Добавляем сертификат Минцифры в системное хранилище
COPY certs/certificate_MinDigDev.crt /usr/local/share/ca-certificates/certificate_MinDigDev.crt
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY data/ ./data/

CMD ["python", "-u", "app/main.py"]