FROM python:3.10-slim

WORKDIR /app

# Install system dependencies for DNS lookups
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x start.sh

# Start both the FastAPI web server and the Celery worker
CMD ["./start.sh"]
