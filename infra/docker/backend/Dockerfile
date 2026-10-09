FROM python:3.13-slim

# ca-certificates: the weather lookup in weather.py is the only outbound TLS
# call this service makes, and urllib uses the SYSTEM trust store. pip ships
# its own bundle, so a working `pip install` above does not prove this is
# present. Without it the lookup fails with CERTIFICATE_VERIFY_FAILED, which
# reads like the weather service being down.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first for layer caching
COPY apps/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY apps/backend/ ./

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
